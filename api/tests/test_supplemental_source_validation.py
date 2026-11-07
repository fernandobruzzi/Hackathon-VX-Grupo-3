"""Aprovação documental reextrai bytes e identidade, mesmo se o contrato for reassinado."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from domain.pdm_loader import load_pdm
from enrichment.internal_documents import bundle_object_key
from vx_materials_api.errors import ApiError
from vx_materials_api.schemas.proposals import EnrichmentContext
from vx_materials_api.services.enrichment_validation import validate_internal_sources

TEXT = "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009"


@pytest.fixture
def documentary_case():
    catalog = load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")
    content = json.dumps(
        {
            "schema_version": "internal-documents-v1",
            "dataset_id": "dataset",
            "documents": [
                {"id": "doc", "title": "Ficha", "text": TEXT + "; ALTURA: 100MM", "kind": "INTERNAL_DOCUMENT"}
            ],
        }
    ).encode()
    key = bundle_object_key(content, "dataset")
    ctx = EnrichmentContext(
        schema_version="internal-enrichment-v1",
        report_key="runs/r.json",
        manifest_sha256="a" * 64,
        original_hash="b" * 64,
        extraction_signature="rules",
        supplemental_source={"object_key": key, "sha256": hashlib.sha256(content).hexdigest()},
    )
    source = NS(
        source_url="dataset://dataset/internal-documents#doc",
        source_sha256=hashlib.sha256(content).hexdigest(),
        s3_object_key=key,
        confidence_basis=["INTERNAL_DATASET"],
        source_excerpt=TEXT + "; ALTURA: 100MM",
        source_title="Ficha",
        attribute_name="ALTURA",
        proposed_value="100MM",
    )
    primary = NS(
        material_code="t",
        status="ATIVO",
        original_description_long=TEXT,
        original_description_short="",
        manufacturer="",
        manufacturer_reference="",
        unit="PC",
        ncm="84212300",
        attributes={},
        merchandise_group="",
    )
    return catalog, content, NS(enrichment_context=ctx), NS(id="dataset", files=[]), source, primary


def test_documentary_source_is_replayed(documentary_case):
    catalog, content, changes, dataset, source, primary = documentary_case
    validate_internal_sources(changes, dataset, [source], primary, catalog, store=NS(get=lambda key: content))


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_excerpt", "falso"),
        ("proposed_value", "200MM"),
        ("source_url", "dataset://dataset/internal-documents#other"),
    ],
)
def test_reassigned_evidence_cannot_change_document_facts(documentary_case, field, value):
    catalog, content, changes, dataset, source, primary = documentary_case
    setattr(source, field, value)
    with pytest.raises(ApiError):
        validate_internal_sources(changes, dataset, [source], primary, catalog, store=NS(get=lambda key: content))


def test_tampered_bytes_or_different_product_are_rejected(documentary_case):
    catalog, content, changes, dataset, source, primary = documentary_case
    with pytest.raises(ApiError):
        validate_internal_sources(
            changes, dataset, [source], primary, catalog, store=NS(get=lambda key: content + b" ")
        )
    primary.original_description_long = TEXT.replace("LF9009", "LF7000")
    with pytest.raises(ApiError):
        validate_internal_sources(changes, dataset, [source], primary, catalog, store=NS(get=lambda key: content))
