"""Recuperação real no PostgreSQL/pgvector com modelo simulado: escopo antes do limite."""

import asyncio
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import PDM
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_resources_prompts import resource_data as resource_data

from domain.pdm_loader import load_pdm
from pipelines.search_index import index_version
from repositories.classification import get_classification_repository
from repositories.embeddings.simulated_v1 import SimulatedV1EmbeddingRepository
from repositories.extraction import get_extraction_repository
from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot, MaterialMaster, MaterialSearchIndex
from vx_materials_mcp.chatbot.mcp_client import connect
from vx_materials_mcp.security import Caller, caller_to_environment
from vx_materials_mcp.tools import retrieve_context


class Embedding:
    signature = SimulatedV1EmbeddingRepository().signature
    dimensions = 512
    simulated = True

    def embed(self, texts, *, query):
        return [[1.0, *([0.0] * 511)]]


@pytest.fixture
def case(resource_data, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")
    monkeypatch.delenv("NCM_SNAPSHOT_VERSION", raising=False)
    monkeypatch.setattr(retrieve_context, "get_embedding_repository", lambda: Embedding())
    data = resource_data
    caller = Caller(
        data["caller"]["user_id"],
        data["caller"]["tenant_id"],
        frozenset(data["caller"]["permissions"]),
        frozenset({"1200"}),
    )
    catalog = load_pdm(PDM)
    version = index_version(
        catalog, get_classification_repository(catalog), get_extraction_repository(), Embedding.signature
    )
    tenant = uuid.UUID(caller.tenant_id)
    ids, datasets = [], []
    with Session(data["admin"], expire_on_commit=False) as db:
        current = Dataset(id=uuid.uuid4(), tenant_id=tenant, imported_at=datetime(2099, 1, 1, tzinfo=UTC))
        old = Dataset(id=uuid.uuid4(), tenant_id=tenant, imported_at=datetime(2098, 1, 1, tzinfo=UTC))
        foreign = Dataset(id=uuid.uuid4(), tenant_id=uuid.uuid4(), imported_at=datetime(2099, 1, 1, tzinfo=UTC))
        db.add_all([current, old, foreign])
        db.flush()
        datasets = [current.id, old.id, foreign.id]
        records = [
            ("APPROVED", current, "1200", True),
            ("INFERRED", current, "1200", False),
            ("HISTORICAL", old, "1200", True),
            ("FOREIGN", foreign, "1200", True),
            *[(f"HIDDEN-{i}", current, "9000", True) for i in range(55)],
        ]
        for index, (code, dataset, center, approved) in enumerate(records):
            material = MaterialMaster(
                id=uuid.uuid4(),
                tenant_id=dataset.tenant_id,
                source_system="RAG_TEST",
                material_code=f"RAG-{uuid.uuid4().hex[:8]}-{code}",
                status="ATIVO",
                unit="PC",
                original_description_long="RAGCONTEXT PARAFUSO DE ACO",
                pdm_class_id="PDM001" if approved else None,
                attributes={"MATERIAL": "ACO"} if approved else {},
                ncm="7318.15.00",
                ncm_review_status="APPROVED" if approved else None,
            )
            db.add(material)
            db.flush()
            ids.append(material.id)
            db.add(
                MaterialInventorySnapshot(
                    tenant_id=dataset.tenant_id,
                    dataset_id=dataset.id,
                    material_id=material.id,
                    center_code=center,
                    quantity=Decimal(1),
                    unit="PC",
                    unit_price=Decimal("987654321"),
                    total_value=Decimal("987654321"),
                    source_line=index + 1,
                )
            )
            db.add(
                MaterialSearchIndex(
                    tenant_id=dataset.tenant_id,
                    material_id=material.id,
                    proposed_class_id="PDM001",
                    extracted_attributes={"MATERIAL": "INOX"},
                    normalization_version=version,
                    source_version=1,
                    embedding=[0.5, 0.5, *([0.0] * 510)] if code == "APPROVED" else [1.0, *([0.0] * 511)],
                )
            )
        db.commit()
        # Uma assinatura histórica coexistente não torna o índice atual pendente.
        db.add(
            MaterialSearchIndex(
                tenant_id=tenant,
                material_id=ids[0],
                proposed_class_id="PDM001",
                extracted_attributes={},
                normalization_version="old-rag-signature",
                source_version=1,
            )
        )
        db.commit()
        db.execute(
            text(
                "UPDATE material_search_index SET search_vector=to_tsvector('simple','RAGCONTEXT PARAFUSO DE ACO') "
                "WHERE material_id=ANY(:ids)"
            ),
            {"ids": ids},
        )
        db.commit()
    service = retrieve_context.ContextRetrieval(catalog, data["reader"], caller)
    try:
        yield service, data["admin"], ids
    finally:
        service.engine.dispose()
        with data["admin"].begin() as connection:
            connection.execute(text("DELETE FROM material_search_index WHERE material_id=ANY(:ids)"), {"ids": ids})
            connection.execute(
                text("DELETE FROM material_inventory_snapshots WHERE material_id=ANY(:ids)"), {"ids": ids}
            )
            connection.execute(text("DELETE FROM materials_master WHERE id=ANY(:ids)"), {"ids": ids})
            connection.execute(text("DELETE FROM datasets WHERE id=ANY(:ids)"), {"ids": datasets})


def test_real_vector_retrieval_prefers_approved_and_excludes_hidden_history_and_finance(case):
    service, _, _ = case
    packet = service.run("RAGCONTEXT", "PDM001", 1)
    examples = [item["content"] for item in packet["items"] if item["kind"] == "MATERIAL"]
    assert len(examples) == 1 and examples[0]["material_code"].endswith("-APPROVED")
    assert examples[0]["attributes"] == {"MATERIAL": "ACO"}
    assert examples[0]["centers"] == [{"center_code": "1200"}]
    payload = json.dumps(packet)
    assert all(
        secret not in payload
        for secret in ("HIDDEN", "HISTORICAL", "FOREIGN", "987654321", "unit_price", "total_value")
    )
    assert packet["retrieval"] == Embedding.signature
    assert packet["ncm_status"] == "UNAVAILABLE"


def test_embedding_failure_returns_explicit_text_fallback(case, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("Modelo indisponível")

    service, _, _ = case
    monkeypatch.setattr(Embedding, "embed", fail)
    packet = service.run("RAGCONTEXT", "PDM001")
    assert packet["retrieval"] == "FULL_TEXT_EMBEDDING_UNAVAILABLE"
    assert len([row for row in packet["items"] if row["kind"] == "MATERIAL"]) == 2


def test_without_inventory_permission_context_contains_only_public_references(case):
    service, _, _ = case
    service.caller = replace(service.caller, permissions=frozenset({"materials:read"}))
    packet = service.run("RAGCONTEXT", "PDM001")
    assert all(item["kind"] != "MATERIAL" for item in packet["items"])
    assert "HIDDEN" not in json.dumps(packet)


def test_context_and_citations_cross_the_real_stdio_protocol(case):
    service, _, _ = case

    async def retrieve():
        async with connect(
            PDM, service.engine.url.render_as_string(hide_password=False), caller_to_environment(service.caller)
        ) as client:
            return await client.call_tool(
                "retrieve_material_context", {"query": "RAGCONTEXT", "pdm_class_id": "PDM001", "limit": 1}
            )

    packet = asyncio.run(retrieve())
    assert packet["version"] == "rag_context_v1"
    assert packet["retrieval"] == Embedding.signature
    assert packet["sources"] and packet["context_id"]
    payload = json.dumps(packet)
    assert "-APPROVED" in payload
    assert "HIDDEN" not in payload and "FOREIGN" not in payload and "HISTORICAL" not in payload


@pytest.mark.parametrize(
    "assignment", ["embedding=NULL", "source_version=0", "normalization_version='stale-signature'"]
)
def test_stale_or_missing_embedding_is_pending_not_an_empty_result(case, assignment):
    service, admin, ids = case
    with admin.begin() as connection:
        connection.execute(
            text(
                "UPDATE material_search_index SET "
                + assignment
                + " WHERE material_id=:id AND normalization_version <> 'old-rag-signature'"
            ),
            {"id": ids[0]},
        )
    with pytest.raises(ValueError, match="INDEX_UPDATING"):
        service.run("RAGCONTEXT", "PDM001")


def test_caller_cannot_supply_another_identity_or_use_simulation_outside_local(case, monkeypatch):
    service, _, _ = case
    service.caller = replace(service.caller, tenant_id=str(uuid.uuid4()))
    with pytest.raises(ValueError, match="autorizada"):
        service.run("RAGCONTEXT")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        from domain.runtime import check_simulated_clients

        check_simulated_clients()
