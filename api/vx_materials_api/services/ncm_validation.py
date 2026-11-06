"""Reavalia a base fiscal do conteúdo persistido antes de cada aprovação."""

from dataclasses import asdict

from domain.ncm_rules import check_ncm_consistency
from domain.proposals import canonical_hash
from vx_materials_api.errors import ApiError


def evaluate_proposed_ncm(catalog, changes):
    result = asdict(
        check_ncm_consistency(
            catalog,
            changes.after.pdm_class_id,
            changes.after.attributes,
            changes.after.ncm,
            item_name=changes.after.item_name,
        )
    )
    if changes.ncm_assessment is not None and canonical_hash(changes.ncm_assessment) != canonical_hash(result):
        raise ApiError(409, "NCM_ASSESSMENT_CHANGED", "A base fiscal mudou. Gere e revise uma nova proposta.")
    if changes.after.ncm is not None and result["technical_consistency"] != "CONSISTENT":
        raise ApiError(422, "NCM_REFERENCE_MISMATCH", "NCM nao atende as condicoes da classe e dos atributos PDM.")
    return result
