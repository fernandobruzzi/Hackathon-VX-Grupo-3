"""Premissas quantitativas imutáveis no ObjectStore; hipóteses, nunca ganhos medidos."""

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clients.storage import get_object_store
from vx_materials_api.errors import ApiProblem

AssumptionKey = Literal[
    "registration_cost", "code_annual_cost", "review_minutes_before", "review_minutes_after", "hourly_cost"
]


class SavingsAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: AssumptionKey
    value: str = Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,6})?$")
    source: str = Field(min_length=1, max_length=1000)
    recorded_on: date

    @model_validator(mode="after")
    def nonblank_source(self):
        if not self.source.strip():
            raise ValueError("Premissa exige origem explícita")
        return self


class SavingsAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
    assumptions: list[SavingsAssumption]

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [a.key for a in self.assumptions]
        if len(set(keys)) != len(keys):
            raise ValueError("Premissa duplicada")
        values = {a.key: a.value for a in self.assumptions}
        from decimal import Decimal

        if {"review_minutes_before", "review_minutes_after"} <= values.keys() and Decimal(
            values["review_minutes_after"]
        ) > Decimal(values["review_minutes_before"]):
            raise ValueError("Tempo posterior não pode superar o anterior na hipótese de economia")
        return self


class AssumptionSource(BaseModel):
    version: str
    sha256: str


def register_assumptions(store, raw: bytes):
    assumptions = SavingsAssumptions.model_validate_json(raw)
    store.put_if_absent(f"references/savings/{assumptions.version}.json", raw)
    return AssumptionSource(version=assumptions.version, sha256=hashlib.sha256(raw).hexdigest())


def configured_assumptions():
    version = os.environ.get("SAVINGS_ASSUMPTIONS_VERSION")
    if not version:
        return {}, None
    try:
        # Validar antes de formar a chave impede caminho arbitrário por configuração.
        SavingsAssumptions(version=version, assumptions=[])
        raw = get_object_store().get(f"references/savings/{version}.json")
        assumptions = SavingsAssumptions.model_validate_json(raw)
        if assumptions.version != version:
            raise ValueError("Versão divergente")
        return {a.key: a for a in assumptions.assumptions}, AssumptionSource(
            version=version, sha256=hashlib.sha256(raw).hexdigest()
        )
    except Exception as error:
        raise ApiProblem(
            503, "SAVINGS_ASSUMPTIONS_UNAVAILABLE", "As premissas de economia configuradas estão indisponíveis."
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    source = register_assumptions(get_object_store(), args.file.read_bytes())
    print(json.dumps(source.model_dump()))


if __name__ == "__main__":
    main()
