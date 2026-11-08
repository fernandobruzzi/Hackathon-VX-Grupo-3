"""Equivalentes autorizados quando falta saldo (#246), com PostgreSQL real."""

import uuid

from sqlalchemy import func, select
from test_purchase_forwards import REQUESTS, add_material, add_stock, case, headers, login, new_request  # noqa: F401

from vx_materials_api.db.models import AuditLog, MaterialInventorySnapshot

EQUIVALENCES = "/api/v1/material-equivalences"


def approve(client, first, second, persona="GESTOR_CADASTRO"):
    me = login(client, persona)
    body = {"material_id": str(first.id), "equivalent_material_id": str(second.id), "basis": "Ficha técnica conferida."}
    return client.post(EQUIVALENCES, json=body, headers=headers(me))


def alternatives(client, request):
    return client.get(f"{REQUESTS}/{request['id']}/equivalent-alternatives")


def substitute(client, me, request, material, confirm=True):
    body = {"expected_version": request["version"], "material_id": str(material.id), "confirm_substitution": confirm}
    return client.post(f"{REQUESTS}/{request['id']}/substitution", json=body, headers=headers(me))


def test_only_approved_equivalents_are_offered_and_substitution_is_recorded(case):  # noqa: F811
    client, db, me, dataset = case
    wanted, similar, equivalent = add_material(db), add_material(db), add_material(db)
    for material, quantity in [(wanted, "0"), (similar, "40"), (equivalent, "25")]:
        add_stock(db, dataset, material, quantity)
    snapshots = [(row.id, row.quantity) for row in db.scalars(select(MaterialInventorySnapshot))]
    request = new_request(client, me, wanted)

    # Sem registro aprovado, nada é oferecido, nem o produto parecido com saldo.
    assert alternatives(client, request).json()["items"] == []
    # Só a Governança aprova; o solicitante não registra equivalência.
    assert approve(client, wanted, equivalent, "SOLICITANTE_OPERACAO").status_code == 403
    assert approve(client, wanted, equivalent).status_code == 201
    me = login(client)
    listed = alternatives(client, request).json()
    assert listed["shortage"] is True
    assert [item["material_code"] for item in listed["items"]] == [equivalent.material_code]
    assert listed["items"][0]["available_quantity"] == "25.000000"

    # A troca exige confirmação explícita.
    refused = substitute(client, me, request, equivalent, confirm=False)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    unapproved = substitute(client, me, request, similar)
    assert unapproved.json()["error"]["code"] == "EQUIVALENCE_NOT_APPROVED"

    done = substitute(client, me, request, equivalent)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["material_id"] == str(equivalent.id)
    assert body["substitution"]["from_material_code"] == wanted.material_code
    assert body["history"][-1]["action"] == "MATERIAL_REQUEST_SUBSTITUTED"
    audit = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == request["id"], AuditLog.action == "MATERIAL_REQUEST_SUBSTITUTED")
    )
    assert audit.after_json["substitution"]["to_material_code"] == equivalent.material_code
    # Materiais continuam separados e os snapshots não mudam.
    assert [(row.id, row.quantity) for row in db.scalars(select(MaterialInventorySnapshot))] == snapshots
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_type == "material_equivalence"))


def test_no_alternatives_while_the_requested_material_has_stock(case):  # noqa: F811
    client, db, me, dataset = case
    wanted, equivalent = add_material(db), add_material(db)
    add_stock(db, dataset, wanted, "50")
    add_stock(db, dataset, equivalent, "50")
    request = new_request(client, me, wanted)
    assert approve(client, equivalent, wanted).status_code == 201
    login(client)
    listed = alternatives(client, request).json()
    assert listed["shortage"] is False and listed["items"] == []
    assert approve(client, wanted, equivalent).json()["error"]["code"] == "EQUIVALENCE_EXISTS"
    assert uuid.UUID(request["id"])
