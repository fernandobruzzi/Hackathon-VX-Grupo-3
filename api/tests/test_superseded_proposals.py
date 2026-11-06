"""Nova execução do batch com conteúdo alterado substitui as propostas pendentes anteriores (#115)."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from clients.storage import LocalObjectStore
from domain.proposals import proposal_hash
from pipelines.full_run import run_sanitize
from repositories import batch_repository
from vx_materials_api.bootstrap import bootstrap
from vx_materials_api.db.temporary_login import temporary_login

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")
CHANGED_RULE = "Regra alterada entre execuções"

PENDING_PER_KEY = """
    SELECT count(*) FROM (
        SELECT proposal_type, members FROM sanitization_proposals WHERE status = 'PENDING'
        GROUP BY proposal_type, members HAVING count(*) > 1
    ) duplicated
"""


def changed_rules(monkeypatch):
    """Simula regras novas: todo changeset ganha um conflito a mais, então hash e id mudam."""
    original = batch_repository.approval_payload

    def payload(proposal, ids, dataset_id):
        members, changeset, _ = original(proposal, ids, dataset_id)
        changeset = {**changeset, "conflicts": [*changeset["conflicts"], CHANGED_RULE]}
        return members, changeset, proposal_hash(members, changeset)

    monkeypatch.setattr(batch_repository, "approval_payload", payload)


@pytest.fixture(scope="module")
def runs(migrated_url, tmp_path_factory):
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(
            text("TRUNCATE datasets, reference_versions, materials_master, sanitization_proposals, audit_logs CASCADE")
        )
    monkeypatch = pytest.MonkeyPatch()
    with temporary_login(migrated_url, "api_user") as api_url, temporary_login(migrated_url, "batch_user") as batch_url:
        api = create_engine(api_url)
        bootstrap(KIT, api, LocalObjectStore(tmp_path_factory.mktemp("storage")))
        api.dispose()
        first = run_sanitize(PDM, database_url=batch_url)
        with admin.begin() as connection:
            # Decisões já tomadas nunca são revertidas por uma execução nova.
            decided = dict(
                connection.execute(
                    text(
                        """
                        UPDATE sanitization_proposals SET status = v.status
                        FROM (
                            SELECT id, CASE WHEN row_number() OVER (ORDER BY id) = 1 THEN 'APPLIED'
                                            ELSE 'REJECTED' END AS status
                            FROM sanitization_proposals WHERE proposal_type = 'UNIT_CORRECTION'
                            ORDER BY id LIMIT 2
                        ) v
                        WHERE sanitization_proposals.id = v.id
                        RETURNING sanitization_proposals.id, sanitization_proposals.status
                        """
                    )
                ).all()
            )
        changed_rules(monkeypatch)
        second = run_sanitize(PDM, database_url=batch_url)
        third = run_sanitize(PDM, database_url=batch_url)
        yield first, second, third, decided, admin
    monkeypatch.undo()
    admin.dispose()


def scalar(engine, query, **params):
    with engine.connect() as connection:
        return connection.execute(text(query), params).scalar_one()


def test_second_run_leaves_one_pending_set_per_material_and_type(runs):
    first, second, _, decided, admin = runs
    assert second["inserted"] == first["proposals"]
    assert scalar(admin, PENDING_PER_KEY) == 0
    pending = scalar(admin, "SELECT count(*) FROM sanitization_proposals WHERE status = 'PENDING'")
    assert pending == second["proposals"]
    assert (
        scalar(
            admin,
            "SELECT count(*) FROM sanitization_proposals "
            "WHERE status = 'PENDING' AND NOT changeset->'conflicts' ? :rule",
            rule=CHANGED_RULE,
        )
        == 0
    )
    stale = scalar(admin, "SELECT count(*) FROM sanitization_proposals WHERE status = 'STALE'")
    assert stale == first["proposals"] - len(decided)


def test_every_superseded_proposal_is_audited_as_system(runs):
    _, _, _, _, admin = runs
    with admin.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """
                SELECT a.actor_type, a.before_json, a.after_json, p.version, n.status AS new_status,
                       n.proposal_type = p.proposal_type AS same_type, n.members = p.members AS same_members
                FROM sanitization_proposals p
                JOIN audit_logs a ON a.entity_id = p.id::text AND a.action = 'PROPOSAL_SUPERSEDED'
                JOIN sanitization_proposals n ON n.id::text = a.after_json->>'superseded_by'
                WHERE p.status = 'STALE'
                """
                )
            )
            .mappings()
            .all()
        )
    stale = scalar(admin, "SELECT count(*) FROM sanitization_proposals WHERE status = 'STALE'")
    assert len(rows) == stale > 0
    for row in rows:
        assert row["actor_type"] == "SYSTEM"
        assert row["before_json"]["status"] == "PENDING"
        assert (row["after_json"]["status"], row["after_json"]["version"]) == ("STALE", row["version"])
        assert row["before_json"]["version"] == row["version"] - 1
        assert (row["new_status"], row["same_type"], row["same_members"]) == ("PENDING", True, True)


def test_applied_and_rejected_proposals_never_change(runs):
    _, _, _, decided, admin = runs
    assert sorted(decided.values()) == ["APPLIED", "REJECTED"]
    with admin.connect() as connection:
        for proposal_id, status in decided.items():
            row = connection.execute(
                text("SELECT status, version FROM sanitization_proposals WHERE id = :id"), {"id": proposal_id}
            ).one()
            assert (row.status, row.version) == (status, 1)
            audits = connection.execute(
                text("SELECT count(*) FROM audit_logs WHERE entity_id = :id"), {"id": str(proposal_id)}
            ).scalar_one()
            assert audits == 0


def test_repeating_the_same_content_supersedes_nothing(runs):
    _, second, third, _, admin = runs
    assert third["inserted"] == 0
    assert third["proposals"] == second["proposals"]
    assert scalar(admin, "SELECT count(*) FROM audit_logs WHERE action = 'PROPOSAL_SUPERSEDED'") == scalar(
        admin, "SELECT count(*) FROM sanitization_proposals WHERE status = 'STALE'"
    )


def test_batch_supersedes_only_through_the_function(migrated_url, connection):
    """batch_user executa a substituição, mas segue sem acesso direto à auditoria."""
    connection.execute(text("SET LOCAL ROLE batch_user"))
    assert connection.execute(text("SELECT supersede_proposals(ARRAY[]::uuid[])")).scalar_one() == 0
    with pytest.raises(Exception, match="permission denied"):
        with connection.begin_nested():
            connection.execute(text("SELECT count(*) FROM audit_logs"))
