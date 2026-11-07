"""Dois pontos num rótulo inline não apagam as medidas anteriores."""

from pathlib import Path

import pytest

from domain.contracts import MaterialRecord
from domain.pdm_loader import load_pdm
from pipelines.import_orders import analyze_order, read_orders
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.extraction.rule_based_v1 import RuleBasedV1ExtractionRepository

KIT = Path(__file__).parents[2] / "data/desafio01"
EXPECTED = {
    "ROSCA": "METRICA GROSSA",
    "BITOLA": "M12",
    "COMPRIMENTO": "50MM",
    "CLASSE RESISTENCIA": "8.8",
    "MATERIAL": "ACO CARBONO",
    "ACABAMENTO": "ZINCADO BRANCO",
    "NORMA": "DIN 933",
}


@pytest.fixture(scope="module")
def pdm_class():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx").classes["PDM001"]


@pytest.mark.parametrize(
    "text",
    [
        "parafuso sextavado M12 x 50 classe 8.8 aco carbono zincado branco DIN 933",
        "parafuso sextavado M12 x 50 classe: 8.8 aco carbono zincado branco DIN 933",
        "parafuso sextavado M12 x 50 classe resistencia: 8.8 aco carbono zincado branco DIN 933.",
        "parafuso sextavado M12 x 50 classe: 8.8 material: aco carbono acabamento: zincado branco norma: DIN 933",
        "BITOLA M12 x 50 classe: 8.8 aco carbono zincado branco DIN 933",
        "CLASSE: 8.8; parafuso sextavado M12 x 50 aco carbono zincado branco DIN 933",
        "parafuso sextavado M12 x 50\n- classe: 8.8\n- material: aco carbono\n"
        "- acabamento: zincado branco\n- norma: DIN 933.",
    ],
)
def test_inline_label_keeps_all_seven_attributes_and_evidence(pdm_class, text):
    result = RuleBasedV1ExtractionRepository().extract(pdm_class, text)
    assert {name: attribute.value for name, attribute in result.attributes.items()} == EXPECTED
    assert all(attribute.original and attribute.rule for attribute in result.attributes.values())


def test_generic_finish_and_dotted_standard_are_never_completed(pdm_class):
    result = RuleBasedV1ExtractionRepository().extract(
        pdm_class,
        "parafuso sextavado M12 x 50 classe: 8.8 aco carbono zincado DIN 931.1",
    )
    assert result.attributes["CLASSE RESISTENCIA"].value == "8.8"
    assert result.attributes["BITOLA"].value == "M12"
    assert result.attributes["COMPRIMENTO"].value == "50MM"
    assert "ACABAMENTO" not in result.attributes
    assert "NORMA" not in result.attributes


def test_batch_analysis_preserves_the_original_text_and_identity():
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    text = "PARAFUSO SEXTAVADO M12 X 50 CLASSE: 8.8 ACO CARBONO ZINCADO BRANCO DIN 933"
    record = MaterialRecord("000198", "ATIVO", text, unit="PC", ncm="73181500")
    result = analyze_material(
        record, catalog, get_classification_repository(catalog), RuleBasedV1ExtractionRepository()
    )
    assert result.attributes == EXPECTED
    assert result.identity_key is not None
    assert result.record.description == text


@pytest.mark.parametrize(
    "order_id,reference",
    [
        ("SC-202600006", "N59815007"),
        ("SC-202600009", "LE 1380"),
        ("SC-202600287", None),
    ],
)
def test_real_manufacturer_headers_never_turn_connectors_into_references(order_id, reference):
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    row = next(r for r in read_orders((KIT / "02_pedidos_cadastro.csv").read_bytes()) if r.source_order_id == order_id)
    result = analyze_order(row, catalog, get_classification_repository(catalog), RuleBasedV1ExtractionRepository())
    assert result.attributes.get("REFERENCIA FABRICANTE") == reference


@pytest.mark.parametrize(
    "code,conductors",
    [
        ("27406104", "1"),
        ("29181674", "3"),
        ("19387950", "2"),
        ("18347105", "1"),
    ],
)
def test_real_cables_keep_the_explicit_conductor_quantity(code, conductors):
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    record = next(r for r in read_csv_records(str(KIT / "01_base_materiais.csv")) if r.code == code)
    result = analyze_material(
        record, catalog, get_classification_repository(catalog), RuleBasedV1ExtractionRepository()
    )
    assert result.pdm_class_id == "PDM060"
    assert result.attributes["NUMERO CONDUTORES"] == conductors
    assert result.record == record


@pytest.mark.parametrize(
    "order_id,reference,original_text",
    [
        (
            "SC-202600031",
            "2713243123",
            "Item amortecedor FLSMIDTH 2713243123 do LUDOWICI 3.6X8.5, código do fabricante na plaqueta",
        ),
        (
            "SC-202600048",
            "6644889826",
            "Peça tela FLSMIDTH 6644889826 do LUDOWICI 3.6X8.5, código do fabricante na plaqueta",
        ),
        (
            "SC-202600416",
            "N72836H06",
            "Peça viga METSO N72836H06 do LH 8X20, código do fabricante na plaqueta",
        ),
        (
            "SC-202600451",
            "497-9544",
            "Preciso de pino CATERPILLAR 497-9544 do 6030, código do fabricante na plaqueta",
        ),
        (
            "SC-202600481",
            None,
            "Peça viga HAVER HB-798945 do T-CLASS 3.0X7.3, código do fabricante na plaqueta",
        ),
        (
            "SC-202600497",
            "87796744",
            "Item rotor KSB 87796744 do MEGANORM 100-315, código do fabricante na plaqueta",
        ),
    ],
)
def test_real_compound_manufacturer_headers_preserve_order_evidence(order_id, reference, original_text):
    catalog = load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")
    source = KIT / "02_pedidos_cadastro.csv"
    content = source.read_bytes()
    row = next(r for r in read_orders(content) if r.source_order_id == order_id)
    assert row.original_text == original_text
    assert row.attachment_text is None

    result = analyze_order(row, catalog, get_classification_repository(catalog), RuleBasedV1ExtractionRepository())

    assert result.attributes.get("REFERENCIA FABRICANTE") == reference
    assert result.status == "INCOMPLETE"
    assert result.identity_key is None
    assert row.original_text == original_text
    assert row.attachment_text is None
    assert source.read_bytes() == content
