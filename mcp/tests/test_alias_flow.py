"""Aliases técnicos no turno de chat (#86): classificação e extração no mesmo fluxo, com o MCP real."""

from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401

VALVE = 'VALV ESF 2" AISI 316 NPT'
FILTER = "ELEMENTO FILTRANTE FLEETGUARD LF9009"


def test_abbreviated_ball_valve_reaches_the_card_without_guessing_the_body(client):  # noqa: F811
    card = run(client, VALVE).json()["material_card"]

    assert card["pdm_class_id"] == "PDM040"
    assert card["validation_status"] == "INCOMPLETE"
    assert card["attributes"]["DIAMETRO NOMINAL"] == "2POL"
    assert card["attributes"]["CONEXAO"] == "ROSCA NPT"
    # AISI 316 não diz se o corpo é forjado ou fundido: o campo fica para o solicitante.
    assert card["attributes"]["MATERIAL CORPO"] is None
    assert "MATERIAL CORPO" in card["missing_attributes"]


def test_generic_filter_element_asks_for_the_type_instead_of_rejecting(client):  # noqa: F811
    response = run(client, FILTER).json()

    card = response["material_card"]
    assert card["pdm_class_id"] is None
    # Dúvida de classe não é "fora do escopo": o pedido continua aguardando resposta.
    assert card["validation_status"] == "INCOMPLETE"
    assert card["can_submit"] is False
    assert "PDM100" in response["context_patch"]["candidate_class_ids"]
    assert "FILTRO AR" in response["assistant_message"]
    assert "FILTRO OLEO LUBRIFICANTE" in response["assistant_message"]


def test_answering_the_type_classifies_and_keeps_the_reference(client):  # noqa: F811
    first = run(client, FILTER).json()
    history = [("user", FILTER), ("assistant", first["assistant_message"])]

    card = run(client, "é filtro de ar", history).json()["material_card"]

    assert card["pdm_class_id"] == "PDM100"
    assert card["attributes"]["FABRICANTE"] == "FLEETGUARD"
    assert card["attributes"]["REFERENCIA FABRICANTE"] == "LF9009"


def test_unknown_product_still_reports_out_of_scope(client):  # noqa: F811
    assert run(client, "quero uma cadeira de escritório").json()["material_card"]["validation_status"] == "OUT_OF_SCOPE"
