"""O chat pede a qualificação ausente em vez de completá-la pelo PDM (#133)."""

from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401

VALVE = (
    "VALVULA BORBOLETA; DIAM:DN 50; TIPO CORPO:WAFER; MATERIAL CORPO:FERRO FUNDIDO; MATERIAL DISCO:CF8M; PTFE; MANOPLA"
)


def test_cast_iron_body_without_nodular_evidence_stays_missing_in_the_chat_card(client):  # noqa: F811
    response = run(client, VALVE)

    assert response.status_code == 200
    card = response.json()["material_card"]
    assert card["pdm_class_id"] == "PDM044"
    assert card["validation_status"] == "INCOMPLETE"
    assert card["attributes"]["MATERIAL CORPO"] is None
    assert "MATERIAL CORPO" in card["missing_attributes"]
    assert card["can_submit"] is False


def test_explicit_nodular_confirmation_fills_the_chat_card(client):  # noqa: F811
    response = run(client, VALVE.replace("FERRO FUNDIDO;", "FERRO FUNDIDO NODULAR;"))

    assert response.status_code == 200
    card = response.json()["material_card"]
    assert card["attributes"]["MATERIAL CORPO"] == "FERRO FUNDIDO NODULAR"
    assert "MATERIAL CORPO" not in card["missing_attributes"]
