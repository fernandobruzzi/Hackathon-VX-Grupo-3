"""Rótulo em frase livre preserva os atributos seguintes em chat e batch."""

import pytest
from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401

from pipelines.import_orders import OrderRow, analyze_order
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository


@pytest.mark.parametrize("finish", ["ZINCADO BRANCO", "GALVANIZADO A FOGO"])
def test_strength_label_leaves_material_finish_and_standard_for_chat_and_batch(client, catalog, finish):  # noqa: F811
    text = f"parafuso sextavado M12 x 50 classe 8.8 aco carbono {finish} DIN 933."
    card = run(client, text).json()["material_card"]
    batch = analyze_order(
        OrderRow("test", text, None, None, None),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    for name, value in {
        "CLASSE RESISTENCIA": "8.8",
        "MATERIAL": "ACO CARBONO",
        "ACABAMENTO": finish,
        "NORMA": "DIN 933",
    }.items():
        assert card["attributes"][name] == batch.attributes[name] == value
    assert batch.identity_key is not None
    assert card["validation_status"] == "VALID"
