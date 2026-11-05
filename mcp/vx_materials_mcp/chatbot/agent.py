"""Ciclo conversacional do agente.

Esta versão planeja o turno por regras, sem LLM: a classificação e a extração vêm dos repositórios
do `back`, e toda validação passa pelas tools MCP reais. Um planejador com LLM pode substituir
`run_turn` sem mudar o contrato, porque os limites e o registro das chamadas ficam em `ToolRecorder`.
"""

import time
from typing import Any, Protocol

from domain.contracts import ClassificationStatus, PdmClass
from vx_materials_mcp.chatbot.session_manager import TurnContext
from vx_materials_mcp.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    MaterialCard,
    NcmCard,
    ToolCallRecord,
)

PLANNER = "rule_based_v1"
MAX_TOOL_CALLS = 5
TURN_TIMEOUT_SECONDS = 20.0


class ToolLimitExceeded(RuntimeError):
    """O turno tentou mais chamadas de tool do que o limite permite."""


class ToolClient(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ToolRecorder:
    """Executa as tools e registra cada chamada como ela aconteceu, para o painel do front."""

    def __init__(self, client: ToolClient, limit: int = MAX_TOOL_CALLS) -> None:
        self._client = client
        self._limit = limit
        self.calls: list[ToolCallRecord] = []

    async def call(self, name: str, arguments: dict[str, Any], summarize) -> dict[str, Any] | None:
        if len(self.calls) >= self._limit:
            raise ToolLimitExceeded(f"Limite de {self._limit} chamadas de tool por turno")
        started = time.perf_counter()
        try:
            result = await self._client.call_tool(name, arguments)
        except Exception as error:  # noqa: BLE001 - a falha vira resultado visível, não erro do turno
            self._record(name, arguments, "FAILED", started, {"error": str(error)})
            return None
        self._record(name, arguments, "SUCCEEDED", started, summarize(result))
        return result

    def _record(self, name, arguments, status, started, result) -> None:
        self.calls.append(
            ToolCallRecord(
                id=f"tool-call-{len(self.calls) + 1:03d}",
                name=name,
                input=arguments,
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                result=result,
            )
        )


def _summarize_template(result: dict[str, Any]) -> dict[str, Any]:
    attributes = result["attributes"]
    return {
        "noun": result["noun"],
        "attributes_count": len(attributes),
        "required_attributes_count": sum(1 for attribute in attributes if attribute["required"]),
    }


def _summarize_validation(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "validation_status": result["status"],
        "missing_attributes": [item["name"] for item in result["missing_attributes"]],
        "invalid_attributes": [item["name"] for item in result["invalid_attributes"]],
        "formatted_description": result["formatted_description"],
    }


def _class_name(pdm_class: PdmClass, item_name: str | None) -> str:
    if item_name:
        return item_name
    if len(pdm_class.item_names) == 1:
        return pdm_class.item_names[0]
    return pdm_class.noun or " / ".join(pdm_class.item_names)


def _suggested_ncm(template: dict[str, Any] | None) -> str | None:
    codes = {code for reference in (template or {}).get("ncm_references", []) for code in reference["codes"]}
    return next(iter(codes)) if len(codes) == 1 else None


def _no_class_response(context: TurnContext, recorder: ToolRecorder) -> AgentRunResponse:
    candidates = context.classification.candidate_class_ids
    if context.classification.status == ClassificationStatus.UNRESOLVED and candidates:
        message = (
            "Encontrei mais de uma classe possível para esse material. "
            "Pode dizer o tipo do item com mais detalhe, por exemplo o nome usado no catálogo?"
        )
    else:
        message = (
            "Não identifiquei a classe do material no padrão de cadastro. "
            "Pode descrever o item pelo nome e principais características, como medidas e material?"
        )
    return AgentRunResponse(
        assistant_message=message,
        tool_calls=recorder.calls,
        context_patch={"planner": PLANNER, "pdm_class_id": None, "candidate_class_ids": list(candidates)},
        material_card=MaterialCard(
            pdm_class_id=None,
            attributes={},
            pdm_description=None,
            validation_status="OUT_OF_SCOPE",
            missing_attributes=[],
            ncm=NcmCard(suggested=None, status="PENDING_VALIDATION"),
            duplicate_check_status="PENDING",
            can_submit=False,
        ),
    )


def _message_for(validation: dict[str, Any] | None, class_name: str) -> str:
    if validation is None:
        return "Não consegui validar o material agora. Tente enviar a mensagem de novo em instantes."
    status = validation["status"]
    if status == "VALID":
        return (
            f"A ficha de {class_name} está completa: {validation['formatted_description']}. "
            "Falta a verificação de duplicidade na base antes de enviar o pedido."
        )
    if status == "INCOMPLETE":
        questions = [item["question"] for item in validation["missing_attributes"]]
        return f"Identifiquei {class_name}. Para completar a ficha: " + " ".join(questions)
    if status == "INVALID":
        problems = [
            f"{item['name']} ({item['value']})" if item["value"] else item["name"]
            for item in validation["invalid_attributes"]
        ]
        listed = ", ".join(problems)
        return f"Identifiquei {class_name}, mas estes valores não seguem o padrão: {listed}. Pode corrigir?"
    return "Esse material não se enquadra no padrão de cadastro."


async def run_turn(request: AgentRunRequest, context: TurnContext, recorder: ToolRecorder) -> AgentRunResponse:
    """Um turno: consulta o modelo da classe e valida a ficha com as tools MCP."""
    if context.pdm_class is None:
        return _no_class_response(context, recorder)

    pdm_class = context.pdm_class
    version = request.context.pdm_version
    template = await recorder.call(
        "get_pdm_template", {"pdm_class_id": pdm_class.id, "pdm_version": version}, _summarize_template
    )
    arguments: dict[str, Any] = {
        "pdm_class_id": pdm_class.id,
        "pdm_version": version,
        "attributes": context.attributes,
    }
    if context.item_name:
        arguments["item_name"] = context.item_name
    validation = await recorder.call("validate_and_format_pdm", arguments, _summarize_validation)

    template_names = [attribute["name"] for attribute in (template or {}).get("attributes", [])]
    card_attributes = {name: context.attributes.get(name) for name in template_names} or dict(context.attributes)
    status = validation["status"] if validation else "INCOMPLETE"
    missing = [item["name"] for item in validation["missing_attributes"]] if validation else []
    # Pedido só pode ser enviado depois da verificação de duplicidade, que ainda não roda no chat.
    return AgentRunResponse(
        assistant_message=_message_for(validation, _class_name(pdm_class, context.item_name)),
        tool_calls=recorder.calls,
        context_patch={
            "planner": PLANNER,
            "pdm_class_id": pdm_class.id,
            "item_name": context.item_name,
            "confirmed_attributes": {name: value for name, value in context.attributes.items() if value},
            "validation_status": status,
            "missing_attributes": missing,
        },
        material_card=MaterialCard(
            pdm_class_id=pdm_class.id,
            pdm_class_name=_class_name(pdm_class, context.item_name),
            attributes=card_attributes,
            pdm_description=validation["formatted_description"] if validation else None,
            validation_status=status,
            missing_attributes=missing,
            ncm=NcmCard(suggested=_suggested_ncm(template), status="PENDING_VALIDATION"),
            duplicate_check_status="PENDING",
            can_submit=False,
        ),
    )
