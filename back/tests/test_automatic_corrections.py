"""Exemplos reais e recusa de evidência insuficiente/alterada na política automática."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines.automatic_corrections import assess_record
from pipelines.measure_automatic_corrections import candidates
from pipelines.sanitize import read_csv_records
from repositories.proposal_payload import approval_payload

DATA = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def inputs():
    return load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx"), {
        r.code: r for r in read_csv_records(DATA / "01_base_materiais.csv")
    }


def verdict(inputs, code, kind, mutate=None):
    catalog, records = inputs
    record = replace(records[code], database_id="11111111-1111-4111-8111-111111111111")
    proposal = next(p for p in candidates(record, catalog) if p.proposal_type == kind)
    _, changes, _ = approval_payload(proposal, {code: record.database_id}, "22222222-2222-4222-8222-222222222222")
    current = {"unit": record.unit, "ncm": record.ncm or None, "attributes": {}}
    if mutate:
        record, kind = mutate(record, changes, current, kind)
    return assess_record(catalog, record, kind, changes, current, "22222222-2222-4222-8222-222222222222")


@pytest.mark.parametrize(("code", "kind"), [("24794045", "UNIT_CORRECTION"), ("16454102", "PDM_CORRECTION")])
def test_real_positive(inputs, code, kind):
    result = verdict(inputs, code, kind)
    assert result.eligible, result.reasons
    assert result.evidence["classification_evidence"]
    assert result.evidence["original_description"]


@pytest.mark.parametrize(
    "case",
    [
        "unknown_rule",
        "ncm",
        "fiscal",
        "group",
        "factor",
        "packaging",
        "inactive",
        "missing_class",
        "contradiction",
        "review_reason",
        "unknown_type",
        "missing_attribute",
    ],
)
def test_modified_or_unsupported_evidence_never_authorizes(inputs, case):
    def mutate(record, payload, current, kind):
        if case == "unknown_rule":
            payload["changes"][0]["source"] = "unknown_v1"
        elif case == "ncm":
            payload["after"]["ncm"] = "12345678"
        elif case == "fiscal":
            payload["ncm_assessment"] = {"unknown": True}
        elif case == "group":
            payload["after"]["merchandise_group"] = "OTHER"
        elif case == "factor":
            payload["conversions"] = [
                {"from_unit": "PCA", "to_unit": "PC", "factor": "2", "source": "rule_based_v1/unit.alias"}
            ]
        elif case == "packaging":
            record = replace(record, unit="CX")
        elif case == "inactive":
            record = replace(record, status="BLOQUEADO")
        elif case == "missing_class":
            payload["after"]["pdm_class_id"] = None
        elif case == "contradiction":
            current["attributes"] = {"MATERIAL": "CONTRADICAO"}
        elif case == "review_reason":
            payload["review_lane"]["reasons"] = ["UNKNOWN_REASON"]
        elif case == "unknown_type":
            kind = "MERGE"
        elif case == "missing_attribute":
            payload["after"]["attributes"] = {}
        return record, kind

    result = verdict(inputs, "16454102", "PDM_CORRECTION", mutate)
    assert not result.eligible, case


@pytest.mark.parametrize("code", ["24477027", "15487300"])
def test_alias_without_trusted_class_is_human(inputs, code):
    result = verdict(inputs, code, "UNIT_CORRECTION")
    assert not result.eligible and "UNTRUSTED_CLASS" in result.reasons


def test_real_revision_reference_conflict_has_no_pdm_rewrite(inputs):
    from pipelines.sanitize import analyze_material
    from repositories.classification import get_classification_repository
    from repositories.extraction import get_extraction_repository

    catalog, records = inputs
    record = records["15452229"]
    analyzed = analyze_material(record, catalog, get_classification_repository(catalog), get_extraction_repository())
    assert "OBSERVATION_CONFLICT:REFERENCIA FABRICANTE" in analyzed.review_reasons
    assert not any(p.proposal_type == "PDM_CORRECTION" for p in candidates(record, catalog))


def test_revision_text_outside_reference_is_not_discarded(inputs):
    catalog, records = inputs
    record = replace(
        records["15452229"],
        description=records["15452229"].description.replace(" REV A", "") + "; REV A",
        database_id="test",
    )
    proposal = next(p for p in candidates(record, catalog) if p.proposal_type == "PDM_CORRECTION")
    _, payload, _ = approval_payload(proposal, {record.code: record.database_id}, "dataset")
    result = assess_record(
        catalog,
        record,
        "PDM_CORRECTION",
        payload,
        {"unit": record.unit, "ncm": record.ncm, "attributes": {}},
        "dataset",
    )
    assert not result.eligible and "TEXT_LOSS" in result.reasons
    assert "REV" in result.evidence["lost_terms"]


def test_unknown_algorithm_revision_cannot_inherit_authorization(inputs, monkeypatch):
    from pipelines import automatic_corrections
    from repositories.extraction import get_extraction_repository

    extractor = get_extraction_repository()
    extractor.revision = "unreviewed-revision"
    monkeypatch.setattr(automatic_corrections, "get_extraction_repository", lambda: extractor)
    result = verdict(inputs, "24794045", "UNIT_CORRECTION")
    assert not result.eligible and "UNTRUSTED_CLASS" in result.reasons


def test_unknown_classifier_revision_cannot_inherit_authorization(inputs, monkeypatch):
    from pipelines import automatic_corrections
    from repositories.classification import get_classification_repository

    classifier = get_classification_repository(inputs[0])
    classifier.revision = "unreviewed-revision"
    monkeypatch.setattr(automatic_corrections, "get_classification_repository", lambda _: classifier)
    result = verdict(inputs, "24794045", "UNIT_CORRECTION")
    assert not result.eligible and "UNTRUSTED_CLASS" in result.reasons


def test_unknown_field_reader_revision_cannot_inherit_authorization(inputs, monkeypatch):
    from pipelines import automatic_corrections

    monkeypatch.setattr(automatic_corrections, "MATERIAL_FIELDS_VERSION", "unreviewed-fields", raising=False)
    result = verdict(inputs, "24794045", "UNIT_CORRECTION")
    assert not result.eligible and "UNTRUSTED_CLASS" in result.reasons


@pytest.mark.parametrize(
    ("description", "group"),
    [
        ("PARAF SEXTAVADO METRICA GROSSA M12X50 8.8 ACO CARBONO NATURAL DIN 933", "FIX01"),
        ("PARAFUSO SEXT. INTERNO, M12X50 12.9 ACO LIGA OXIDADO PRETO CILINDRICA", "FIX01"),
        ("FLG ENCAIXE SW 2POL 300# RF A182 F316 ASME B16.5", "TUB01"),
        ("PLACA TRASERA METSO PN MM4504436 BOMBA POLPA MM400", "SOB01"),
        ("BUCHA GUIA MANCAL KSB PN 123456 BOMBA CENTRIFUGA", "SOB01"),
    ],
)
def test_pilot_aliases_remain_in_human_review(inputs, description, group):
    from domain.contracts import MaterialRecord

    catalog, _ = inputs
    record = MaterialRecord("pilot", "ATIVO", description, group=group, unit="PCA", database_id="test")
    proposal = next(p for p in candidates(record, catalog) if p.proposal_type == "UNIT_CORRECTION")
    _, payload, _ = approval_payload(proposal, {record.code: record.database_id}, "dataset")
    result = assess_record(
        catalog, record, "UNIT_CORRECTION", payload, {"unit": "PCA", "ncm": None, "attributes": {}}, "dataset"
    )
    assert not result.eligible and "UNTRUSTED_CLASS" in result.reasons


def test_short_only_attributes_are_traced_and_require_human_pdm_review(inputs):
    catalog, records = inputs
    record = replace(
        records["16454102"],
        description="ANEL O-RING DIAMETRO DE 15MM, COM SECAO TRANSV 2 MM, NBR",
        short_description="DUREZA: 70 SHORE A",
        database_id="test",
    )
    proposal = next(p for p in candidates(record, catalog) if p.proposal_type == "PDM_CORRECTION")
    _, payload, _ = approval_payload(proposal, {record.code: record.database_id}, "dataset")
    result = assess_record(
        catalog,
        record,
        "PDM_CORRECTION",
        payload,
        {"unit": record.unit, "ncm": record.ncm, "attributes": {}},
        "dataset",
    )
    assert not result.eligible
    assert "SHORT_DESCRIPTION_REQUIRES_REVIEW" in result.evidence["pending"]
    assert result.evidence["attribute_evidence"]["DUREZA"]["source_field"] == "short_description"
    assert result.evidence["original_short_description"] == record.short_description
