import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.proposals import proposal_hash
from vx_materials_api.schemas.proposals import MemberInterpretation, ProposalChangeset, UnitConversion

FIXTURE = Path(__file__).parents[1] / "contracts/fixtures/approval-proposal.json"


def test_persisted_fixture_matches_the_consumer_contract():
    data = json.loads(FIXTURE.read_text())
    for member in data["members"]:
        MemberInterpretation.model_validate_json(json.dumps(member))
    ProposalChangeset.model_validate_json(json.dumps(data["changeset"]))


def test_hash_binds_member_versions_attributes_and_evidence_but_not_dict_order():
    data = json.loads(FIXTURE.read_text())
    original = proposal_hash(data["members"], data["changeset"], [])
    reordered = [{key: value for key, value in reversed(list(member.items()))} for member in data["members"]]
    assert proposal_hash(reordered, data["changeset"], []) == original
    changed = copy.deepcopy(data)
    changed["members"][0]["expected_version"] += 1
    assert proposal_hash(changed["members"], changed["changeset"], []) != original
    changed = copy.deepcopy(data)
    changed["changeset"]["after"]["attributes"]["REFERENCIA FABRICANTE"] = "OTHER"
    assert proposal_hash(changed["members"], changed["changeset"], []) != original
    assert proposal_hash(data["members"], data["changeset"], ["different-evidence"]) != original


@pytest.mark.parametrize("factor", ["0", "-1", "NaN", "Infinity", "1,5", "1e4", "9" * 65])
def test_unknown_or_nonpositive_factors_are_not_accepted(factor):
    with pytest.raises(ValidationError):
        UnitConversion(from_unit="CX", to_unit="PC", factor=factor, source="Fonte da embalagem")
