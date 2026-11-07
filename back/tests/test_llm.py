"""Cliente de modelo trocável (#287): contrato comum, Bedrock simulado por stub e modelo simulado."""

import logging

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from domain.llm import DEFAULT_BEDROCK_MODEL, LlmBudget, LlmError, LlmSettings
from repositories.llm import REPOSITORIES, get_llm_repository
from repositories.llm.bedrock_v1 import BedrockV1LlmRepository
from repositories.llm.simulated_v1 import SimulatedV1LlmRepository

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pdm_class_id", "evidence"],
    "properties": {
        "pdm_class_id": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}
VALID = {"pdm_class_id": "PDM001", "evidence": ["PARAFUSO SEXTAVADO"]}
SETTINGS = LlmSettings(timeout_seconds=1, max_attempts=2, max_calls=10, max_tokens=256)


class FakeBedrock:
    """Stub do bedrock-runtime: devolve respostas ou levanta exceções na ordem dada."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def converse(self, **parameters):
        self.calls.append(parameters)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def converse_response(data=VALID, *, stop="tool_use", name="answer"):
    content = [{"toolUse": {"toolUseId": "t1", "name": name, "input": data}}] if stop == "tool_use" else []
    return {
        "stopReason": stop,
        "output": {"message": {"role": "assistant", "content": content}},
        "usage": {"inputTokens": 120, "outputTokens": 30},
    }


def client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


def build(name, *outcomes, budget=None):
    if name == "bedrock_v1":
        return BedrockV1LlmRepository(client=FakeBedrock(*outcomes), settings=SETTINGS, budget=budget)
    return SimulatedV1LlmRepository(responses={"answer": VALID}, settings=SETTINGS, budget=budget)


def complete(repository, **overrides):
    arguments = {
        "system": "Classifique.",
        "prompt": "PARAFUSO SEXT M12",
        "schema": SCHEMA,
        "tool_name": "answer",
        "prompt_version": "classe-v1",
    }
    return repository.complete(**{**arguments, **overrides})


# Contrato: vale para todo repositório registrado.


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_returns_validated_data_and_call_record(name):
    result = complete(build(name, converse_response()))
    assert result.data == VALID
    call = result.call
    assert (call.repository, call.prompt_version, call.attempts) == (name, "classe-v1", 1)
    assert call.model and call.input_tokens >= 0 and call.output_tokens >= 0 and call.latency_ms >= 0
    assert call.simulated is REPOSITORIES[name].simulated


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_budget_exhaustion_is_an_error(name):
    repository = build(name, converse_response(), converse_response(), budget=LlmBudget(1))
    complete(repository)
    with pytest.raises(LlmError) as error:
        complete(repository)
    assert error.value.code == "LLM_BUDGET_EXHAUSTED"


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_invalid_schema_fails_before_spending(name):
    budget = LlmBudget(1)
    with pytest.raises(ValueError, match="objeto"):
        complete(build(name, budget=budget), schema={"type": "string"})
    assert budget.used == 0


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_requires_prompt_version(name):
    with pytest.raises(ValueError, match="prompt_version"):
        complete(build(name), prompt_version=" ")


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_logs_metadata_without_prompt(name, caplog):
    with caplog.at_level(logging.INFO, logger="vx.llm"):
        complete(build(name, converse_response()), prompt="SEGREDO-DO-PROMPT")
    assert "prompt_version=classe-v1" in caplog.text
    assert "SEGREDO-DO-PROMPT" not in caplog.text and "PDM001" not in caplog.text


# Seleção.


def test_without_configuration_no_model_is_used(monkeypatch):
    monkeypatch.delenv("LLM_REPOSITORY", raising=False)
    assert get_llm_repository() is None
    assert get_llm_repository("none") is None


def test_unknown_repository_lists_options():
    with pytest.raises(ValueError, match="bedrock_v1, simulated_v1"):
        get_llm_repository("nao_existe")


def test_model_comes_from_environment_with_sonnet_5_default(monkeypatch):
    monkeypatch.delenv("BEDROCK_LLM_MODEL_ID", raising=False)
    assert DEFAULT_BEDROCK_MODEL == "us.anthropic.claude-sonnet-5"
    assert BedrockV1LlmRepository(client=FakeBedrock(), settings=SETTINGS).model == DEFAULT_BEDROCK_MODEL
    monkeypatch.setenv("BEDROCK_LLM_MODEL_ID", "global.anthropic.claude-sonnet-5")
    assert get_llm_repository("bedrock_v1").model == "global.anthropic.claude-sonnet-5"


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LLM_MAX_CALLS_PER_RUN", "40")
    monkeypatch.setenv("LLM_MAX_TOKENS", "1024")
    assert LlmSettings.from_env() == LlmSettings(12.5, 3, 40, 1024)
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "0")
    with pytest.raises(ValueError):
        LlmSettings.from_env()
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "dois")
    with pytest.raises(ValueError, match="LLM_MAX_ATTEMPTS"):
        LlmSettings.from_env()


# Bedrock: chamada e respostas inválidas.


def test_bedrock_request_carries_model_schema_and_limits():
    fake = FakeBedrock(converse_response())
    BedrockV1LlmRepository(client=fake, model="m-1", settings=SETTINGS).complete(
        system="Classifique.", prompt="TEXTO", schema=SCHEMA, tool_name="answer", prompt_version="v1"
    )
    parameters = fake.calls[0]
    assert parameters["modelId"] == "m-1"
    assert parameters["inferenceConfig"] == {"maxTokens": 256}
    spec = parameters["toolConfig"]["tools"][0]["toolSpec"]
    assert spec["name"] == "answer" and spec["inputSchema"] == {"json": SCHEMA}
    assert "toolChoice" not in parameters["toolConfig"]


def test_bedrock_reports_tokens_from_usage():
    call = complete(build("bedrock_v1", converse_response())).call
    assert (call.input_tokens, call.output_tokens, call.simulated) == (120, 30, False)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (converse_response({"pdm_class_id": 7, "evidence": []}), "LLM_INVALID_RESPONSE"),
        (converse_response({**VALID, "extra": 1}), "LLM_INVALID_RESPONSE"),
        (converse_response(name="outra"), "LLM_INVALID_RESPONSE"),
        (converse_response("{nao e json"), "LLM_INVALID_RESPONSE"),
        (converse_response(stop="end_turn"), "LLM_INVALID_RESPONSE"),
        (converse_response(stop="max_tokens"), "LLM_TRUNCATED"),
        (converse_response(stop="guardrail_intervened"), "LLM_REFUSED"),
        ({"unexpected": True}, "LLM_INVALID_RESPONSE"),
    ],
)
def test_bedrock_invalid_response_is_never_success(response, code):
    with pytest.raises(LlmError) as error:
        complete(build("bedrock_v1", response))
    assert error.value.code == code


def test_bedrock_accepts_tool_input_serialized_as_json():
    assert complete(build("bedrock_v1", converse_response('{"pdm_class_id": null, "evidence": []}'))).data == {
        "pdm_class_id": None,
        "evidence": [],
    }


def test_bedrock_retries_transient_errors_within_attempts_and_budget():
    budget = LlmBudget(10)
    repository = build("bedrock_v1", client_error("ThrottlingException"), converse_response(), budget=budget)
    assert complete(repository).call.attempts == 2
    assert budget.used == 2


def test_bedrock_gives_up_after_max_attempts():
    repository = build("bedrock_v1", ReadTimeoutError(endpoint_url="x"), client_error("ServiceUnavailableException"))
    with pytest.raises(LlmError) as error:
        complete(repository)
    assert error.value.code == "LLM_UNAVAILABLE"


def test_bedrock_does_not_retry_rejected_requests():
    fake = FakeBedrock(client_error("AccessDeniedException"), converse_response())
    with pytest.raises(LlmError) as error:
        complete(BedrockV1LlmRepository(client=fake, settings=SETTINGS))
    assert error.value.code == "LLM_REQUEST_REJECTED"
    assert len(fake.calls) == 1


def test_bedrock_without_region_is_not_configured(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/dev/null")
    with pytest.raises(LlmError) as error:
        complete(BedrockV1LlmRepository(settings=SETTINGS))
    assert error.value.code == "LLM_NOT_CONFIGURED"


# Simulado.


def test_simulated_without_fixture_returns_minimal_valid_answer_and_label():
    result = complete(SimulatedV1LlmRepository(settings=SETTINGS))
    assert result.data == {"pdm_class_id": None, "evidence": []}
    assert result.call.simulated is True and result.call.model == "simulated-minimal-v1"


def test_simulated_fixture_still_goes_through_schema():
    with pytest.raises(LlmError) as error:
        complete(SimulatedV1LlmRepository(responses={"answer": {"pdm_class_id": 1}}, settings=SETTINGS))
    assert error.value.code == "LLM_INVALID_RESPONSE"
