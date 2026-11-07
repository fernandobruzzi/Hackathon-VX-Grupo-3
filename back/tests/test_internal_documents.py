"""Documentos fornecidos são bytes arquivados, sem autodeclaração de aprovação."""

import hashlib
import json
from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm


def document(**changes):
    return {
        "id": "ficha-01",
        "title": "Ficha técnica do filtro",
        "text": "FILTRO OLEO LUBRIFICANTE; ALTURA: 100MM",
        "kind": "INTERNAL_DOCUMENT",
        "manufacturer": "FLEETGUARD",
        "manufacturer_reference": "LF9009",
    } | changes


def bundle(documents=None, **changes):
    value = {
        "schema_version": "internal-documents-v1",
        "dataset_id": "dataset-01",
        "documents": [document()] if documents is None else documents,
    } | changes
    return json.dumps(value, ensure_ascii=False).encode()


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(Path(__file__).parents[2] / "data/desafio01/03_padrao_cadastro_PDM.xlsx")


def test_bundle_preserves_exact_documentary_fields():
    from enrichment.internal_documents import parse_bundle

    content = bundle([document(short_description="FILTRO OLEO", merchandise_group="FLT01")])
    result = parse_bundle(content, "dataset-01")
    assert result == json.loads(content)


def test_sources_bind_dataset_hash_key_title_and_shared_identity(catalog):
    from domain.contracts import MaterialRecord
    from enrichment.internal_documents import bundle_object_key, load_supplemental_sources
    from pipelines.internal_enrichment import internal_report
    from pipelines.sanitize import analyze_material
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    content = bundle([document(short_description="FILTRO OLEO")])
    key = bundle_object_key(content, "dataset-01")
    sources = load_supplemental_sources(content, "dataset-01", catalog, key)
    assert len(sources) == 1
    source = sources[0]
    assert source.filename == "internal-documents"
    assert source.title == "Ficha técnica do filtro"
    assert source.sha256 == hashlib.sha256(content).hexdigest()
    assert source.object_key == key == f"references/internal-sources/dataset-01/{source.sha256}.json"
    assert source.material.record.code == "ficha-01"
    assert source.material.record.status == "ATIVO"
    assert source.material.record.description == document()["text"]
    assert source.material.record.short_description == "FILTRO OLEO"
    assert source.material.attributes["REFERENCIA FABRICANTE"] == "LF9009"
    target = analyze_material(
        MaterialRecord("t", "ATIVO", "FILTRO OLEO LUBRIFICANTE", manufacturer="FLEETGUARD", reference="LF9009"),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    result = internal_report([target], sources, catalog, "dataset-01")["results"][0]
    assert result["suggestions"] == {"ALTURA": "100MM"}
    fact = result["evidence"][0]
    assert fact["source_url"] == "dataset://dataset-01/internal-documents#ficha-01"
    assert fact["source_sha256"] == source.sha256
    assert fact["source_title"] == source.title


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "internal-documents-v2"},
        {"dataset_id": "other-dataset"},
        {"dataset_id": 1},
        {"approval_status": "APPROVED"},
        {"documents": []},
        {"documents": {}},
        {"documents": [None]},
        {"documents": [document(), document()]},
    ],
)
def test_bundle_rejects_unknown_scope_duplicate_documents_and_fields(changes):
    from enrichment.internal_documents import parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(bundle(**changes), "dataset-01")


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../escape"},
        {"id": "with#fragment"},
        {"id": "with/slash"},
        {"id": "white space"},
        {"id": "https://example.org"},
        {"id": ""},
        {"title": ""},
        {"text": " "},
        {"kind": "APPROVED"},
        {"kind": "PENDING_PROPOSAL"},
        {"kind": "EXTERNAL_DOCUMENT"},
        {"kind": "SIMULATED"},
        {"approval_status": "APPROVED"},
        {"source_url": "https://example.org/ficha"},
        {"attributes": {"ALTURA": "100MM"}},
        {"manufacturer": False},
        {"manufacturer_reference": None},
        {"merchandise_group": None},
        {"merchandise_group": False},
        {"merchandise_group": "SOB01\nTUB01"},
        {"text": "FILTRO\x00ALTURA: 100MM"},
        {"title": "FICHA\nAPROVADA"},
    ],
)
def test_document_rejects_unsafe_or_unattested_content(changes):
    from enrichment.internal_documents import parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(bundle([document(**changes)]), "dataset-01")


@pytest.mark.parametrize(
    "content",
    [
        b"not JSON",
        b"\xff",
        b"[]",
        bundle().replace(b'"dataset_id": "dataset-01"', b'"dataset_id": "dataset-01", "dataset_id": "dataset-01"'),
        bundle().replace(b'"kind": "INTERNAL_DOCUMENT"', b'"kind": "INTERNAL_DOCUMENT", "kind": "INTERNAL_DOCUMENT"'),
        b'{"schema_version":"internal-documents-v1","dataset_id":"dataset-01","documents":[NaN]}',
        bundle([document(text="FILTRO BAD")]).replace(b"FILTRO BAD", b"FILTRO \\ud800"),
    ],
)
def test_non_json_utf8_and_duplicate_json_keys_are_rejected(content):
    from enrichment.internal_documents import parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(content, "dataset-01")


@pytest.mark.parametrize(
    "field,size",
    [
        ("text", 20_001),
        ("title", 201),
        ("manufacturer", 201),
        ("manufacturer_reference", 201),
        ("short_description", 121),
        ("merchandise_group", 201),
    ],
)
def test_document_field_size_is_bounded(field, size):
    from enrichment.internal_documents import parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(bundle([document(**{field: "A" * size})]), "dataset-01")


def test_bundle_bytes_and_document_count_are_bounded():
    from enrichment.internal_documents import parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(b" " * 2_000_001, "dataset-01")
    with pytest.raises(ValueError):
        parse_bundle(bundle([document(id=f"ficha-{i}") for i in range(501)]), "dataset-01")


@pytest.mark.parametrize("dataset_id", ["../other", "other#fragment", "", None])
def test_expected_dataset_identifier_is_safe(dataset_id):
    from enrichment.internal_documents import bundle_object_key, parse_bundle

    with pytest.raises(ValueError):
        parse_bundle(bundle(), dataset_id)
    with pytest.raises(ValueError):
        bundle_object_key(bundle(), dataset_id)


@pytest.mark.parametrize(
    "key", ["raw/document.json", "https://example.org/ficha", "references/internal-sources/other/" + "a" * 64 + ".json"]
)
def test_loader_refuses_a_key_not_bound_to_dataset_and_bytes(catalog, key):
    from enrichment.internal_documents import load_supplemental_sources

    with pytest.raises(ValueError):
        load_supplemental_sources(bundle(), "dataset-01", catalog, key)


def test_text_links_are_only_literal_data_and_no_remote_source_is_created(catalog):
    from enrichment.internal_documents import bundle_object_key, load_supplemental_sources

    content = bundle([document(text=document()["text"] + "\nVeja https://example.org/ficha")])
    source = load_supplemental_sources(content, "dataset-01", catalog, bundle_object_key(content, "dataset-01"))[0]
    assert source.filename == "internal-documents"
    assert "https://example.org/ficha" in source.material.record.description


def test_changed_bytes_cannot_reuse_the_archived_key(catalog):
    from enrichment.internal_documents import bundle_object_key, load_supplemental_sources

    original = bundle()
    changed = bundle([document(text=document()["text"].replace("100MM", "200MM"))])
    with pytest.raises(ValueError):
        load_supplemental_sources(changed, "dataset-01", catalog, bundle_object_key(original, "dataset-01"))


@pytest.mark.parametrize(
    "changes", [{"manufacturer": "", "manufacturer_reference": ""}, {"manufacturer_reference": "OTHER-PART"}]
)
def test_document_cannot_fill_an_unconfirmed_material_identity(catalog, changes):
    from domain.contracts import MaterialRecord
    from enrichment.internal_documents import bundle_object_key, load_supplemental_sources
    from pipelines.internal_enrichment import internal_report
    from pipelines.sanitize import analyze_material
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    content = bundle([document(**changes)])
    sources = load_supplemental_sources(content, "dataset-01", catalog, bundle_object_key(content, "dataset-01"))
    target = analyze_material(
        MaterialRecord("t", "ATIVO", "FILTRO OLEO LUBRIFICANTE", manufacturer="FLEETGUARD", reference="LF9009"),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    result = internal_report([target], sources, catalog, "dataset-01")["results"][0]
    assert result["suggestions"] == {}


@pytest.mark.parametrize("group,expected_class", [(None, None), ("TUB01", None), ("SOB01", "PDM110")])
def test_documentary_group_resolves_bucha_only_when_supplied_on_the_document(catalog, group, expected_class):
    from domain.contracts import MaterialRecord
    from enrichment.internal_documents import bundle_object_key, load_supplemental_sources
    from pipelines.internal_enrichment import internal_report
    from pipelines.sanitize import analyze_material
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    supplied_group = {} if group is None else {"merchandise_group": group}
    content = bundle(
        [
            document(
                text="BUCHA; APLICACAO: ESCAVADEIRA HIDRAULICA; MODELO EQUIPAMENTO: 6015B",
                manufacturer="CATERPILLAR",
                manufacturer_reference="5072254",
                **supplied_group,
            )
        ]
    )
    sources = load_supplemental_sources(content, "dataset-01", catalog, bundle_object_key(content, "dataset-01"))
    assert sources[0].material.record.group == (group or "")
    assert sources[0].material.pdm_class_id == expected_class
    target = analyze_material(
        MaterialRecord("t", "ATIVO", "BUCHA", group="SOB01", manufacturer="CATERPILLAR", reference="5072254"),
        catalog,
        get_classification_repository(catalog),
        get_extraction_repository(),
    )
    result = internal_report([target], sources, catalog, "dataset-01")["results"][0]
    assert result["suggestions"] == (
        {"APLICACAO": "ESCAVADEIRA HIDRAULICA", "MODELO EQUIPAMENTO": "6015B"} if expected_class else {}
    )
