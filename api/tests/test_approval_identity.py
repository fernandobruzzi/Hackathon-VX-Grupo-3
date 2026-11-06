"""A aprovação não confia em PN coincidente diante de evidência contraditória."""

import copy

import pytest
from approval_fixtures import decide, persist
from sqlalchemy import func, select

from vx_materials_api.db.models import AuditLog, InventoryConsolidation


@pytest.mark.parametrize(
    "contradiction",
    ["interpretation", "original_description", "revision", "suffix", "text_reference", "ambiguous_noun"],
)
def test_same_reference_cannot_override_piece_evidence(approval_case, contradiction):
    case = approval_case
    if contradiction == "interpretation":
        members = copy.deepcopy(case["proposal"].members)
        members[1]["item_name"] = "FILTRO AR"
        case["proposal"].members = members
    elif contradiction == "original_description":
        case["materials"][1].original_description_long = "FILTRO AR FLEETGUARD LF9009"
    elif contradiction == "revision":
        case["materials"][1].original_description_long = "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009 REV A"
    elif contradiction == "suffix":
        case["materials"][1].manufacturer_reference = "LF9009-00"
    elif contradiction == "text_reference":
        case["materials"][1].original_description_long = "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9999"
    else:
        case["materials"][1].original_description_long = "FILTRO AR FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009"
    persist(case)

    response = decide(case)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "IDENTITY_REVIEW_REQUIRED"
    case["session"].expire_all()
    assert case["proposal"].status == "PENDING"
    assert all(m.status == "ATIVO" and m.version == 1 for m in case["materials"])
    assert case["session"].scalar(select(func.count()).select_from(InventoryConsolidation)) == 0
    assert case["session"].scalar(select(func.count()).select_from(AuditLog)) == 0
