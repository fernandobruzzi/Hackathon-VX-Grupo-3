"""Equivalências em polegadas atravessam chat e batch."""

import pytest
from test_conversation_flow import callers, catalog, client, executed, run  # noqa: F401

from pipelines.import_orders import OrderRow, analyze_order
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository


@pytest.mark.parametrize("decimal,fraction", [("0,5", "1/2"), ("0,25", "1/4"), ("0,75", "3/4")])
def test_decimal_inches_match_fraction_in_chat_and_batch(client, catalog, decimal, fraction):  # noqa: F811
    identities = []
    for size in (decimal, fraction):
        text = f"VALVULA ESFERA {size}POL 150# ACO INOX FUNDIDO A351 CF8M ROSCA NPT PLENA PTFE ALAVANCA"
        card = run(client, text).json()["material_card"]
        batch = analyze_order(
            OrderRow("test", text, None, None, None),
            catalog,
            get_classification_repository(catalog),
            get_extraction_repository(),
        )
        assert card["attributes"]["DIAMETRO NOMINAL"] == f"{fraction}POL"
        assert batch.attributes["DIAMETRO NOMINAL"] == f"{fraction}POL"
        identities.append(batch.identity_key)
    assert identities[0] is not None
    assert identities[0] == identities[1]
