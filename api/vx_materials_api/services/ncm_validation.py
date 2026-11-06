"""Reavalia a base fiscal do conteúdo persistido antes de cada aprovação."""

from dataclasses import asdict

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.ncm_rules import check_ncm_consistency
from domain.ncm_snapshot import NcmSnapshotError
from domain.proposals import canonical_hash
from vx_materials_api.errors import ApiError


def evaluate_proposed_ncm(catalog, changes, *, require_consistency=True):
    try:
        snapshot = load_configured_ncm_snapshot()
    except NcmSnapshotError as error:
        raise ApiError(
            409, "NCM_REFERENCE_UNAVAILABLE", "A referencia fiscal configurada esta indisponivel."
        ) from error
    if snapshot is not None and changes.ncm_assessment is None:
        raise ApiError(409, "NCM_ASSESSMENT_CHANGED", "A base fiscal mudou. Gere e revise uma nova proposta.")
    result = asdict(
        check_ncm_consistency(
            catalog,
            changes.after.pdm_class_id,
            changes.after.attributes,
            changes.after.ncm,
            item_name=changes.after.item_name,
            snapshot=snapshot,
        )
    )
    if changes.ncm_assessment is not None and canonical_hash(changes.ncm_assessment) != canonical_hash(result):
        raise ApiError(409, "NCM_ASSESSMENT_CHANGED", "A base fiscal mudou. Gere e revise uma nova proposta.")
    if require_consistency and changes.after.ncm is not None and result["technical_consistency"] != "CONSISTENT":
        raise ApiError(422, "NCM_REFERENCE_MISMATCH", "NCM nao atende as condicoes da classe e dos atributos PDM.")
    return result
