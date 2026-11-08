"""Notificações do solicitante derivadas da auditoria (#249), com PostgreSQL real."""

from test_stock_reservations import (  # noqa: F401
    add_dataset,
    add_material,
    add_stock,
    case,
    headers,
    login,
    new_request,
    reserve,
)

NOTIFICATIONS = "/api/v1/notifications"


def test_reservation_notifies_only_the_owner_and_can_be_marked_read(case):  # noqa: F811
    client, db = case
    dataset = add_dataset(db)
    material = add_material(db)
    add_stock(db, dataset, material, "50")
    owner = login(client, "SOLICITANTE_OPERACAO")
    request = new_request(client, owner, material, "5")
    # A própria criação não vira notificação.
    assert client.get(NOTIFICATIONS).json() == {"items": [], "unread_count": 0, "next_cursor": None}

    stock = login(client, "ALMOXARIFADO")
    assert reserve(client, stock, request, "5").status_code == 201
    # Outro usuário não vê as notificações do dono.
    assert client.get(NOTIFICATIONS).json()["unread_count"] == 0

    owner = login(client, "SOLICITANTE_OPERACAO")
    listed = client.get(NOTIFICATIONS).json()
    assert listed["unread_count"] == 1
    [item] = listed["items"]
    assert item["action"] == "STOCK_RESERVED" and item["request_id"] == request["id"]
    assert item["protocol"] == request["protocol"] and item["read"] is False

    marked = client.post(f"{NOTIFICATIONS}/read", json={"ids": [item["id"]]}, headers=headers(owner))
    assert marked.status_code == 200, marked.text
    assert marked.json()["unread_count"] == 0 and marked.json()["items"][0]["read"] is True
    assert client.get(NOTIFICATIONS, params={"unread": True}).json()["items"] == []
    # Repetir não duplica nem falha.
    again = client.post(f"{NOTIFICATIONS}/read", json={"all": True}, headers=headers(owner))
    assert again.status_code == 200 and again.json()["unread_count"] == 0
