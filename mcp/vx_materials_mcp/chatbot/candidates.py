"""Decisão de duplicidade no chat a partir do resultado de search_similar_materials.

- Item com a mesma identidade pela regra do PDM: mostra o código a usar.
- Só itens parecidos: pergunta ao solicitante se o item dele é um deles, sem liberar o envio.
- O solicitante escolhe um código oferecido: vira o item existente.
- O solicitante diz que é outro item: os códigos oferecidos ficam descartados. Se a ficha mudar e
  aparecerem candidatos novos, pergunta de novo.

As respostas do solicitante são lidas de forma determinística: o front envia frases fixas pelos
botões, e só variações óbvias do texto são aceitas.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from vx_materials_mcp.schemas.agent import ExistingMatch, InventoryRow, SimilarCandidate

DISMISS_MESSAGE = "Nenhum desses é o meu item"
PICK_PREFIX = "É o item"
_DISMISSALS = {
    "nenhum desses e o meu item",
    "nenhum desses",
    "nenhum deles",
    "nao e nenhum desses",
    "nao e nenhum deles",
    "e outro item",
    "e um item diferente",
    "item diferente",
    "outro item",
}
_PICK = re.compile(r"^(?:e o item|e o codigo|e o|codigo|item)?\s*(\d{5,})$")


def _normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", plain).split())


def is_dismissal(text: str) -> bool:
    return _normalize(text) in _DISMISSALS


def picked_code(text: str) -> str | None:
    match = _PICK.match(_normalize(text))
    return match.group(1) if match else None


def is_reply_to_candidates(text: str) -> bool:
    """Respostas aos candidatos não descrevem o item: ficam fora da classificação e da busca."""
    return is_dismissal(text) or picked_code(text) is not None


def _code_to_use(item: dict[str, Any]) -> str | None:
    """Ativo pelo próprio código; bloqueado pelo código ativo de destino; obsoleto nunca."""
    if item["status"] == "ATIVO":
        return item["material_code"]
    if item["status"] == "BLOQUEADO" and item["active_code_target"]:
        return item["active_code_target"]
    return None


def existing_from(item: dict[str, Any], reason: str | None = None) -> ExistingMatch:
    code = _code_to_use(item)
    if reason is None:
        reason = "Mesmo item pela regra de identidade do PDM."
    if item["status"] == "BLOQUEADO":
        reason = f"{reason} O código {item['material_code']} está bloqueado: use o código ativo {code}."
    return ExistingMatch(
        material_code=code,
        status="ATIVO",
        pdm_description=item["description"] or "",
        match_type=item["match_type"],
        reason=reason,
        inventory=[
            InventoryRow(center_code=row["center_code"], quantity=row["quantity"], unit=row["unit"] or "")
            for row in item["inventory"]
        ],
    )


def verified_existing(search: dict[str, Any]) -> ExistingMatch | None:
    """Primeiro item com a mesma identidade que pode ser reutilizado."""
    for item in search["candidates"]:
        if item["identity_verified"] and _code_to_use(item):
            return existing_from(item)
    return None


@dataclass
class DuplicateDecision:
    status: str  # PENDING, NO_MATCH ou MATCH_FOUND
    existing: ExistingMatch | None = None
    similar: list[SimilarCandidate] = field(default_factory=list)
    offered: list[str] = field(default_factory=list)
    dismissed: list[str] = field(default_factory=list)
    message: str = ""


def _similar(item: dict[str, Any]) -> SimilarCandidate:
    return SimilarCandidate(
        material_code=item["material_code"],
        status=item["status"],
        pdm_description=item["description"] or "",
        active_code_target=item["active_code_target"],
    )


def _ask(similar: list[SimilarCandidate]) -> str:
    listed = "; ".join(
        f"{item.material_code} ({item.pdm_description})"
        + (f", bloqueado: use {item.active_code_target}" if item.status == "BLOQUEADO" else "")
        for item in similar
    )
    return (
        f"Encontrei itens parecidos na base: {listed}. "
        "O seu item é um desses? Responda com o código, ou diga que é um item diferente."
    )


def existing_message(existing: ExistingMatch) -> str:
    stock = ", ".join(f"{row.quantity} {row.unit} no centro {row.center_code}".strip() for row in existing.inventory)
    where = f" Estoque nos seus centros: {stock}." if stock else " Sem estoque nos seus centros."
    return f"Esse item já existe: use o código {existing.material_code}. {existing.reason}{where}"


def decide(
    search: dict[str, Any] | None, message: str, offered_before: list[str], dismissed_before: list[str]
) -> DuplicateDecision:
    dismissed = list(dismissed_before)
    if search is None:
        # Sem a verificação, o pedido nunca fica pronto: juntar itens diferentes custa mais que esperar.
        return DuplicateDecision(
            "PENDING",
            dismissed=dismissed,
            message="Não consegui verificar se o item já existe na base: tente enviar de novo em instantes.",
        )
    existing = verified_existing(search)
    if existing is not None:
        return DuplicateDecision("MATCH_FOUND", existing=existing, dismissed=dismissed)

    reusable = [item for item in search["candidates"] if not item["identity_verified"] and _code_to_use(item)]
    code = picked_code(message)
    if code and code in offered_before:
        chosen = next((item for item in reusable if code in (item["material_code"], _code_to_use(item))), None)
        if chosen is not None:
            existing = existing_from(chosen, "Confirmado pelo solicitante como o mesmo item.")
            return DuplicateDecision("MATCH_FOUND", existing=existing, dismissed=dismissed)
    if is_dismissal(message):
        dismissed += [code for code in offered_before if code not in dismissed]

    pending = [item for item in reusable if item["material_code"] not in dismissed]
    if pending:
        similar = [_similar(item) for item in pending]
        return DuplicateDecision(
            "PENDING",
            similar=similar,
            offered=[item.material_code for item in similar],
            dismissed=dismissed,
            message=_ask(similar),
        )
    return DuplicateDecision("NO_MATCH", dismissed=dismissed)
