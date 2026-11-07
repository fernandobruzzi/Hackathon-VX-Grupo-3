"""Nível de revisão de cada correção, conforme a decisão da #36.

Elegibilidade automática é uma política separada (#224).

- Nível 1: grafia da mesma unidade, com classe confiável e sem pendência de unidade.
- Nível 2: descrição ou grupo no padrão do PDM, com classe confiável, sem pendência e sem perda de texto.
- Nível 3: todo o resto, revisado item a item, com os motivos.

O nível só diz como uma pessoa revisa. Nada é aplicado sem aprovação, nem nos níveis 1 e 2.
A regra mínima de 20 itens por lote fica com quem monta os lotes, a API.
"""

from domain.contracts import FieldCorrection, ReviewLane

UNIT_ALIAS_TIER = 1
PDM_FORMAT_TIER = 2
INDIVIDUAL_TIER = 3

CONFLICT = "CONFLICT"
TEXT_LOSS = "TEXT_LOSS"
UNTRUSTED_CLASS = "UNTRUSTED_CLASS"
UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
NO_CLASS = "SEM_CLASSE"


def lot_key(proposal_type: str, changes: list[FieldCorrection], pdm_class_id: str | None) -> str:
    rules = "+".join(sorted({change.rule for change in changes}))
    return f"{proposal_type}|{rules}|{pdm_class_id or NO_CLASS}"


def assign_lane(
    proposal_type: str,
    changes: list[FieldCorrection],
    pending: tuple[str, ...],
    pdm_class_id: str | None,
    lost_terms: tuple[str, ...] = (),
) -> ReviewLane:
    """`pending` são as pendências do material que valem para este tipo de proposta."""
    reasons: list[str] = []
    if proposal_type == "UNIT_CORRECTION":
        tier = UNIT_ALIAS_TIER
        # Sem classe confirmada, a correção de unidade usa a regra própria `unit.alias_without_class`.
        if pdm_class_id is None or any("alias_without_class" in change.rule for change in changes):
            reasons.append(UNTRUSTED_CLASS)
    elif proposal_type == "PDM_CORRECTION":
        tier = PDM_FORMAT_TIER
        if pdm_class_id is None:
            reasons.append(UNTRUSTED_CLASS)
        if lost_terms:
            reasons.append(TEXT_LOSS)
    else:
        tier = INDIVIDUAL_TIER
        reasons.append(UNSUPPORTED_TYPE)
    if pending:
        reasons.append(CONFLICT)
    return ReviewLane(
        INDIVIDUAL_TIER if reasons else tier,
        lot_key(proposal_type, changes, pdm_class_id),
        tuple(reasons),
    )
