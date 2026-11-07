"""O servidor MCP real conserva a referência confirmada quando o solicitante informa a quantidade."""

from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401


def test_quantity_alone_keeps_the_part_reference_missing(client):  # noqa: F811
    card = run(client, "carcaca Caterpillar preciso de 20 unidades").json()["material_card"]
    assert card["pdm_class_id"] == "PDM110"
    assert card["attributes"].get("REFERENCIA FABRICANTE") is None
    assert "REFERENCIA FABRICANTE" in card["missing_attributes"]
    assert card["can_submit"] is False


def test_quantity_followup_never_replaces_the_confirmed_reference(client):  # noqa: F811
    message = "CARCACA Caterpillar, MODELO EQUIPAMENTO: 793F, REF: 123-4567, APLICACAO: CAMINHAO FORA DE ESTRADA"
    first = run(client, message).json()
    confirmed = first["context_patch"]["confirmed_attributes"]
    assert confirmed["REFERENCIA FABRICANTE"] == "123-4567"
    result = run(
        client,
        "preciso de 20 unidades",
        history=[("user", message), ("assistant", first["assistant_message"])],
        confirmed=confirmed,
    ).json()
    assert result["material_card"]["attributes"]["REFERENCIA FABRICANTE"] == "123-4567"
    assert result["context_patch"]["confirmed_attributes"]["REFERENCIA FABRICANTE"] == "123-4567"
