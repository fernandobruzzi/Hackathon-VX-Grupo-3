"""Passo explícito não suportado permanece pendente no chat e no batch."""

import pytest
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


@pytest.mark.parametrize("pitch,expected", [("1,75", None), ("1,5", "M12X1,5")])
def test_labeled_spaced_metric_pitch_does_not_become_coarse(client, catalog, pitch, expected):  # noqa: F811
    text = (
        f"PARAFUSO SEXTAVADO; BITOLA: M12 X {pitch} X 50; COMPRIMENTO: 50MM; CLASSE: 8.8; "
        "MATERIAL: ACO CARBONO; ACABAMENTO: ZINCADO BRANCO; NORMA: DIN 933"
    )
    card = run(client, text).json()["material_card"]
    batch = analyze_order(
        OrderRow("labeled-pitch-150", text, None, None, None),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    assert card["attributes"]["BITOLA"] == expected
    assert batch.attributes.get("BITOLA") == expected
    assert card["attributes"]["ROSCA"] == ("METRICA FINA" if expected else None)
    if expected is None:
        assert batch.identity_key is None
        assert not card["can_submit"]
    else:
        assert batch.identity_key is not None
