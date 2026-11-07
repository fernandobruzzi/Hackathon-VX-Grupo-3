"""Correções fiscais propostas pelo PDM, nunca aplicadas pelo batch."""

from dataclasses import asdict, replace

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.contracts import AnalyzedMaterial, FieldCorrection, MergeProposal, PdmCatalog
from domain.ncm_rules import (
    PROPOSAL_POLICY_VERSION,
    RULES_VERSION,
    check_ncm_consistency,
    ncm_proposal_blockers,
    requires_snapshot_fiscal_review,
)
from domain.ncm_snapshot import NcmSnapshot
from domain.proposals import canonical_hash
from pipelines.corrections import build_correction_proposal
from repositories.corrections.head_noun_v2 import head_confirmed


def propose_ncm_corrections(
    materials: list[AnalyzedMaterial], catalog: PdmCatalog, *, snapshot: NcmSnapshot | None = None
) -> list[MergeProposal]:
    snapshot = snapshot if snapshot is not None else load_configured_ncm_snapshot()
    proposals = []
    for material in materials:
        # NCM é dado fiscal do item em qualquer status; a aprovação fiscal continua obrigatória.
        if material.pdm_class_id is None or not head_confirmed(material):
            continue
        # Só os atributos que decidem o código são exigidos: a condição não resolvida abaixo
        # barra a proposta, e o código único da classe exige a matéria provada.
        if ncm_proposal_blockers(catalog.classes[material.pdm_class_id], material.attributes, material.item_name):
            continue
        before = check_ncm_consistency(
            catalog,
            material.pdm_class_id,
            material.attributes,
            material.record.ncm or None,
            item_name=material.item_name,
            snapshot=snapshot,
        )
        if len(before.suggested_ncm_codes) != 1 or "PDM_CONDITION_UNRESOLVED" in before.pending_checks:
            continue
        target = before.suggested_ncm_codes[0]
        if target == material.record.ncm:
            continue
        after = check_ncm_consistency(
            catalog, material.pdm_class_id, material.attributes, target, item_name=material.item_name, snapshot=snapshot
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
                    f"{RULES_VERSION}/{before.rule_id}; {PROPOSAL_POLICY_VERSION}; PDM sha256:{catalog.source_sha256}",
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


def bind_snapshot_assessment(proposal: MergeProposal, catalog: PdmCatalog, snapshot: NcmSnapshot) -> MergeProposal:
    """Vincula também merges/correções técnicas à mesma referência fiscal da execução."""
    if proposal.proposal_type == "UNIT_CORRECTION":
        return proposal
    primary = next(m for m in proposal.members if m["material_code"] == proposal.suggested_primary_code)
    after = proposal.changeset["after"]
    result = check_ncm_consistency(
        catalog,
        after.get("pdm_class_id", proposal.changeset.get("pdm_class_id")),
        after["attributes"],
        after.get("ncm", primary.get("ncm")),
        item_name=after.get("item_name", proposal.changeset.get("item_name")),
        snapshot=snapshot,
    )
    changes = {**proposal.changeset, "ncm_assessment": asdict(result)}
    return replace(
        proposal,
        changeset=changes,
        changeset_hash=canonical_hash(changes),
        fiscal_review_required=proposal.fiscal_review_required or requires_snapshot_fiscal_review(asdict(result)),
    )
