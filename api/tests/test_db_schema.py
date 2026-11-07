import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from vx_materials_api.db.cli import PASSWORD_VARIABLES, alembic_config, set_passwords
from vx_materials_api.db.models import Base

TABLES = {
    "material_requests",
    "automatic_correction_runs",
    "automatic_correction_results",
    "manual_reviews",
    "login_transactions",
    "users_sso",
    "auth_sessions",
    "audit_logs",
    "materials_master",
    "sanitization_proposals",
    "registration_orders",
    "chat_sessions",
    "chat_messages",
    "enrichment_sources",
    "datasets",
    "reference_versions",
    "material_inventory_snapshots",
    "material_search_index",
    "batch_jobs",
    "operation_requests",
    "inventory_consolidations",
    "quality_snapshots",
    "quality_snapshot_items",
    "lot_reviews",
}
VIEWS = {
    "mcp_automatic_index_pending",
    "mcp_catalog",
    "mcp_inventory",
    "mcp_inventory_financial",
    "mcp_references",
    "mcp_search_index",
    "mcp_evidence",
    "mcp_callers",
    "mcp_datasets",
}


def as_role(connection, role, statement, **params):
    """Executa como a credencial, em um savepoint para sobreviver a uma permissão negada."""
    with connection.begin_nested():
        connection.execute(text(f"SET LOCAL ROLE {role}"))
        result = connection.execute(text(statement), params)
        rows = result.all() if result.returns_rows else None
        connection.execute(text("RESET ROLE"))
    return rows


def denied(connection, role, statement, **params):
    with pytest.raises(DBAPIError, match="permission denied"):
        as_role(connection, role, statement, **params)


def test_every_architecture_table_exists(migrated_url):
    engine = create_engine(migrated_url)
    inspector = inspect(engine)
    assert TABLES <= set(inspector.get_table_names())
    assert set(Base.metadata.tables) == TABLES
    assert VIEWS <= set(inspector.get_view_names())
    engine.dispose()


def test_models_match_migrations(migrated_url):
    command.check(alembic_config(migrated_url))


def test_embedding_column_has_512_dimensions(connection):
    kind = connection.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'material_search_index'::regclass AND attname = 'embedding'"
        )
    ).scalar_one()
    assert kind == "vector(512)"


def test_migrations_run_down_and_up_again(database_url, migrated_url):
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    engine = create_engine(database_url)
    assert not TABLES & set(inspect(engine).get_table_names())
    engine.dispose()
    command.upgrade(config, "head")


def test_two_canonical_actives_cannot_share_identity(connection, add_material):
    add_material("A", canonical=True, identity="PDM100|X|Y")
    with pytest.raises(IntegrityError, match="uq_materials_master_canonical_identity"):
        with connection.begin_nested():
            add_material("B", canonical=True, identity="PDM100|X|Y")


def test_legacy_duplicates_are_allowed(connection, add_material):
    add_material("A", identity="PDM100|X|Y")
    add_material("B", identity="PDM100|X|Y")
    add_material("C", canonical=True, identity="PDM100|X|Y")
    add_material("D", status="OBSOLETO", canonical=True, identity="PDM100|X|Y")


def test_same_identity_is_allowed_in_another_tenant(connection, add_material):
    add_material("A", canonical=True, identity="K")
    add_material("A", canonical=True, identity="K", tenant_id=uuid.uuid4())


def test_material_code_is_unique_per_tenant(connection, add_material):
    add_material("A")
    with pytest.raises(IntegrityError, match="uq_materials_master_tenant_id"):
        with connection.begin_nested():
            add_material("A")


def test_active_material_cannot_redirect(connection, add_material):
    primary = add_material("A")
    add_material("B", status="BLOQUEADO", target=primary)
    with pytest.raises(IntegrityError, match="active_has_no_target"):
        with connection.begin_nested():
            add_material("C", target=primary)


def test_material_cannot_point_to_itself(connection, add_material):
    blocked = add_material("A", status="BLOQUEADO")
    with pytest.raises(IntegrityError, match="no_self_target"):
        with connection.begin_nested():
            connection.execute(
                text("UPDATE materials_master SET active_code_target = id WHERE id = :i"), {"i": blocked}
            )


def test_invalid_status_is_rejected(connection, add_material):
    with pytest.raises(IntegrityError, match="ck_materials_master_status"):
        with connection.begin_nested():
            add_material("A", status="QUALQUER")


def test_chat_order_requires_requester(connection, tenant):
    with pytest.raises(IntegrityError, match="chat_has_requester"):
        with connection.begin_nested():
            connection.execute(
                text("INSERT INTO registration_orders (tenant_id, origin, original_text) VALUES (:t, 'CHAT', 'x')"),
                {"t": tenant},
            )
    connection.execute(
        text("INSERT INTO registration_orders (tenant_id, origin, original_text) VALUES (:t, 'IMPORT', 'x')"),
        {"t": tenant},
    )


AUDIT_INSERT = (
    "INSERT INTO audit_logs (tenant_id, actor_type, action, entity_type, entity_id) VALUES (:t, 'USER', 'X', 'Y', 'Z')"
)


def test_api_user_can_insert_and_read_audit_but_never_change_it(connection, tenant):
    as_role(connection, "api_user", AUDIT_INSERT, t=tenant)
    assert as_role(connection, "api_user", "SELECT count(*) FROM audit_logs")[0][0] >= 1
    denied(connection, "api_user", "UPDATE audit_logs SET reason = 'x'")
    denied(connection, "api_user", "DELETE FROM audit_logs")


@pytest.mark.parametrize("role", ["batch_user", "mcp_reader"])
def test_other_credentials_have_no_audit_access(connection, tenant, role):
    denied(connection, role, AUDIT_INSERT, t=tenant)
    denied(connection, role, "SELECT * FROM audit_logs")


def test_original_inventory_is_immutable_for_api(connection):
    denied(connection, "api_user", "UPDATE material_inventory_snapshots SET quantity = 0")
    denied(connection, "api_user", "DELETE FROM material_inventory_snapshots")


@pytest.mark.parametrize("table", ["quality_snapshots", "quality_snapshot_items"])
def test_published_quality_snapshots_are_immutable_for_api(connection, table):
    denied(connection, "api_user", f"UPDATE {table} SET tenant_id = tenant_id")
    denied(connection, "api_user", f"DELETE FROM {table}")
    denied(connection, "batch_user", f"SELECT * FROM {table}")


def test_lot_reviews_are_kept_and_only_the_api_writes_them(connection):
    denied(connection, "api_user", "DELETE FROM lot_reviews")
    denied(connection, "batch_user", "SELECT * FROM lot_reviews")
    denied(connection, "mcp_reader", "SELECT * FROM lot_reviews")


def test_mcp_reader_reads_views_only(connection, add_material):
    add_material("A")
    assert as_role(connection, "mcp_reader", "SELECT count(*) FROM mcp_catalog")[0][0] >= 1
    for view in VIEWS:
        as_role(connection, "mcp_reader", f"SELECT * FROM {view}")
    denied(connection, "mcp_reader", "SELECT * FROM materials_master")
    denied(connection, "mcp_reader", "SELECT * FROM users_sso")


def test_mcp_reader_cannot_write_master(connection, tenant):
    denied(
        connection,
        "mcp_reader",
        "INSERT INTO materials_master (tenant_id, source_system, material_code, status) "
        "VALUES (:t, 'ERP', 'X', 'ATIVO')",
        t=tenant,
    )
    denied(connection, "mcp_reader", "UPDATE mcp_catalog SET status = 'OBSOLETO'")
    denied(connection, "mcp_reader", "DELETE FROM mcp_catalog")


def test_prices_are_only_in_the_financial_view(connection):
    def columns(view):
        return {c["name"] for c in inspect(connection).get_columns(view)}

    assert not {"unit_price", "total_value"} & columns("mcp_inventory")
    assert {"unit_price", "total_value"} <= columns("mcp_inventory_financial")
    as_role(connection, "mcp_reader", "SELECT unit_price, total_value FROM mcp_inventory_financial")


def test_raw_inventory_record_stays_hidden_from_mcp(connection):
    assert "raw_record" not in {c["name"] for c in inspect(connection).get_columns("mcp_inventory_financial")}
    denied(connection, "mcp_reader", "SELECT raw_record FROM material_inventory_snapshots")


def test_batch_cannot_change_master_or_apply_approvals_directly(connection):
    denied(connection, "batch_user", "UPDATE materials_master SET status = 'OBSOLETO'")
    denied(connection, "batch_user", "DELETE FROM sanitization_proposals")


def test_batch_can_write_proposals(connection, tenant):
    as_role(
        connection,
        "batch_user",
        "INSERT INTO sanitization_proposals (tenant_id, proposal_type, changeset_hash) VALUES (:t, 'MERGE', 'h')",
        t=tenant,
    )


@pytest.fixture
def disposable_role(migrated_url):
    """Role NOLOGIN membro de api_user, apagada no fim: a senha de api_user nunca muda."""
    name = f"vx_tmp_setpw_{uuid.uuid4().hex[:8]}"
    admin = create_engine(migrated_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE ROLE "{name}" NOLOGIN INHERIT IN ROLE api_user'))
    yield name
    with admin.connect() as conn:
        conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = :n"), {"n": name})
        conn.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
    admin.dispose()


def test_set_passwords_enables_login_only_with_the_right_password(migrated_url, monkeypatch, disposable_role):
    monkeypatch.setenv("VX_TEST_ROLE_PASSWORD", "it's-a-test")
    monkeypatch.delenv("VX_TEST_UNSET_PASSWORD", raising=False)
    roles = {disposable_role: "VX_TEST_ROLE_PASSWORD", "mcp_reader": "VX_TEST_UNSET_PASSWORD"}
    assert set_passwords(migrated_url, roles) == [disposable_role]

    login = make_url(migrated_url).set(username=disposable_role, password="it's-a-test")
    engine = create_engine(login)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_user")).scalar_one() == disposable_role
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("DELETE FROM audit_logs"))
    engine.dispose()

    engine = create_engine(login.set(password="wrong"))
    with pytest.raises(OperationalError, match="authentication failed"):
        engine.connect()
    engine.dispose()


def test_set_passwords_targets_the_application_roles_by_default():
    assert set(PASSWORD_VARIABLES) == {"api_user", "batch_user", "mcp_reader"}


def test_migration_history_has_one_unambiguous_head():
    scripts = ScriptDirectory.from_config(alembic_config())
    assert len(scripts.get_heads()) == 1


def test_manual_observations_cannot_be_rewritten_by_application_roles(connection):
    as_role(connection, "api_user", "SELECT * FROM manual_reviews")
    as_role(connection, "batch_user", "SELECT * FROM manual_reviews")
    for role in ("api_user", "batch_user"):
        denied(connection, role, "UPDATE manual_reviews SET reasons = ARRAY['OUTRO']")
        denied(connection, role, "DELETE FROM manual_reviews")
    denied(connection, "mcp_reader", "SELECT * FROM manual_reviews")


def test_batch_cannot_enable_automatic_corrections(connection):
    denied(
        connection, "batch_user", "UPDATE batch_jobs SET automatic_corrections = jsonb_build_object('mode', 'APPLY')"
    )
    for table in ("automatic_correction_runs", "automatic_correction_results"):
        denied(connection, "batch_user", f"SELECT * FROM {table}")
        denied(connection, "mcp_reader", f"SELECT * FROM {table}")
        denied(connection, "api_user", f"DELETE FROM {table}")
