"""Propostas de correção de um material: descrição e grupo pelo PDM, e unidade pela normalização.

Cada tipo vira uma proposta separada, para ser aprovada ou rejeitada sem depender do outro.
Toda mudança leva o valor original, o novo e a regra aplicada. Nada é aplicado aqui.
"""

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable

from domain.contracts import (
    AnalyzedMaterial,
    CorrectionRepository,
    CorrectionResult,
    FieldCorrection,
    MergeProposal,
    NormalizationRepository,
    PdmCatalog,
    ReviewLane,
    TextLossRepository,
)
from domain.proposal_validation import approval_blockers
from domain.review_lanes import CONFLICT, INDIVIDUAL_TIER, assign_lane
from repositories.text_loss import get_text_loss_repository

_NAMESPACE = uuid.UUID("6b8f3e21-2c4d-4a9e-b1f7-93d05c8a7e14")
PROPOSAL_TYPES = ("PDM_CORRECTION", "UNIT_CORRECTION")
# Pendência do material que impede cada tipo de correção. Uma descrição fora do padrão não
# impede corrigir a grafia da unidade, e uma embalagem sem fator não impede corrigir a descrição.
# Motivo fora desta tabela vale para todos os tipos, por cautela.
_PENDING_SCOPE = {
    "CLASSE_NAO_CONFIRMADA": ("PDM_CORRECTION",),
    "DESCRICAO_FORA_DO_PADRAO": ("PDM_CORRECTION",),
    "SEM_CLASSE_CONFIAVEL": ("PDM_CORRECTION",),
    "UNIDADE_AUSENTE": ("UNIT_CORRECTION",),
    "UNIDADE_DIFERENTE_DA_CLASSE": ("UNIT_CORRECTION",),
    "UNIDADE_SEM_FATOR": ("UNIT_CORRECTION",),
}


def pending_for(proposal_type: str, pending: tuple[str, ...]) -> tuple[str, ...]:
    """Só as pendências que dizem respeito a este tipo de proposta."""
    return tuple(
        reason for reason in pending if proposal_type in _PENDING_SCOPE.get(reason.split(":")[0], PROPOSAL_TYPES)
    )


def _member(material: AnalyzedMaterial) -> dict:
    record = material.record
    return {
        "material_code": record.code,
        "observed_version": record.version,
        "status": record.status,
        "description": record.description,
        "merchandise_group": record.group or None,
        "unit": record.unit,
        "ncm": record.ncm or None,
        "value_brl": record.total_value,
        "inventory": list(record.inventory),
        "attributes": material.attributes,
        "pdm_class_id": material.pdm_class_id,
        "item_name": material.item_name,
    }


def build_correction_proposal(
    material: AnalyzedMaterial,
    proposal_type: str,
    changes: list[FieldCorrection],
    pending: tuple[str, ...],
    catalog: PdmCatalog,
    repository_name: str,
    lane: ReviewLane | None = None,
) -> MergeProposal:
    record = material.record
    after = {"description": record.description, "merchandise_group": record.group or None, "unit": record.unit}
    after.update({change.field: change.after for change in changes})
    conflicts = list(pending)
    if proposal_type == "PDM_CORRECTION":
        # A aprovação publica a identidade PDM com a unidade atual: o batch aplica a mesma validação.
        candidate = {
            "pdm_class_id": material.pdm_class_id,
            "item_name": material.item_name,
            "attributes": material.attributes,
            "unit": after["unit"],
        }
        conflicts.extend(approval_blockers(catalog, candidate))
    changeset = {
        "correction_repository": repository_name,
        "pdm_class_id": material.pdm_class_id,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "item_name": material.item_name,
        "material_code": record.code,
        "changes": [
            {"field": change.field, "before": change.before, "after": change.after, "source": change.rule}
            for change in changes
        ],
        "after": {**after, "ncm": record.ncm or None, "attributes": material.attributes},
        "conflicts": conflicts,
    }
    if lane is not None and conflicts and lane.tier != INDIVIDUAL_TIER:
        # Bloqueios da aprovação também são conflito: a proposta nunca entra em lote.
        lane = ReviewLane(INDIVIDUAL_TIER, lane.lot_key, (*lane.reasons, CONFLICT))
    if lane is not None:
        changeset["review_lane"] = {"tier": lane.tier, "lot_key": lane.lot_key, "reasons": list(lane.reasons)}
    payload = json.dumps(changeset, sort_keys=True, ensure_ascii=False)
    return MergeProposal(
        # Id por material, tipo e versão do PDM: repetir o batch não duplica a proposta.
        id=str(uuid.uuid5(_NAMESPACE, f"{catalog.version}|{proposal_type}|{record.code}")),
        proposal_type=proposal_type,
        material_codes=(record.code,),
        suggested_primary_code=record.code,
        members=(_member(material),),
        changeset=changeset,
        changeset_hash=hashlib.sha256(payload.encode()).hexdigest(),
        conflicts=tuple(conflicts),
        # NCM não muda aqui; correções fiscais são NCM_CORRECTION, com revisão fiscal.
        fiscal_review_required=False,
        ranking_score=float(len(changes)),
    )


def correction_proposals(
    material: AnalyzedMaterial,
    result: CorrectionResult,
    catalog: PdmCatalog,
    repository_name: str,
    text_loss: TextLossRepository | None = None,
) -> list[MergeProposal]:
    proposals = []
    for proposal_type in PROPOSAL_TYPES:
        changes = [change for change in result.corrections if change.proposal_type == proposal_type]
        if changes:
            pending = pending_for(proposal_type, result.pending)
            lane = None
            if text_loss is not None:
                lane = assign_lane(
                    proposal_type,
                    changes,
                    pending,
                    material.pdm_class_id,
                    _lost_terms(material, changes, catalog, text_loss),
                )
            proposals.append(
                build_correction_proposal(material, proposal_type, changes, pending, catalog, repository_name, lane)
            )
    return proposals


def _lost_terms(
    material: AnalyzedMaterial, changes: list[FieldCorrection], catalog: PdmCatalog, text_loss: TextLossRepository
) -> tuple[str, ...]:
    description = next((change.after for change in changes if change.field == "description"), None)
    if description is None or material.pdm_class_id is None:
        return ()
    return text_loss.lost_terms(material, catalog.classes[material.pdm_class_id], description)


def propose_corrections(
    analyzed: Iterable[AnalyzedMaterial],
    catalog: PdmCatalog,
    normalizer: NormalizationRepository,
    corrector: CorrectionRepository,
    pending_by_code: dict[str, tuple[str, ...]] | None = None,
    text_loss: TextLossRepository | None = None,
) -> tuple[list[MergeProposal], Counter[str]]:
    """Devolve as propostas e a contagem de pendências por motivo, que ficam sem correção automática.

    `pending_by_code`, quando informado, recebe os motivos de cada material, para a cobertura do job.
    Cada proposta sai com o nível de revisão (`review_lane`), usando a regra de perda de texto ativa.
    """
    text_loss = text_loss or get_text_loss_repository()
    proposals: list[MergeProposal] = []
    pending: Counter[str] = Counter()
    for material in analyzed:
        result = corrector.correct(material, catalog, normalizer)
        reasons = tuple(dict.fromkeys(reason.split(":")[0] for reason in result.pending))
        pending.update(reasons)
        if pending_by_code is not None and reasons:
            pending_by_code[material.record.code] = reasons
        proposals.extend(correction_proposals(material, result, catalog, corrector.name, text_loss))
    return sorted(proposals, key=lambda p: (p.proposal_type, p.material_codes)), pending


def summarize_corrections(proposals: list[MergeProposal], pending: Counter[str]) -> dict:
    fields: Counter[str] = Counter()
    for proposal in proposals:
        fields.update(change["field"] for change in proposal.changeset["changes"])
    return {
        "proposals": dict(sorted(Counter(p.proposal_type for p in proposals).items())),
        "materials": len({code for p in proposals for code in p.material_codes}),
        "changes": dict(sorted(fields.items())),
        "pending": dict(pending.most_common()),
        "review_lanes": summarize_review_lanes(proposals),
    }


LOT_MIN_SIZE = 20


def summarize_review_lanes(proposals: list[MergeProposal]) -> dict:
    """Propostas por nível e por motivo, e os lotes que a API pode montar (nível 1 ou 2, 20 ou mais)."""
    tiers: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    lots: Counter[tuple[int, str]] = Counter()
    for proposal in proposals:
        lane = proposal.changeset.get("review_lane")
        if lane is None:
            continue
        tiers[str(lane["tier"])] += 1
        reasons.update(lane["reasons"])
        if lane["tier"] in (1, 2):
            lots[(lane["tier"], lane["lot_key"])] += 1
    eligible = {key: size for key, size in lots.items() if size >= LOT_MIN_SIZE}
    return {
        "tiers": dict(sorted(tiers.items())),
        "reasons": dict(reasons.most_common()),
        "lots": len(lots),
        "lots_min_size": LOT_MIN_SIZE,
        "eligible_lots": len(eligible),
        "proposals_in_eligible_lots": sum(eligible.values()),
    }
