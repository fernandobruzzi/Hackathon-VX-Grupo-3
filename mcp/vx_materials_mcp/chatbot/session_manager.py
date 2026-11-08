"""Reconstrução do contexto multi-turn a partir do que a API envia.

O contrato interno não carrega a classe identificada, então ela é recalculada a cada turno a partir
das mensagens do usuário: a mais recente que identifica uma classe vence. Atributos confirmados em
turnos anteriores valem até o usuário informar outro valor.
"""

from dataclasses import dataclass, replace

from domain.contracts import (
    ClassificationInput,
    ClassificationRepository,
    ClassificationResult,
    ClassificationStatus,
    ExtractionRepository,
    PdmClass,
)
from domain.identity import reference_revision_evidence, resolve_item_name
from vx_materials_mcp.chatbot.candidates import is_reply_to_candidates
from vx_materials_mcp.schemas.agent import AgentRunRequest


@dataclass(frozen=True)
class TurnContext:
    classification: ClassificationResult
    pdm_class: PdmClass | None
    item_name: str | None
    attributes: dict[str, str | None]
    # Nomes do PDM das classes candidatas, para perguntar o tipo quando a classe ficou em dúvida.
    candidate_names: tuple[str, ...] = ()
    # Bedrock busca apenas os fatos aceitos; regras locais mantêm a consulta original.
    search_text: str | None = None


def user_messages(request: AgentRunRequest) -> list[str]:
    """Mensagens do usuário que descrevem o item, em ordem.

    Respostas aos candidatos ("É o item 123", "Nenhum desses é o meu item") ficam de fora, para a
    busca do turno repetir a anterior e reencontrar os códigos oferecidos.
    """
    texts = [message.content for message in request.context.history if message.author == "user"]
    # Mensagem de botão não descreve o item, qualquer que seja o texto exibido.
    current = [] if request.action is not None else [request.message]
    described = [text for text in [*texts, *current] if not is_reply_to_candidates(text)]
    return described or [request.message]


def _classify(messages: list[str], classifier: ClassificationRepository) -> ClassificationResult:
    results = [classifier.classify(ClassificationInput(description=text)) for text in reversed(messages)]
    for result in results:
        if result.status == ClassificationStatus.CLASSIFIED:
            return result
    # Sem classe: mostra o resultado da mensagem atual, com candidatos se houver dúvida.
    return next((r for r in results if r.status == ClassificationStatus.UNRESOLVED), results[0])


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
        names = tuple(
            name
            for class_id in classification.candidate_class_ids
            if class_id in catalog_classes
            for name in catalog_classes[class_id].item_names
        )
        return TurnContext(classification, None, None, dict(request.context.confirmed_attributes), names)

    known = {attribute.name for attribute in pdm_class.attributes}
    attributes = {name: value for name, value in request.context.confirmed_attributes.items() if name in known}
    for text in messages:
        # A extração deixa vazio o que não reconhece com segurança: não apaga valores anteriores.
        extracted = extractor.extract(pdm_class, text).attributes
        attributes.update({name: value.value for name, value in extracted.items()})
    names = (e.matched_name for e in classification.evidence if e.class_id == pdm_class.id)
    return TurnContext(classification, pdm_class, resolve_item_name(pdm_class, names), attributes)


def build_fallback_context(
    request: AgentRunRequest,
    catalog_classes: dict[str, PdmClass],
    classifier: ClassificationRepository,
    extractor: ExtractionRepository,
) -> TurnContext:
    """Mantém o estado aceito sem reintroduzir fatos históricos quando o modelo está indisponível."""
    clean = request.model_copy(
        update={"context": request.context.model_copy(update={"history": [], "confirmed_attributes": {}})}
    )
    current = build_turn_context(clean, catalog_classes, classifier, extractor)
    previous = catalog_classes.get(request.context.pdm_class_id or "")
    changed = current.pdm_class is not None and (
        previous is None
        or current.pdm_class.id != previous.id
        or (current.item_name and request.context.item_name and current.item_name != request.context.item_name)
    )
    if previous and (request.action is not None or not changed):
        known = {attribute.name for attribute in previous.attributes}
        attributes = {name: value for name, value in request.context.confirmed_attributes.items() if name in known}
        if request.action is None and not is_reply_to_candidates(request.message):
            attributes.update(
                {name: value.value for name, value in extractor.extract(previous, request.message).attributes.items()}
            )
        classification = replace(
            current.classification,
            status=ClassificationStatus.CLASSIFIED,
            pdm_class_id=previous.id,
            candidate_class_ids=(),
            evidence=(),
        )
        item_name = request.context.item_name or (previous.item_names[0] if len(previous.item_names) == 1 else None)
        current = TurnContext(classification, previous, item_name, attributes)
    query = " ".join(
        [
            current.item_name or "",
            *(f"{name}: {value}" for name, value in current.attributes.items() if value),
            *reference_revision_evidence(*(user_messages(request) if previous and not changed else [request.message])),
        ]
    ).strip()
    return replace(current, search_text=query if current.pdm_class else request.message)
