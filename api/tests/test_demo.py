"""Reset da demo: guarda de ambiente, estado preparado e volta ao mesmo estado depois de um ensaio."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from clients.storage import LocalObjectStore
from domain.pdm_loader import load_pdm
from vx_materials_api import demo
from vx_materials_api.bootstrap import TENANT_ID
from vx_materials_api.db.models import AuditLog, SanitizationProposal, UserSso
from vx_materials_api.main import create_app

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = str(KIT / "03_padrao_cadastro_PDM.xlsx")
ORIGIN = "http://localhost:8000"


@pytest.fixture(scope="module")
def prepared(migrated_url, tmp_path_factory):
    store = LocalObjectStore(tmp_path_factory.mktemp("demo-storage"))
    first = demo.reset(migrated_url, KIT, store, PDM)
    engine = create_engine(migrated_url)
    yield migrated_url, store, first, engine
    engine.dispose()


def test_reset_requires_demo_mode_and_the_confirmed_database(monkeypatch):
    url = "postgresql+psycopg://migration_user:x@127.0.0.1:5432/vx_materiais"
    monkeypatch.delenv("DEMO_MODE", raising=False)
    with pytest.raises(demo.DemoGuardError, match="DEMO_MODE"):
        demo.check_demo_environment(url, "vx_materiais")
    monkeypatch.setenv("DEMO_MODE", "true")
    for confirm in (None, "", "outro_banco"):
        with pytest.raises(demo.DemoGuardError, match="--confirm vx_materiais"):
            demo.check_demo_environment(url, confirm)
    demo.check_demo_environment(url, "vx_materiais")


def test_cli_refuses_outside_demo_before_touching_the_database(monkeypatch, capsys):
    # Porta 1: se o comando tentasse conectar, falharia com outro erro.
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/nao_existe")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert demo.main(["reset", "--confirm", "nao_existe"]) == 2
    assert "DEMO_MODE=true" in capsys.readouterr().err
    monkeypatch.setenv("DEMO_MODE", "true")
    assert demo.main(["reset", "--confirm", "outro"]) == 2
    assert "--confirm nao_existe" in capsys.readouterr().err


def test_reset_prepares_proposals_orders_and_the_three_personas(prepared):
    _, _, summary, engine = prepared
    counts = summary["state"]["counts"]
    assert counts["materials"] == 23554
    assert counts["orders"] == summary["orders_imported"] == 520
    assert counts["proposals"] == counts["pending_proposals"] > 0
    assert summary["proposals_by_type"]["MERGE"] > 0
    assert counts["material_search_index"] == 23554
    for empty in ("audit_events", "chat_sessions", "operation_requests", "inventory_consolidations", "batch_jobs"):
        assert counts[empty] == 0, empty
    picks = summary["demo_proposals"]
    assert picks["governance"]["fiscal_review_status"] == "NOT_REQUIRED"
    assert picks["fiscal"]["fiscal_review_status"] == "PENDING"
    with engine.connect() as connection:
        users = connection.execute(
            select(UserSso.subject, UserSso.roles_snapshot).where(UserSso.issuer == demo.LOCAL_ISSUER)
        ).all()
        orders = connection.execute(
            text("SELECT DISTINCT origin, status, requester_user_id IS NULL FROM registration_orders")
        ).all()
    assert {subject for subject, _ in users} == {"SOLICITANTE_OPERACAO", "GESTOR_CADASTRO", "AUDITOR_FISCAL"}
    assert orders == [("IMPORT", "DRAFT", True)]


def _login(client, persona):
    response = client.post("/api/v1/auth/local-session", json={"persona": persona}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _approve(client, csrf, proposal_id, area, version, primary=None):
    body = {"expected_version": version, "review_area": area, "decision": "APPROVE", "reason": "Ensaio da demo."}
    if primary:
        body["primary_material_code"] = primary
    response = client.post(
        f"/api/v1/sanitization/{proposal_id}/decide",
        json=body,
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_rehearsal_changes_the_state_and_reset_brings_back_the_same_one(prepared, monkeypatch):
    url, store, first, engine = prepared
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_TEST_SESSION", "true")
    app = create_app(session_factory=sessionmaker(engine, expire_on_commit=False))
    app.state.pdm_catalog = load_pdm(PDM)
    picks = first["demo_proposals"]

    with TestClient(app, base_url=ORIGIN) as client:
        governance = _login(client, "GESTOR_CADASTRO")
        simple = picks["governance"]
        applied = _approve(client, governance, simple["id"], "TECHNICAL", 1, simple["suggested_primary_code"])
        assert applied["status"] == "APPLIED"
        fiscal_pick = picks["fiscal"]
        primary = fiscal_pick["suggested_primary_code"]
        technical = _approve(client, governance, fiscal_pick["id"], "TECHNICAL", 1, primary)
        assert technical["status"] == "PENDING"
        fiscal = _login(client, "AUDITOR_FISCAL")
        done = _approve(client, fiscal, fiscal_pick["id"], "FISCAL", technical["version"])
        assert done["status"] == "APPLIED"

    rehearsed = demo.fingerprint(engine)
    assert rehearsed["sha256"] != first["state"]["sha256"]
    assert rehearsed["counts"]["audit_events"] == 3
    with engine.connect() as connection:
        sessions_before = connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()

    second = demo.reset(url, KIT, store, PDM)

    assert second["state"] == first["state"]
    assert second["demo_proposals"] == first["demo_proposals"]
    with engine.connect() as connection:
        statuses = connection.execute(
            select(SanitizationProposal.status).where(
                SanitizationProposal.id.in_([uuid.UUID(simple["id"]), uuid.UUID(fiscal_pick["id"])])
            )
        ).scalars()
        assert set(statuses) == {"PENDING"}
        assert connection.execute(select(AuditLog.id)).first() is None
        # O reset não desloga quem já entrou: as sessões de login continuam.
        assert connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one() == sessions_before
        tenant_users = connection.execute(select(UserSso.tenant_id).where(UserSso.issuer == demo.LOCAL_ISSUER))
        assert set(tenant_users.scalars()) == {TENANT_ID}
