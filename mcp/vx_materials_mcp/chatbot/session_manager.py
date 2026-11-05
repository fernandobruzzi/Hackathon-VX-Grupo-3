"""Reconstrução do contexto multi-turn a partir do que a API envia.

O contrato interno não carrega a classe identificada, então ela é recalculada a cada turno a partir
das mensagens do usuário: a mais recente que identifica uma classe vence. Atributos confirmados em
turnos anteriores valem até o usuário informar outro valor.
"""

from dataclasses import dataclass

from domain.contracts import (
    ClassificationInput,
    ClassificationRepository,
    ClassificationResult,
    ClassificationStatus,
    ExtractionRepository,
    PdmClass,
)
from vx_materials_mcp.schemas.agent import AgentRunRequest


@dataclass(frozen=True)
class TurnContext:
    classification: ClassificationResult
    pdm_class: PdmClass | None
    item_name: str | None
    attributes: dict[str, str | None]


def user_messages(request: AgentRunRequest) -> list[str]:
    """Mensagens do usuário em ordem, terminando na atual."""
    previous = [message.content for message in request.context.history if message.author == "user"]
    return [*previous, request.message]


def _classify(messages: list[str], classifier: ClassificationRepository) -> ClassificationResult:
    results = [classifier.classify(ClassificationInput(description=text)) for text in reversed(messages)]
    for result in results:
        if result.status == ClassificationStatus.CLASSIFIED:
            return result
    # Sem classe: mostra o resultado da mensagem atual, com candidatos se houver dúvida.
    return next((r for r in results if r.status == ClassificationStatus.UNRESOLVED), results[0])


def _item_name(pdm_class: PdmClass, result: ClassificationResult) -> str | None:
    """Classes com vários itens precisam do nome usado na mensagem; as demais dispensam."""
    if len(pdm_class.item_names) <= 1:
        return None
    matched = {evidence.matched_name for evidence in result.evidence if evidence.class_id == pdm_class.id}
    names = [name for name in pdm_class.item_names if name in matched]
    return names[0] if len(names) == 1 else None


def build_turn_context(
    request: AgentRunRequest,
    catalog_classes: dict[str, PdmClass],
    classifier: ClassificationRepository,
    extractor: ExtractionRepository,
) -> TurnContext:
    messages = user_messages(request)
    classification = _classify(messages, classifier)
    pdm_class = catalog_classes.get(classification.pdm_class_id) if classification.pdm_class_id else None
    if pdm_class is None:
        return TurnContext(classification, None, None, dict(request.context.confirmed_attributes))

    known = {attribute.name for attribute in pdm_class.attributes}
    attributes = {name: value for name, value in request.context.confirmed_attributes.items() if name in known}
    for text in messages:
        # A extração deixa vazio o que não reconhece com segurança: não apaga valores anteriores.
        extracted = extractor.extract(pdm_class, text).attributes
        attributes.update({name: value.value for name, value in extracted.items()})
    return TurnContext(classification, pdm_class, _item_name(pdm_class, classification), attributes)
