"""Pontuador por log probs com um modelo do Bedrock Custom Model Import (#297).

O Claude não expõe log probs no Bedrock; modelos importados expõem, no formato OpenAIChatCompletion
do `InvokeModel` (`logprobs` e `top_logprobs`). Os candidatos do PDM recebem letras, o modelo gera
um único token e o log prob de cada letra entre as alternativas mais prováveis vira a pontuação.
Letra fora das alternativas devolvidas recebe um piso baixo, porque ficou abaixo do top-k.

O modelo vem de BEDROCK_SCORER_MODEL_ARN e a região de AWS_REGION; credenciais pela cadeia padrão do
SDK. Formato conforme a documentação do Custom Model Import; ainda não validado na conta do workshop.
"""

import json
import os
import string

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoRegionError

from domain.llm import LlmBudget, LlmError
from domain.ncm_scoring import CandidateLogprobs, NcmScorerError

LETTERS = string.ascii_uppercase
MAX_TOP_LOGPROBS = 20
# Abaixo de qualquer alternativa devolvida: a letra não ficou entre as mais prováveis.
FLOOR_BELOW_TOP_K = 20.0
PROMPT_VERSION = "ncm-scorer-v1"


def scoring_prompt(prompt: str, candidates: tuple[str, ...]) -> str:
    options = "\n".join(f"{LETTERS[i]}) {code}" for i, code in enumerate(candidates))
    return (
        f"{prompt}\n\nEntre os códigos NCM de referência da classe no PDM, qual é o correto para este"
        f" material?\n{options}\nResponda somente com a letra."
    )


def letter_logprobs(response: dict, count: int) -> dict[str, float]:
    """Log prob de cada letra no primeiro token gerado, a partir das alternativas devolvidas."""
    try:
        first = response["choices"][0]["logprobs"]["content"][0]
        alternatives = first.get("top_logprobs") or [first]
    except (KeyError, IndexError, TypeError):
        raise NcmScorerError("SCORER_INVALID_RESPONSE", "sem logprobs no primeiro token") from None
    found: dict[str, float] = {}
    for item in alternatives:
        letter = str(item.get("token", "")).strip().rstrip(")").upper()
        if letter in LETTERS[:count] and isinstance(item.get("logprob"), int | float):
            found[letter] = max(found.get(letter, float("-inf")), float(item["logprob"]))
    if not found:
        raise NcmScorerError("SCORER_NO_CANDIDATE_TOKEN")
    floor = min(found.values()) - FLOOR_BELOW_TOP_K
    return {LETTERS[i]: found.get(LETTERS[i], floor) for i in range(count)}


class BedrockImportV1NcmScorer:
    name = "bedrock_import_v1"
    simulated = False

    def __init__(self, client=None, model: str | None = None, budget: LlmBudget | None = None) -> None:
        self.model = model or os.environ.get("BEDROCK_SCORER_MODEL_ARN", "").strip()
        self.budget = budget or LlmBudget(int(os.environ.get("NCM_SCORER_MAX_CALLS", "200")))
        self._client = client

    def _bedrock(self):
        if self._client is None:
            try:
                self._client = boto3.session.Session().client(
                    "bedrock-runtime",
                    region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
                    config=Config(connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 2}),
                )
            except NoRegionError as error:
                raise NcmScorerError("SCORER_NOT_CONFIGURED", "defina AWS_REGION") from error
        return self._client

    def score(self, prompt: str, candidates: tuple[str, ...]) -> CandidateLogprobs:
        if not self.model:
            raise NcmScorerError("SCORER_NOT_CONFIGURED", "defina BEDROCK_SCORER_MODEL_ARN")
        if not candidates or len(candidates) > len(LETTERS):
            raise NcmScorerError("SCORER_TOO_MANY_CANDIDATES")
        if len(candidates) == 1:
            # Um único código de referência: nada a comparar, sem gastar chamada.
            return CandidateLogprobs(self.name, self.model, self.simulated, {candidates[0]: 0.0})
        try:
            self.budget.spend()
        except LlmError as error:
            raise NcmScorerError("SCORER_BUDGET_EXHAUSTED") from error
        body = {
            "messages": [{"role": "user", "content": scoring_prompt(prompt, candidates)}],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": min(MAX_TOP_LOGPROBS, max(5, len(candidates))),
        }
        try:
            raw = self._bedrock().invoke_model(
                modelId=self.model, body=json.dumps(body), contentType="application/json", accept="application/json"
            )
            response = json.loads(raw["body"].read())
        except ClientError as error:
            raise NcmScorerError("SCORER_REQUEST_REJECTED", error.response.get("Error", {}).get("Code", "")) from error
        except (BotoCoreError, ValueError) as error:
            raise NcmScorerError("SCORER_UNAVAILABLE", type(error).__name__) from error
        by_letter = letter_logprobs(response, len(candidates))
        values = {code: by_letter[LETTERS[i]] for i, code in enumerate(candidates)}
        return CandidateLogprobs(self.name, self.model, self.simulated, values)
