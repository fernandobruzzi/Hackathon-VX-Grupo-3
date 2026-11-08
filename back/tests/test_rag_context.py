"""Contexto RAG: escopo, procedência, orçamento e citações sem serviço externo."""

import hashlib
import json
from dataclasses import replace
from datetime import date

import pytest

from domain.contracts import (
    Condition,
    IdentityMode,
    NcmReference,
    PdmAttribute,
    PdmCatalog,
    PdmClass,
    RagMaterial,
    RagScope,
)
from domain.ncm_snapshot import NcmSourceKind, load_ncm_snapshot
from domain.rag_context import build_context, serialize_context

SCOPE = RagScope("tenant-a", frozenset({"1200"}))


@pytest.fixture
def catalog():
    pdm = PdmClass(
        "PDM001",
        "PARAFUSO",
        (),
        ("PARAFUSO",),
        "FIXADORES",
        "PC",
        IdentityMode.TECHNICAL_ATTRIBUTES,
        (PdmAttribute("MATERIAL", 1, True, Condition(), "Texto", ("ACO", "INOX")),),
        (NcmReference(("7318.15.00",), "Parafusos de ferro ou aço"),),
    )
    return PdmCatalog("pdm-test-v1", "a" * 64, {pdm.id: pdm})


def material(code="M1", **values):
    return replace(
        RagMaterial(
            "tenant-a",
            frozenset({"1200"}),
            code,
            1,
            "PARAFUSO DE ACO",
            "PDM001",
            {"MATERIAL": "ACO"},
            "7318.15.00",
            "APPROVED_MASTER",
            True,
            0.5,
        ),
        **values,
    )


class Repository:
    def __init__(self, rows=()):
        self.rows, self.calls = list(rows), []

    def retrieve(self, query, class_id, scope, limit):
        self.calls.append((query, class_id, scope, limit))
        return self.rows


def context(catalog, rows=(), **kwargs):
    return build_context(catalog, Repository(rows), SCOPE, "parafuso de aço", class_id="PDM001", **kwargs)


def test_scope_is_applied_even_if_repository_returns_forbidden_materials(catalog):
    packet = context(
        catalog,
        [
            material(),
            material("OTHER-TENANT", tenant_id="tenant-b"),
            material("OTHER-CENTER", center_codes=frozenset({"9000"})),
        ],
    )
    payload = serialize_context(packet)
    assert "M1" in payload and "OTHER-TENANT" not in payload and "OTHER-CENTER" not in payload
    repo = Repository([material()])
    build_context(catalog, repo, replace(SCOPE, center_codes=frozenset()), "parafuso", class_id="PDM001")
    assert not repo.calls


def test_approved_examples_precede_inference_without_promoting_it_to_a_fact(catalog):
    packet = context(
        catalog,
        [
            material("INFERRED", technical_source="INDEX_PROPOSAL", ncm_approved=False, score=1),
            material("APPROVED", score=0.1),
            material("APPROVED", score=0.05),
        ],
    )
    examples = [item["content"] for item in packet["items"] if item["kind"] == "MATERIAL"]
    assert [item["material_code"] for item in examples] == ["APPROVED", "INFERRED"]
    assert examples[1]["technical_source"] == "INDEX_PROPOSAL"
    assert examples[1]["ncm_source"] == "UNREVIEWED_MASTER"
    assert all(item["identity_verified"] is False for item in examples)


def test_financial_fields_and_unknown_attributes_cannot_enter_projection(catalog):
    packet = context(
        catalog, [material(attributes={"MATERIAL": "ACO", "unit_price": "SECRET-PRICE", "total_value": "SECRET-VALUE"})]
    )
    assert "SECRET" not in serialize_context(packet)
    pdm = next(item for item in packet["items"] if item["kind"] == "PDM")["content"]
    assert pdm["attributes"][0]["allowed_values"] == ("ACO", "INOX")
    assert pdm["ncm_references"][0]["codes"] == ("7318.15.00",)


def snapshot():
    rows = [
        {"Codigo": code, "Descricao": description, "Data_Inicio": "01/01/2020", "Data_Fim": "31/12/2099"}
        for code, description in [
            ("73", "Obras de ferro ou aço"),
            ("7318", "Parafusos e porcas"),
            ("7318.15", "Outros parafusos"),
            ("7318.15.00", "Parafusos"),
        ]
    ]
    raw = json.dumps({"Data_Ultima_Atualizacao_NCM": "01/01/2026", "Nomenclaturas": rows}).encode()
    return load_ncm_snapshot(raw, snapshot_date=date(2026, 1, 1), source_kind=NcmSourceKind.OFFICIAL_DOWNLOAD)


def test_ncm_keeps_real_position_and_subposition_descriptions_with_provenance(catalog):
    reference = snapshot()
    assert len(reference.records) == 1
    assert reference.hierarchy["7318"].description == "Parafusos e porcas"
    packet = context(catalog, snapshot=reference)
    fiscal = [item["content"] for item in packet["items"] if item["kind"] == "NCM"]
    assert {row["code"] for row in fiscal} == {"73", "7318", "7318.15", "7318.15.00"}
    assert all(row["source_sha256"] == reference.source_sha256 for row in fiscal)
    assert packet["ncm_status"] == "OFFICIAL_SNAPSHOT"
    for kind in (NcmSourceKind.IMPORTED_UNVERIFIED, NcmSourceKind.SIMULATED):
        absent = context(catalog, snapshot=replace(reference, source_kind=kind))
        assert absent["ncm_status"] == "UNAVAILABLE"
        assert not any(item["kind"] == "NCM" for item in absent["items"])


@pytest.mark.parametrize("budget", [1024, 2000, 6000, 12000, 20000])
def test_budget_covers_complete_json_and_only_selected_items_are_cited(catalog, budget):
    packet = context(
        catalog, [material(str(i), description="X" * 10000) for i in range(5)], snapshot=snapshot(), max_chars=budget
    )
    assert len(serialize_context(packet)) <= budget
    assert {row["citation_id"] for row in packet["items"]} == {row["citation_id"] for row in packet["sources"]}
    assert len(packet["items"]) <= 12
    for item, source in zip(packet["items"], packet["sources"], strict=True):
        assert source["sha256"] == hashlib.sha256(serialize_context(item["content"]).encode()).hexdigest()
    if budget == 1024:
        assert packet["truncated"]


def test_context_digest_binds_query_scope_and_versions(catalog):
    first = context(catalog, [material()])
    assert first == context(catalog, [material()])
    other = build_context(catalog, Repository([material()]), SCOPE, "outra consulta", class_id="PDM001")
    assert first["context_id"] != other["context_id"]
    assert first["context_id"] != context(replace(catalog, version="pdm-test-v2"), [material()])["context_id"]


@pytest.mark.parametrize("kwargs", [{"max_chars": 100}, {"max_chars": 20001}, {"limit": 0}, {"limit": 6}])
def test_limits_are_not_controlled_by_unbounded_inputs(catalog, kwargs):
    with pytest.raises(ValueError, match="Limites"):
        context(catalog, **kwargs)
