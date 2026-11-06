"""Eventos existentes de pedidos e substituições, com escopo antes da página."""

import uuid
from dataclasses import replace

from sqlalchemy import text
from test_contracts import validator

from vx_materials_api.db.models import AuditLog, RegistrationOrder, SanitizationProposal
from vx_materials_api.services.proposal_queries import audit_events


def test_batch_substitution_is_shown_as_system_without_human_role(approval_case):
    case = approval_case
    db, original = case["session"], case["proposal"]
    replacement = SanitizationProposal(
        tenant_id=original.tenant_id,
        proposal_type=original.proposal_type,
        members=original.members,
        primary_material_id=original.primary_material_id,
        changeset={**original.changeset, "conflicts": ["Nova revisão"]},
        changeset_hash="changed-rules",
        technical_review_status="PENDING",
        fiscal_review_status="NOT_REQUIRED",
    )
    db.add(replacement)
    db.flush()
    # Mesma função restrita que insert_proposals chama com a credencial do batch.
    db.execute(text("SET LOCAL ROLE batch_user"))
    assert (
        db.execute(text("SELECT supersede_proposals(ARRAY[CAST(:id AS uuid)])"), {"id": replacement.id}).scalar_one()
        == 1
    )
    db.execute(text("RESET ROLE"))
    db.commit()
    for principal in case["principals"][:2]:
        result = audit_events(db, principal, limit=1)
        validator({"$ref": "#/components/schemas/AuditList"}).validate(result)
        event = result["items"][0]
        assert event["actor"] == "Sistema" and event["actor_type"] == "SYSTEM"
        assert event["effective_role"] is None
        assert event["action"] == "PROPOSAL_SUPERSEDED"
        assert event["after"]["superseded_by"] == str(replacement.id)
        assert event["before"]["status"] == "PENDING" and event["after"]["status"] == "STALE"
        assert event["reason"] and event["created_at"]
        assert event["request_id"] == ""  # A função não inventa uma requisição HTTP.
    assert audit_events(db, case["principals"][2])["items"] == []
    assert audit_events(db, replace(case["principals"][0], center_codes=frozenset({"1100"})))["items"] == []
    assert audit_events(db, replace(case["principals"][1], tenant_id=uuid.uuid4()))["items"] == []


def test_mixed_actor_and_entity_pagination_skips_unauthorized_resources(approval_case):
    case = approval_case
    db = case["session"]
    governance, fiscal, requester = case["principals"]
    expected = []
    for number in range(12):
        order = RegistrationOrder(
            tenant_id=governance.tenant_id,
            origin="CHAT",
            requester_user_id=requester.user_id,
            original_text="Pedido",
            center_code="1100" if number % 2 else "9999",
            status="REJECTED",
        )
        db.add(order)
        db.flush()
        event = AuditLog(
            id=uuid.UUID(int=number + 1),
            tenant_id=governance.tenant_id,
            actor_user_id=requester.user_id if number % 3 else governance.user_id,
            actor_type="USER",
            effective_role="ROLE_SOLICITANTE" if number % 3 else "ROLE_GOVERNANCA_PDM",
            action="ORDER_SUBMITTED" if number % 3 else "ORDER_REJECTED",
            entity_type="registration_order",
            entity_id=str(order.id),
            before_json={"status": "DRAFT", "financial": {"total_value": "100"}},
            after_json={"status": "REJECTED", "unit_price": "5"},
            reason="Conferido",
            request_id=f"request-{number}",
        )
        db.add(event)
        if number % 2:
            expected.append(str(event.id))
    system_id = uuid.UUID(int=13)
    db.add(
        AuditLog(
            id=system_id,
            tenant_id=governance.tenant_id,
            actor_type="SYSTEM",
            action="PROPOSAL_SUPERSEDED",
            entity_type="sanitization_proposal",
            entity_id=str(case["proposal"].id),
            before_json={"status": "PENDING"},
            after_json={"status": "STALE", "superseded_by": str(uuid.uuid4())},
        )
    )
    expected.append(str(system_id))
    # UUID conhecido não habilita recurso de outro tenant.
    alien = RegistrationOrder(
        tenant_id=uuid.uuid4(), origin="IMPORT", original_text="Alheio", center_code="1100", status="REGISTERED"
    )
    db.add(alien)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=governance.tenant_id,
            actor_type="USER",
            actor_user_id=governance.user_id,
            effective_role="ROLE_GOVERNANCA_PDM",
            action="ORDER_REJECTED",
            entity_type="registration_order",
            entity_id=str(alien.id),
        )
    )
    db.commit()

    def pages(principal):
        found, cursor = [], None
        for _ in range(15):
            response = audit_events(db, principal, cursor=cursor, limit=2)
            found.extend(response["items"])
            cursor = response["next_cursor"]
            if cursor is None:
                return found
        raise AssertionError("Paginação não terminou")

    technical = pages(governance)
    assert [event["id"] for event in technical] == expected
    assert "total_value" not in str(technical) and "unit_price" not in str(technical)
    assert "total_value" in str(pages(fiscal))
    own = pages(requester)
    assert {event["id"] for event in own} == {str(uuid.UUID(int=n + 1)) for n in range(12) if n % 2 and n % 3}
    assert all(event["actor_type"] == "USER" and event["action"] == "ORDER_SUBMITTED" for event in own)
