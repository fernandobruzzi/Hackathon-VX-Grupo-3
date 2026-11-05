"""Testes pelo protocolo real: cada sessão inicia o servidor MCP como subprocesso."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vx_materials_mcp.chatbot.mcp_client import McpToolError, connect

PDM = str(Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx")
VERSION = "pdm-kit-v1"
BOLT = {
    "ROSCA": "METRICA GROSSA",
    "BITOLA": "M12",
    "COMPRIMENTO": "50MM",
    "MATERIAL": "ACO CARBONO",
    "ACABAMENTO": "ZINCADO BRANCO",
    "NORMA": "DIN 933",
}
FORBIDDEN = ("user", "usuario", "actor", "role", "papel", "tenant", "approved_by", "permission")


def call(name, **arguments):
    async def run():
        async with connect(PDM) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(run())


def discover():
    async def run():
        async with connect(PDM) as client:
            return await client.list_tools()

    return asyncio.run(run())


def test_client_discovers_the_tools_over_the_protocol():
    tools = {tool.name: tool for tool in discover()}
    assert set(tools) == {"get_pdm_template", "search_similar_materials", "validate_and_format_pdm"}
    for tool in tools.values():
        assert tool.description
        assert tool.output_schema
        assert tool.annotations.read_only_hint is True


def test_tool_parameters_have_no_identity_fields():
    for tool in discover():
        assert set(tool.input_schema["properties"]) <= {
            "pdm_class_id",
            "pdm_version",
            "attributes",
            "item_name",
            "unit",
            "query",
            "limit",
        }
        for name in tool.input_schema["properties"]:
            assert not any(word in name.lower() for word in FORBIDDEN)


def test_template_follows_the_architecture_example():
    result = call("get_pdm_template", pdm_class_id="PDM020", pdm_version=VERSION)
    assert result["pdm_class_id"] == "PDM020"
    assert result["pdm_version"] == VERSION
    assert (result["noun"], result["qualifier"]) == ("ROLAMENTO", "RIGIDO ESFERAS")
    assert result["identity_mode"] == "TECHNICAL_ATTRIBUTES"
    assert result["default_unit"] == "PC"
    attributes = {a["name"]: a for a in result["attributes"]}
    assert [a["name"] for a in result["attributes"]][0] == "REFERENCIA"
    assert attributes["FOLGA"]["required"] is True
    assert attributes["FOLGA"]["allowed_values"] == ["C3", "NORMAL"]
    assert attributes["FOLGA"]["applies_when"]["operator"] == "ALWAYS"
    assert attributes["LARGURA"]["required"] is False
    assert attributes["LARGURA"]["allowed_values"] is None
    assert result["ncm_references"] == [{"codes": ["8482.10.10"], "rule": "único para a classe"}]


def test_template_exposes_conditions_and_item_names():
    result = call("get_pdm_template", pdm_class_id="PDM050", pdm_version=VERSION)
    assert result["noun"] is None
    assert "FLANGE" in result["item_names"]
    face = next(a for a in result["attributes"] if a["name"] == "FACE")
    assert face["applies_when"] == {"operator": "EQUALS", "subject": "SUBSTANTIVO", "values": ["FLANGE"]}


def test_validation_follows_the_architecture_example():
    result = call("validate_and_format_pdm", pdm_class_id="PDM001", pdm_version=VERSION, attributes=BOLT)
    assert result["status"] == "INCOMPLETE"
    assert [m["name"] for m in result["missing_attributes"]] == ["CLASSE RESISTENCIA"]
    assert result["missing_attributes"][0]["reason_code"] == "REQUIRED_ATTRIBUTE_MISSING"
    assert result["missing_attributes"][0]["question"]
    assert result["invalid_attributes"] == []
    assert result["not_applicable_attributes"] == []
    assert result["formatted_description"] is None
    assert result["identity_key"] is None
    assert result["can_submit"] is False


def test_valid_material_returns_description_and_identity():
    attributes = {**BOLT, "CLASSE RESISTENCIA": "8.8"}
    result = call("validate_and_format_pdm", pdm_class_id="PDM001", pdm_version=VERSION, attributes=attributes)
    assert result["status"] == "VALID"
    assert result["can_submit"] is True
    assert result["formatted_description"].startswith("PARAFUSO SEXTAVADO; ROSCA: METRICA GROSSA; BITOLA: M12")
    assert result["identity_key"].startswith("PDM001|PARAFUSO SEXTAVADO|")


def test_chat_null_attribute_counts_as_missing():
    attributes = {**BOLT, "CLASSE RESISTENCIA": None}
    result = call("validate_and_format_pdm", pdm_class_id="PDM001", pdm_version=VERSION, attributes=attributes)
    assert [m["name"] for m in result["missing_attributes"]] == ["CLASSE RESISTENCIA"]


def test_item_name_and_unit_reach_the_validator():
    attributes = {**BOLT, "CLASSE RESISTENCIA": "8.8"}
    result = call(
        "validate_and_format_pdm", pdm_class_id="PDM001", pdm_version=VERSION, attributes=attributes, unit="CX"
    )
    assert result["status"] == "INVALID"
    assert result["invalid_attributes"][0]["expected"] == "PC"
    flange = call(
        "validate_and_format_pdm", pdm_class_id="PDM050", pdm_version=VERSION, attributes={}, item_name="FLANGE"
    )
    assert "CLASSE PRESSAO" in [m["name"] for m in flange["missing_attributes"]]


def test_unknown_class_is_a_business_result_when_validating():
    result = call("validate_and_format_pdm", pdm_class_id="PDM999", pdm_version=VERSION, attributes={})
    assert result["status"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("get_pdm_template", {"pdm_class_id": "PDM999", "pdm_version": VERSION}, "desconhecida"),
        ("get_pdm_template", {"pdm_class_id": "PDM001", "pdm_version": "outra"}, "indisponivel"),
        (
            "validate_and_format_pdm",
            {"pdm_class_id": "PDM001", "pdm_version": "outra", "attributes": {}},
            "indisponivel",
        ),
    ],
)
def test_tool_errors_reach_the_client(name, arguments, message):
    with pytest.raises(McpToolError, match=message):
        call(name, **arguments)


def test_server_fails_clearly_without_the_pdm_file():
    result = subprocess.run(
        [sys.executable, "-m", "vx_materials_mcp.server"],
        env={**os.environ, "PDM_WORKBOOK_PATH": "/nao/existe.xlsx"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "/nao/existe.xlsx" in result.stderr
    assert result.stdout == ""
