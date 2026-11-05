"""Contrato estático: validação de exemplos, transporte e proteção das escritas."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts"
SPEC = json.loads((CONTRACT_DIR / "openapi.json").read_text())
EXAMPLES = json.loads((CONTRACT_DIR / "fixtures" / "examples.json").read_text())
CHECKER = FormatChecker()


def validator(schema):
    return Draft202012Validator({**schema, "components": SPEC["components"]}, format_checker=CHECKER)


def test_openapi_is_valid():
    validate(SPEC)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda item: item["name"])
def test_examples_match_their_operations(example):
    operation = SPEC["paths"][example["path"]][example["method"]]
    if "requestBody" in operation:
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        validator(schema).validate(example["request"])
    response = operation["responses"][str(example["status"])]
    if "content" in response:
        validator(response["content"]["application/json"]["schema"]).validate(example["response"])
    for parameter in operation["parameters"]:
        if "$ref" in parameter:
            continue
        source = {"path": "params", "query": "query", "header": "request_headers"}[parameter["in"]]
        values = example.get(source, {})
        if parameter.get("required"):
            assert parameter["name"] in values
        if parameter["name"] in values:
            validator(parameter["schema"]).validate(values[parameter["name"]])
    for name, header in response.get("headers", {}).items():
        validator(header["schema"]).validate(example["response_headers"][name])


def test_every_operation_has_a_success_example():
    covered = {(e["path"], e["method"]) for e in EXAMPLES if e["status"] < 400}
    expected = {(path, method) for path, methods in SPEC["paths"].items() for method in methods}
    assert covered == expected


def test_batch_manifest_has_no_user_token():
    manifest = json.loads((CONTRACT_DIR / "fixtures" / "batch-manifest.json").read_text())
    schema = {"$ref": "#/components/schemas/BatchManifest"}
    validator(schema).validate(manifest)
    with pytest.raises(ValidationError):
        validator(schema).validate({**manifest, "access_token": "not-allowed"})


def test_authenticated_writes_require_csrf_and_idempotency():
    for methods in SPEC["paths"].values():
        for method, operation in methods.items():
            if method != "post":
                continue
            schema = operation["requestBody"]["content"]["application/json"]["schema"]
            resolved = SPEC["components"]["schemas"][schema["$ref"].split("/")[-1]]
            assert resolved["additionalProperties"] is False
            assert not {"role", "actor_id", "approved_by"} & resolved["properties"].keys()
            if operation["security"] and not operation["tags"] == ["agent-internal"]:
                refs = {p.get("$ref") for p in operation["parameters"]}
                assert "#/components/parameters/CsrfToken" in refs
                assert "#/components/parameters/IdempotencyKey" in refs
                assert {"sessionCookie": [], "csrfToken": []} in operation["security"]
                assert {"cognitoAccessToken": []} in operation["security"]


@pytest.mark.parametrize("field", ["role", "actor_id", "approved_by", "unexpected"])
def test_decisions_reject_identity_and_unknown_fields(field):
    example = next(e for e in EXAMPLES if e["name"] == "proposal-approve")
    payload = {**example["request"], field: "not-authorized"}
    with pytest.raises(ValidationError):
        validator({"$ref": "#/components/schemas/ProposalDecisionRequest"}).validate(payload)


@pytest.mark.parametrize("value", [12.5, "12,5", "NaN", "1e5"])
def test_decimal_values_are_strings_in_canonical_format(value):
    with pytest.raises(ValidationError):
        validator({"$ref": "#/components/schemas/InventoryRow"}).validate(
            {"center_code": "1200", "quantity": value, "unit": "PC"}
        )


def test_quality_example_contains_no_financial_values():
    quality = next(e["response"] for e in EXAMPLES if e["name"] == "dashboard-quality")
    assert "financial" not in quality
    assert quality["after"] is None


def test_version_and_uuid_constraints_are_checked():
    request = copy.deepcopy(next(e["request"] for e in EXAMPLES if e["name"] == "chat-incomplete"))
    schema = {"$ref": "#/components/schemas/ChatMessageRequest"}
    request["client_message_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        validator(schema).validate(request)
    request["client_message_id"] = "22222222-2222-4222-8222-222222222222"
    request["expected_session_version"] = -1
    with pytest.raises(ValidationError):
        validator(schema).validate(request)
