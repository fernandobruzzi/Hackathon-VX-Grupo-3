"""Interpretação e entrevista com Bedrock; estados da ficha continuam nas tools e na API."""

import json
import os
import re
from dataclasses import asdict, replace

import anyio
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.contracts import ClassificationStatus, PdmCatalog
from domain.identity import reference_revision_evidence
from repositories.extraction import get_extraction_repository
from vx_materials_mcp.chatbot.candidates import existing_message
from vx_materials_mcp.chatbot.prompts import MATERIAL_REGISTRATION_SYSTEM, SYSTEM_PROMPT_VERSION
from vx_materials_mcp.chatbot.session_manager import TurnContext, user_messages
from vx_materials_mcp.schemas.agent import AgentRunRequest, AgentRunResponse

PLANNER = "bedrock_sonnet_5_v1"


class BedrockError(Exception):
    def __init__(self, code="BEDROCK_INVALID_RESPONSE"):
        self.code = code
        super().__init__("Não foi possível concluir o atendimento com o Bedrock. Tente novamente.")


class _Attribute(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100)
    value: str | None = Field(max_length=500)
    source: str = Field(min_length=1, max_length=2000)


class _Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pdm_class_id: str | None
    item_name: str | None
    attributes: list[_Attribute] = Field(max_length=100)


class BedrockPlanner:
    def __init__(self, model_id: str, client=None):
        self.model_id, self._client = model_id, client

    async def _converse(self, data: dict, *, interpret: bool = False) -> dict:
        parameters = {
            "modelId": self.model_id,
            "system": [{"text": MATERIAL_REGISTRATION_SYSTEM}],
            "messages": [{"role": "user", "content": [{"text": json.dumps(data, ensure_ascii=False)}]}],
            "inferenceConfig": {"maxTokens": 2048},
        }
        if interpret:
            parameters["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "interpret_material_request",
                            "description": "Propõe classe e atributos explícitos do usuário, sujeitos à validação PDM.",
                            "inputSchema": {"json": _Interpretation.model_json_schema()},
                        }
                    }
                ],
            }

        def invoke():
            # Sessão explícita por chamada: não compartilhar a sessão global do boto3 entre threads.
            client = self._client or boto3.session.Session().client(
                "bedrock-runtime",
                region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
                config=Config(connect_timeout=2, read_timeout=8, retries={"total_max_attempts": 1}),
            )
            try:
                return client.converse(**parameters)
            finally:
                if self._client is None:
                    client.close()

        try:
            # A vaga fica ocupada até a chamada limitada do SDK terminar, inclusive no cancelamento.
            response = await anyio.to_thread.run_sync(invoke)
        except (BotoCoreError, ClientError, OSError) as error:
            raise BedrockError("BEDROCK_UNAVAILABLE") from error
        if not isinstance(response, dict):
            raise BedrockError()
        return response

    async def interpret(self, request: AgentRunRequest, context: TurnContext, catalog: PdmCatalog) -> TurnContext:
        response = await self._converse(
            {
                "task": "Interpretar o pedido com interpret_material_request; não responder ao usuário nesta etapa.",
                "history": [message.model_dump(mode="json") for message in request.context.history],
                "message": request.message if request.action is None else None,
                "confirmed_attributes": request.context.confirmed_attributes,
                "previous_pdm_class_id": request.context.pdm_class_id,
                "previous_item_name": request.context.item_name,
                "catalog": [
                    {"pdm_class_id": c.id, "item_names": c.item_names, "attributes": [asdict(a) for a in c.attributes]}
                    for c in catalog.classes.values()
                ],
            },
            interpret=True,
        )
        try:
            blocks = response["output"]["message"]["content"]
            uses = [block["toolUse"] for block in blocks if "toolUse" in block]
            if response["stopReason"] != "tool_use" or len(uses) != 1:
                raise ValueError("Interpretação ausente ou truncada")
            if uses[0]["name"] != "interpret_material_request":
                raise ValueError("Ferramenta desconhecida")
            proposal = _Interpretation.model_validate(uses[0]["input"])
            if proposal.pdm_class_id is None:
                if proposal.attributes or proposal.item_name is not None:
                    raise ValueError("Atributos sem classe")
                if request.context.pdm_class_id is not None:
                    # Resposta inconclusiva não substitui a ficha aceita nem apaga retiradas.
                    raise ValueError("Classe inconclusiva para uma ficha existente")
                # Sem classe segura, não ressuscitar atributos pela extração de mensagens antigas.
                return replace(context, attributes={}, search_text=request.message)
            pdm_class = catalog.classes[proposal.pdm_class_id]
            if proposal.item_name not in pdm_class.item_names:
                raise ValueError("Nome fora da classe")
            known = {a.name for a in pdm_class.attributes}
            previous = request.context
            same_item = previous.item_name == proposal.item_name or (
                previous.item_name is None and len(pdm_class.item_names) == 1
            )
            same_material = previous.pdm_class_id == pdm_class.id and same_item
            attributes = {k: v for k, v in previous.confirmed_attributes.items() if k in known} if same_material else {}
            if request.action is None:
                # Regras só interpretam a mensagem atual. O histórico já virou estado aceito na API.
                extracted = get_extraction_repository().extract(pdm_class, request.message).attributes
                attributes.update({name: value.value for name, value in extracted.items()})
            messages = user_messages(request)
            if previous.pdm_class_id is not None and not same_material:
                # Em outro material, fatos antigos não são evidência para a nova ficha.
                messages = [request.message] if request.action is None else []
            seen = set()
            for attribute in proposal.attributes:
                if attribute.name not in known or attribute.name in seen:
                    raise ValueError("Atributo desconhecido ou duplicado")
                seen.add(attribute.name)
                # A saída do modelo é uma proposta. Exigir trecho literal, inclusive para apagar valores.
                if not any(attribute.source in message for message in messages):
                    raise ValueError("Fonte ausente no texto do usuário")
                if (
                    same_material
                    and attribute.value is not None
                    and attribute.name in previous.confirmed_attributes
                    and previous.confirmed_attributes[attribute.name] is None
                    and attribute.source not in request.message
                ):
                    raise ValueError("Valor retirado exige nova afirmação do usuário")
                if attribute.value is not None and (
                    not attribute.value.strip() or attribute.value.casefold() not in attribute.source.casefold()
                ):
                    raise ValueError("Valor sem evidência literal")
                attributes[attribute.name] = attribute.value
            classification = replace(
                context.classification,
                status=ClassificationStatus.CLASSIFIED,
                pdm_class_id=pdm_class.id,
                candidate_class_ids=(),
                evidence=(),
                rule=PLANNER,
            )
            # A busca também extrai atributos do texto: não enviar fatos históricos retirados/de outro item.
            query = " ".join(
                [
                    proposal.item_name,
                    *(f"{name}: {value}" for name, value in attributes.items() if value),
                    *reference_revision_evidence(*user_messages(request)),
                ]
            )
            return TurnContext(classification, pdm_class, proposal.item_name, attributes, search_text=query)
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise BedrockError() from error

    async def respond(
        self, request: AgentRunRequest, result: AgentRunResponse, *, rag_context: dict | None = None
    ) -> AgentRunResponse:
        response = await self._converse(
            {
                "task": "Redigir a próxima resposta de cadastro com base exclusiva na ficha validada abaixo.",
                "history": [message.model_dump(mode="json") for message in request.context.history],
                "message": request.message,
                "material_card": result.material_card.model_dump(mode="json"),
                # O pacote entra uma única vez: o registro completo continua persistido na API.
                "tool_calls": [
                    call.model_dump(mode="json")
                    for call in result.tool_calls
                    if call.name != "retrieve_material_context" or call.status != "SUCCEEDED"
                ],
                "validated_guidance": result.assistant_message,
                "reference_context": rag_context,
            }
        )
        try:
            if response["stopReason"] != "end_turn":
                raise ValueError("Resposta recusada ou truncada")
            text = "\n".join(block["text"] for block in response["output"]["message"]["content"] if "text" in block)
            if not text.strip() or len(text) > 12000:
                raise ValueError("Resposta vazia ou longa demais")
        except (KeyError, TypeError, ValueError) as error:
            raise BedrockError() from error
        # A resposta só pode citar itens efetivamente entregues ao modelo nesta chamada.
        sources = {source["citation_id"]: source for source in (rag_context or {}).get("sources", [])}
        used = list(dict.fromkeys(re.findall(r"\[(R[0-9]+)\]", text)))
        if result.material_card.existing:
            used = []
        elif any(citation not in sources for citation in used):
            raise BedrockError()
        elif used:
            text = (
                text.strip()
                + "\n\nFontes: "
                + "; ".join(f"[{citation}] {sources[citation]['label']}" for citation in used)
            )
        for call in result.tool_calls:
            if call.name == "retrieve_material_context" and call.status == "SUCCEEDED":
                call.result["used_citation_ids"] = used
        return result.model_copy(
            update={
                # O estoque autorizado mantém quantidades e apresentação determinísticas.
                "assistant_message": existing_message(result.material_card.existing, request.context.center_code)
                if result.material_card.existing
                else text.strip(),
                "context_patch": {
                    **result.context_patch,
                    "planner": PLANNER,
                    "system_prompt_version": SYSTEM_PROMPT_VERSION,
                    "rag_context_id": (rag_context or {}).get("context_id"),
                    "rag_citations_used": used,
                },
            }
        )
