import copy
import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import cli
from domain.contracts import ClassificationInput, ClassificationStatus, PdmCatalog
from domain.pdm_loader import load_pdm
from pipelines.classify import classification_evaluation, classification_report
from repositories import classification
from repositories.classification import REPOSITORIES, get_classification_repository
from repositories.classification.rule_based_v1 import RuleBasedV1ClassificationRepository

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = KIT / "03_padrao_cadastro_PDM.xlsx"
SAMPLE = Path(__file__).parent / "fixtures" / "classification_review.json"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


@pytest.fixture(params=sorted(REPOSITORIES))
def repository(request, catalog):
    return get_classification_repository(catalog, request.param)


def test_contract_recognizes_every_canonical_class(repository, catalog):
    before = copy.deepcopy(catalog)
    for pdm_class in catalog.classes.values():
        item = ClassificationInput(pdm_class.item_names[0], merchandise_group=pdm_class.group)
        result = repository.classify(item)
        assert result.status is ClassificationStatus.CLASSIFIED
        assert result.pdm_class_id == pdm_class.id
        assert result.candidate_class_ids == (pdm_class.id,)
        assert result.original == item
        assert result.pdm_version == catalog.version
        assert result.pdm_source_sha256 == catalog.source_sha256
        assert result.rule.startswith(repository.name + "/")
        assert result.evidence
        assert all(e.rule.startswith(repository.name + "/") for e in result.evidence)
        assert repository.classify(item) == result
    assert catalog == before


@pytest.mark.parametrize("description", [None, "", "   "])
def test_contract_missing_text_is_unresolved_even_with_group(repository, description):
    result = repository.classify(ClassificationInput(description, merchandise_group="FIX01"))
    assert result.status is ClassificationStatus.UNRESOLVED
    assert result.pdm_class_id is None


@pytest.mark.parametrize("description", ["Cadeira escritorio giratoria", "Notebook 16GB", "Cafe em po 500g"])
def test_contract_outside_products_are_not_forced_by_group(repository, description):
    result = repository.classify(ClassificationInput(description, merchandise_group="FIX01"))
    assert result.status is ClassificationStatus.OUT_OF_SCOPE
    assert result.pdm_class_id is None
    assert result.candidate_class_ids == ()


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (ClassificationInput("Preciso de uma válvula de esfera 2POL"), "PDM040"),
        (ClassificationInput("PARAFUSO SEXTAVADO INTERNO M12X50"), "PDM002"),
        (ClassificationInput("MANGUEIRA HIDRAULICA MONTADA 1POL"), "PDM011"),
        (ClassificationInput("BUCHA REDUCAO 2POL", merchandise_group="TUB01"), "PDM050"),
        (ClassificationInput("LUVA SEGURANCA RASPA"), "PDM070"),
        (ClassificationInput("LUVA EIXO METSO MM1830058"), "PDM110"),
        (ClassificationInput("CONTRAEIXO BRITADOR", merchandise_group="FIL01"), "PDM110"),
        (
            ClassificationInput("Segue ficha tecnica", attachment_text="Produto: Retentor\nDiametro eixo: 60 mm"),
            "PDM032",
        ),
        (ClassificationInput("RETENTOR diametro eixo 60mm"), "PDM032"),
        (ClassificationInput("ELETRODO REVESTIDO;REVESTIMENTO:BASICO"), "PDM080"),
        (ClassificationInput(None, short_description="PORCA M12"), "PDM003"),
        (ClassificationInput("TE 90 GRAUS", merchandise_group="TUB01"), "PDM050"),
    ],
)
def test_contract_classification_uses_names_and_attachment(repository, item, expected):
    result = repository.classify(item)
    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.pdm_class_id == expected
    assert result.original == item


@pytest.mark.parametrize(
    "item",
    [
        ClassificationInput("PARAFUSO M12"),
        ClassificationInput("LUVA"),
        ClassificationInput("BUCHA"),
        ClassificationInput("TE envio o pedido"),
        ClassificationInput("VALVULA ESFERA E VALVULA GAVETA", merchandise_group="VAL01"),
        ClassificationInput("PORCA M12", short_description="ARRUELA LISA M12"),
        ClassificationInput("PORCA M12", attachment_text="Produto: Retentor"),
        ClassificationInput("VALVULA;MATERIAL:ESFERA"),
    ],
)
def test_contract_ambiguity_never_picks_a_class(repository, item):
    result = repository.classify(item)
    assert result.status is ClassificationStatus.UNRESOLVED
    assert result.pdm_class_id is None
    assert result.candidate_class_ids


def test_attribute_label_and_substring_do_not_identify_products(repository):
    for text in ["RET., B1, DIAMETRO EIXO:22MM", "SUPORCA", "CONTATORIA", "DIAM EIXO 60MM"]:
        result = repository.classify(ClassificationInput(text))
        assert result.pdm_class_id is None


def test_contradictory_group_is_evidence_not_authority(repository):
    result = repository.classify(ClassificationInput("PORCA M12", merchandise_group="TRA01"))
    assert result.pdm_class_id == "PDM003"
    assert any(e.rule.endswith("group.mismatch") for e in result.evidence)


def test_equal_names_in_two_classes_remain_ambiguous(catalog):
    first = catalog.classes["PDM003"]
    second = replace(first, id="OTHER")
    custom = PdmCatalog(catalog.version, catalog.source_sha256, {first.id: first, second.id: second})
    for factory in REPOSITORIES.values():
        result = factory(custom).classify(ClassificationInput("PORCA M12", merchandise_group="FIX01"))
        assert result.pdm_class_id is None
        assert result.candidate_class_ids == ("OTHER", "PDM003")


def test_an_alternative_is_selectable_without_removing_the_first(catalog, monkeypatch):
    class Alternative(RuleBasedV1ClassificationRepository):
        name = "alternative"

    monkeypatch.setitem(classification.REPOSITORIES, "alternative", Alternative)
    monkeypatch.setenv("CLASSIFICATION_REPOSITORY", "alternative")
    assert get_classification_repository(catalog).name == "alternative"
    assert get_classification_repository(catalog, "rule_based_v1").name == "rule_based_v1"
    with pytest.raises(ValueError, match="alternative, rule_based_v1"):
        get_classification_repository(catalog, "unknown")


def test_cli_keeps_each_record_and_original_input(tmp_path, capsys):
    path = tmp_path / "materials.csv"
    path.write_text(
        "\ufeffCODIGO_MATERIAL,DESCRICAO_LONGA,DESCRICAO_CURTA,GRUPO_MERCADORIA\n"
        "123,PORCA M12,PORCA,FIX01\n123,Cadeira escritorio,,FIX01\n",
        encoding="utf-8",
    )
    original = path.read_bytes()
    assert cli.main(["classification-report", str(path), "--input-kind", "materials", "--pdm-workbook", str(PDM)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rows"] == 2
    assert report["input_sha256"] == hashlib.sha256(original).hexdigest()
    assert [r["source_record"] for r in report["items"]] == [2, 3]
    assert [r["pdm_class_id"] for r in report["items"]] == ["PDM003", None]
    assert report["items"][0]["original"]["description"] == "PORCA M12"
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("kind", "filename", "rows"),
    [("materials", "01_base_materiais.csv", 23554), ("orders", "02_pedidos_cadastro.csv", 520)],
)
def test_whole_kit_has_a_result_for_every_input(kind, filename, rows):
    path = KIT / filename
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    report = classification_report(str(path), str(PDM), kind)
    assert report["rows"] == rows
    assert sum(report["counts"].values()) == rows
    assert sum(report["classes"].values()) == report["counts"]["CLASSIFIED"]
    for result in report["items"]:
        assert (result["pdm_class_id"] is not None) == (result["status"] == "CLASSIFIED")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original


def test_missing_csv_columns_are_reported(tmp_path):
    path = tmp_path / "wrong.csv"
    path.write_text("id,description\n1,PORCA\n")
    with pytest.raises(ValueError, match="Colunas ausentes"):
        classification_report(str(path), str(PDM), "orders")


def test_review_labels_preserve_actual_kit_rows():
    sources = {}
    for kind, filename, key in [
        ("materials", "01_base_materiais.csv", "CODIGO_MATERIAL"),
        ("orders", "02_pedidos_cadastro.csv", "ID_PEDIDO"),
    ]:
        with (KIT / filename).open(encoding="utf-8-sig", newline="") as source:
            sources[kind] = {row[key]: row for row in csv.DictReader(source)}
    sample = json.loads(SAMPLE.read_text())
    for case in sample["cases"]:
        row = sources[case["source_kind"]][case["id"]]
        expected = (
            ClassificationInput(row["DESCRICAO_LONGA"], row["DESCRICAO_CURTA"], row["GRUPO_MERCADORIA"])
            if case["source_kind"] == "materials"
            else ClassificationInput(row["TEXTO_SOLICITACAO"], attachment_text=row["CONTEUDO_ANEXO"])
        )
        assert ClassificationInput(**case["input"]) == expected
        assert case["review_note"]


def test_evaluation_measures_both_precision_and_abstention(repository, capsys):
    assert (
        cli.main(["classification-evaluate", str(SAMPLE), "--pdm-workbook", str(PDM), "--repository", repository.name])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    predicted = [item for item in report["items"] if item["predicted_class_id"] is not None]
    correct = [item for item in predicted if item["predicted_class_id"] == item["expected_class_id"]]
    assert report["precision"] == len(correct) / len(predicted)
    assert report["coverage"] == len(predicted) / report["reviewed_items"]
    assert report["coverage"] < 1
    assert report["correct_out_of_scope"] > 0
    assert report["false_out_of_scope"] > 0


def test_empty_evaluation_has_no_invented_precision(tmp_path):
    sample = tmp_path / "empty.json"
    sample.write_text(json.dumps({"cases": [], "label_method": "Amostra vazia"}))
    report = classification_evaluation(str(sample), str(PDM))
    assert report["precision"] is None
    assert report["coverage"] is None
    assert report["in_scope_recall"] is None
