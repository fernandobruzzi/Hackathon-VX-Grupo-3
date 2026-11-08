"""Decisão de duplicidade no chat a partir do resultado de search_similar_materials.

- Item com a mesma identidade pela regra do PDM: mostra o código a usar.
- Só itens parecidos: pergunta ao solicitante se o item dele é um deles, sem liberar o envio.
- O solicitante escolhe um código oferecido: vira o item existente.
- O solicitante diz que é outro item: os códigos oferecidos ficam descartados. Se a ficha mudar e
  aparecerem candidatos novos, pergunta de novo.

Os botões do front enviam uma ação estruturada (`ChatAction`), independente do texto exibido. Texto
digitado continua aceito como alternativa, lido de forma determinística: só frases fixas e variações
óbvias.

A escolha fica salva na conversa: enquanto a ficha não muda, o turno reaproveita a última verificação
aceita pela API, sem nova busca.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from domain.identity import identity_signature
from vx_materials_mcp.schemas.agent import (
    ChatAction,
    DuplicateCheckState,
    ExistingMatch,
    InventoryRow,
    SimilarCandidate,
)

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


def card_signature(pdm_class_id: str | None, attributes: dict[str, str | None], item_name: str | None = None) -> str:
    """Classe, nome efetivo e atributos da ficha; a API usa o mesmo helper de domínio."""
    return identity_signature(pdm_class_id, item_name, attributes)


def wanted_code(action: ChatAction | None, message: str) -> str | None:
    if action is not None:
        return action.material_code if action.type == "PICK_CANDIDATE" else None
    return picked_code(message)


def wants_dismissal(action: ChatAction | None, message: str) -> bool:
    if action is not None:
        return action.type == "DISMISS_CANDIDATES"
    return is_dismissal(message)


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
        reason = (
            "Registro selecionado pelo código informado."
            if item.get("match_type") == "EXACT_MATERIAL_CODE"
            else "Mesmo item pela regra de identidade do PDM."
        )
    if item["status"] == "BLOQUEADO":
        reason = f"{reason} O código {item['material_code']} está bloqueado: use o código ativo {code}."
    return ExistingMatch(
        material_code=code,
        status="ATIVO",
        pdm_description=item["description"] or "",
        match_type=item["match_type"],
        reason=reason,
        inventory=[
            InventoryRow(
                center_code=row["center_code"],
                center_name=row.get("center_name"),
                quantity=row["quantity"],
                unit=row["unit"] or "",
            )
            for row in item["inventory"]
        ],
    )


def verified_existing(search: dict[str, Any]) -> ExistingMatch | None:
    """Primeiro item com a mesma identidade que pode ser reutilizado."""
    for item in search["candidates"]:
        if (item["identity_verified"] or item.get("match_type") == "EXACT_MATERIAL_CODE") and _code_to_use(item):
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
    # Os itens vão estruturados em similar_candidates, que o front lista com a ação "É este";
    # o texto não concatena códigos e descrições, para a conversa continuar legível.
    found = "1 item parecido" if len(similar) == 1 else f"{len(similar)} itens parecidos"
    return (
        f"Encontrei {found} na base. Se o seu item estiver na lista, escolha “É este” "
        "ou responda com o código. Se nenhum corresponder, responda “Nenhum desses é o meu item”."
    )


def _inventory_message(row: InventoryRow) -> str:
    unit = row.unit
    if unit == "PC":
        try:
            singular = Decimal(row.quantity) == 1
        except InvalidOperation:
            singular = False
        unit = "peça" if singular else "peças"
    center = (row.center_name or "").strip() or row.center_code
    return f"{row.quantity} {unit} no centro {center}"


def existing_message(existing: ExistingMatch) -> str:
    stock = ", ".join(_inventory_message(row) for row in existing.inventory)
    where = f" Estoque nos seus centros: {stock}." if stock else " Sem estoque nos seus centros."
    return f"Esse item já existe: use o código {existing.material_code}. {existing.reason}{where}"


def _pending_or_clear(similar: list[SimilarCandidate], dismissed: list[str]) -> DuplicateDecision:
    if similar:
        return DuplicateDecision(
            "PENDING",
            similar=similar,
            offered=[item.material_code for item in similar],
            dismissed=dismissed,
            message=_ask(similar),
        )
    return DuplicateDecision("NO_MATCH", dismissed=dismissed)


def decide(
    search: dict[str, Any] | None,
    message: str,
    offered_before: list[str],
    dismissed_before: list[str],
    action: ChatAction | None = None,
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
    code = wanted_code(action, message)
    if code and code in offered_before:
        chosen = next((item for item in reusable if code in (item["material_code"], _code_to_use(item))), None)
        if chosen is not None:
            existing = existing_from(chosen, "Confirmado pelo solicitante como o mesmo item.")
            return DuplicateDecision("MATCH_FOUND", existing=existing, dismissed=dismissed)
    if wants_dismissal(action, message):
        dismissed += [code for code in offered_before if code not in dismissed]

    pending = [_similar(item) for item in reusable if item["material_code"] not in dismissed]
    return _pending_or_clear(pending, dismissed)


def reuse(
    previous: DuplicateCheckState,
    message: str,
    offered_before: list[str],
    dismissed_before: list[str],
    action: ChatAction | None = None,
) -> DuplicateDecision:
    """Decide sem nova busca, a partir da última verificação aceita para a mesma ficha."""
    dismissed = list(dismissed_before)
    if previous.existing is not None:
        return DuplicateDecision("MATCH_FOUND", existing=previous.existing, dismissed=dismissed)
    if wants_dismissal(action, message):
        dismissed += [code for code in offered_before if code not in dismissed]
    pending = [item for item in previous.similar_candidates if item.material_code not in dismissed]
    return _pending_or_clear(pending, dismissed)


def needs_search(previous: DuplicateCheckState | None, signature: str, action: ChatAction | None, message: str) -> bool:
    """Busca de novo quando a ficha mudou, ou para trazer estoque e detalhes do item escolhido."""
    if previous is None or previous.signature != signature:
        return True
    return previous.existing is None and wanted_code(action, message) is not None
