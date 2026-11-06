"""Passo explícito não suportado permanece pendente no chat e no batch."""

from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401

from pipelines.import_orders import OrderRow, analyze_order
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository


def test_unknown_metric_pitch_does_not_release_identity(client, catalog):  # noqa: F811
    text = "PARAFUSO SEXTAVADO M12X1,75X50 8.8 ACO CARBONO ZINCADO BRANCO DIN 933"
    card = run(client, text).json()["material_card"]
    batch = analyze_order(
        OrderRow("test", text, None, None, None),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    assert not card["can_submit"]
    assert card["attributes"]["COMPRIMENTO"] is None
    assert "COMPRIMENTO" in card["missing_attributes"]
    assert batch.identity_key is None
    assert "COMPRIMENTO" in batch.missing_attributes
