"""Correções fiscais propostas pelo PDM, nunca aplicadas pelo batch."""

from dataclasses import asdict, replace

from domain.contracts import AnalyzedMaterial, FieldCorrection, MergeProposal, PdmCatalog, ValidationStatus
from domain.ncm_rules import RULES_VERSION, check_ncm_consistency
from domain.pdm_validator import validate_pdm
from domain.proposals import canonical_hash
from pipelines.corrections import build_correction_proposal
from repositories.corrections.head_noun_v1 import opens_description


def propose_ncm_corrections(materials: list[AnalyzedMaterial], catalog: PdmCatalog) -> list[MergeProposal]:
    proposals = []
    for material in materials:
        if material.record.status != "ATIVO" or material.pdm_class_id is None or not material.item_name:
            continue
        if not opens_description(material.item_name, material.record.description):
            continue
        validation = validate_pdm(catalog, material.pdm_class_id, material.attributes, item_name=material.item_name)
        if validation.status is not ValidationStatus.VALID:
            continue
        before = check_ncm_consistency(
            catalog,
            material.pdm_class_id,
            material.attributes,
            material.record.ncm or None,
            item_name=material.item_name,
        )
        if len(before.suggested_ncm_codes) != 1 or "PDM_CONDITION_UNRESOLVED" in before.pending_checks:
            continue
        target = before.suggested_ncm_codes[0]
        if target == material.record.ncm:
            continue
        after = check_ncm_consistency(
            catalog, material.pdm_class_id, material.attributes, target, item_name=material.item_name
        )
        if after.technical_consistency != "CONSISTENT":
            continue
        proposal = build_correction_proposal(
            material,
            "NCM_CORRECTION",
            [
                FieldCorrection(
                    "NCM_CORRECTION",
                    "ncm",
                    material.record.ncm or None,
                    target,
                    f"{RULES_VERSION}/{before.rule_id}; PDM sha256:{catalog.source_sha256}",
                )
            ],
            (),
            catalog,
            RULES_VERSION,
        )
        changes = {
            **proposal.changeset,
            "after": {**proposal.changeset["after"], "ncm": target},
            "ncm_before_assessment": asdict(before),
            "ncm_assessment": asdict(after),
        }
        proposals.append(
            replace(proposal, changeset=changes, changeset_hash=canonical_hash(changes), fiscal_review_required=True)
        )
    return proposals
