"""Propostas fiscais rastreáveis, sem alteração do registro original."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.contracts import AnalyzedMaterial, MaterialRecord
from domain.pdm_formatter import format_description
from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from domain.proposals import canonical_hash
from pipelines.ncm_corrections import propose_ncm_corrections
from repositories.proposal_payload import approval_payload


@pytest.fixture(scope="module")
def context():
    catalog = load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    cls = catalog.classes["PDM003"]
    attributes = {a.name: a.allowed_values[0] for a in cls.attributes if a.required}
    item = cls.item_names[0]
    record = MaterialRecord("nut", "ATIVO", format_description(cls, item, attributes), unit="PC", ncm="7318.15.00")
    validation = validate_pdm(catalog, cls.id, attributes, item_name=item)
    assert validation.can_submit
    return catalog, AnalyzedMaterial(record, cls.id, item, attributes, validation.identity_key)


def test_nut_proposal_preserves_original_and_pins_both_assessments(context):
    catalog, material = context
    proposal = propose_ncm_corrections([material], catalog)[0]
    assert proposal.proposal_type == "NCM_CORRECTION"
    assert proposal.fiscal_review_required
    assert proposal.members[0]["ncm"] == material.record.ncm == "7318.15.00"
    assert proposal.changeset["after"]["ncm"] == "7318.16.00"
    assert proposal.changeset["ncm_before_assessment"]["technical_consistency"] == "INCONSISTENT"
    assert proposal.changeset["ncm_assessment"]["technical_consistency"] == "CONSISTENT"
    assert proposal.changeset["ncm_assessment"]["exists_in_snapshot"] is None
    assert proposal.changeset_hash == canonical_hash(proposal.changeset)
    assert propose_ncm_corrections([material], catalog) == [proposal]


def test_approval_payload_binds_assessment_and_does_not_treat_ncm_as_unsupported(context):
    catalog, material = context
    proposal = propose_ncm_corrections([material], catalog)[0]
    members, changes, digest = approval_payload(
        proposal, {"nut": "00000000-0000-0000-0000-000000000001"}, "00000000-0000-0000-0000-000000000002"
    )
    assert changes["ncm_assessment"]["pdm_source_sha256"] == catalog.source_sha256
    assert not changes["conflicts"]
    assert changes["after"]["ncm"] == "7318.16.00"
    assert members[0]["attributes"] == material.attributes
    assert len(digest) == 64


@pytest.mark.parametrize("change", ["incomplete", "already_correct", "class_not_confirmed"])
def test_unsafe_or_unnecessary_ncm_changes_are_not_proposed(context, change):
    catalog, original = context
    material = original
    if change == "incomplete":
        material = replace(original, attributes={})
    elif change == "already_correct":
        material = replace(original, record=replace(original.record, ncm="7318.16.00"))
    else:
        material = replace(original, record=replace(original.record, description="FILTRO COM PORCA"))
    assert propose_ncm_corrections([material], catalog) == []


@pytest.mark.parametrize("status", ["BLOQUEADO", "OBSOLETO"])
def test_ncm_is_proposed_in_any_status_with_fiscal_review(context, status):
    # NCM é dado fiscal do item; bloqueado e obsoleto também precisam do código certo.
    catalog, original = context
    material = replace(original, record=replace(original.record, status=status))
    proposal = propose_ncm_corrections([material], catalog)[0]
    assert proposal.changeset["after"]["ncm"] == "7318.16.00"
    assert proposal.fiscal_review_required
