"""Aliases que completariam o valor só valem com evidência no texto (#158).

Cada linha real foi lida à mão. `ROSCA GROSSA` pode ser métrica ou UNC no parafuso (PDM001 aceita as
duas), e `BLINDADO` não diz se a blindagem é dos dois lados: sem bitola métrica ou sem ZZ/2Z o campo
fica vazio. Com a evidência, o valor continua sendo reconhecido.
"""

from pathlib import Path

import pytest

from domain.pdm_loader import load_pdm
from pipelines.sanitize import read_csv_records
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def records():
    return {record.code: record for record in read_csv_records(KIT / "01_base_materiais.csv")}


def extract(catalog, class_id, text, reference=None):
    return get_extraction_repository().extract(catalog.classes[class_id], text, manufacturer_reference=reference)


# Rosca escrita sem nenhuma bitola: pode ser métrica ou UNC/UNF.
@pytest.mark.parametrize("code", ["29878298", "26323422", "22872566", "14943072", "19083115"])
def test_thread_without_gauge_stays_empty_in_bolts(catalog, records, code):
    result = extract(catalog, "PDM001", records[code].description)

    assert "ROSCA" not in result.attributes


# Com bitola métrica (M14, M6X25, M 8X40, M12X1,5) a rosca escrita continua reconhecida.
@pytest.mark.parametrize(
    ("code", "thread"),
    [
        ("12168946", "METRICA GROSSA"),
        ("18949601", "METRICA GROSSA"),
        ("24353197", "METRICA GROSSA"),
        ("15133460", "METRICA FINA"),
    ],
)
def test_thread_with_metric_gauge_is_kept(catalog, records, code, thread):
    assert extract(catalog, "PDM001", records[code].description).attributes["ROSCA"].value == thread


def test_nut_class_without_imperial_threads_keeps_alias(catalog, records):
    # PDM003 só aceita roscas métricas: ROSCA GROSSA não tem outra leitura.
    assert extract(catalog, "PDM003", records["18066518"].description).attributes["ROSCA"].value == "METRICA GROSSA"


def test_written_metric_thread_never_needs_evidence(catalog):
    result = extract(catalog, "PDM001", "PARAFUSO SEXTAVADO, ROSCA: METRICA GROSSA, COMP: 50MM, CLASSE: 8.8")

    assert result.attributes["ROSCA"].value == "METRICA GROSSA"


# Rolamentos reais com BLINDADO e ZZ na referência: a blindagem dos dois lados está escrita.
@pytest.mark.parametrize("code", ["17011188", "23585941", "11018373"])
def test_shielded_bearing_with_zz_is_both_sides(catalog, records, code):
    record = records[code]
    result = extract(catalog, "PDM020", record.description, record.reference)

    assert result.attributes["VEDACAO"].value == "METALICA AMBOS LADOS"


def test_shielded_bearing_without_zz_stays_empty_not_open(catalog):
    # Variação do 23585941 sem o sufixo: nem dois lados nem aberto, que contradiria BLINDADO.
    text = "ROLAMENTO RIGIDO ESFERAS, VED:BLINDADO, DI:20MM, L:12MM, MODELO:6004, FOLGA:NORMAL"
    result = extract(catalog, "PDM020", text)

    assert "VEDACAO" not in result.attributes
    assert result.attributes["FOLGA"].value == "NORMAL"


def test_bearing_suffix_still_infers_seal_without_written_seal(catalog):
    result = extract(catalog, "PDM020", "ROLAMENTO RIGIDO ESFERAS, DI:20MM, L:12MM, MODELO:6004-2RS")

    assert result.attributes["VEDACAO"].value == "BORRACHA AMBOS LADOS"


def test_boot_type_needs_the_closure(catalog, records):
    # "BOTINA" sozinha pode ser com cadarço ou elástico; o tipo escrito por inteiro continua valendo.
    assert "TIPO" not in extract(catalog, "PDM071", "CALCADO SEGURANCA, TIPO: EPI BOTINA, NUMERO: 40").attributes
    assert extract(catalog, "PDM071", records["19602505"].description).attributes["TIPO"].value == "BOTINA CADARCO"


@pytest.mark.parametrize(
    ("gauge", "extra", "thread"),
    [
        ("BITOLA:1/2POL, ", "REF:M1234", "GROSSA"),
        ("BITOLA:1/2POL, ", "MODELO:M12", "GROSSA"),
        ("BITOLA:1/2POL, ", "OBS:MA", "GROSSA"),
        ("", "REF:M1234", "GROSSA"),
        ("", "REF:MA", "GROSSA"),
        ("", "MODELO:MF", "FINA"),
    ],
)
def test_metric_looking_metadata_never_supplies_a_gauge(catalog, gauge, extra, thread):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, {gauge}ROSCA:ROSCA {thread}, {extra}")
    if gauge:
        assert result.attributes["BITOLA"].value == "1/2POL"
    assert "ROSCA" not in result.attributes


@pytest.mark.parametrize(("tag", "thread"), [("MA", "GROSSA"), ("MF", "FINA")])
@pytest.mark.parametrize("metadata", ["", ", PN:M12"])
def test_metric_standard_marker_is_scoped_to_the_thread_field(catalog, tag, thread, metadata):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, ROSCA:ROSCA {thread} {tag}{metadata}")
    assert result.attributes["ROSCA"].value == f"METRICA {thread}"


@pytest.mark.parametrize("reference", ["6004ZZ", "6004ZZ/C3"])
def test_compact_valid_bearing_suffix_keeps_explicit_shielding(catalog, reference):
    text = f"ROLAMENTO RIGIDO ESFERAS, VED:BLINDADO, DI:20MM, L:12MM, MODELO:{reference}"
    result = extract(catalog, "PDM020", text)
    assert "-ZZ" in result.attributes["REFERENCIA"].value
    assert result.attributes["VEDACAO"].value == "METALICA AMBOS LADOS"


@pytest.mark.parametrize(("tag", "thread"), [("MA", "GROSSA"), ("MF", "FINA")])
def test_imperial_gauge_vetoes_metric_marker_even_in_thread_field(catalog, tag, thread):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, BITOLA:1/2POL, ROSCA:ROSCA {thread} {tag}")
    assert result.attributes["BITOLA"].value == "1/2POL"
    assert "ROSCA" not in result.attributes


@pytest.mark.parametrize("metadata", ["REF:MA", "PN:MF", "MODELO:MA"])
def test_adjacent_metadata_label_does_not_supply_thread_marker(catalog, metadata):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, ROSCA:ROSCA GROSSA {metadata}")
    assert "ROSCA" not in result.attributes


@pytest.mark.parametrize("reference", ["M1234", "ROSCA:MA", "ROSCA:ROSCA GROSSA MA"])
def test_structured_reference_does_not_supply_thread_marker(catalog, reference):
    result = extract(catalog, "PDM001", "PARAFUSO SEXTAVADO, ROSCA:ROSCA GROSSA", reference)
    assert "ROSCA" not in result.attributes


@pytest.mark.parametrize("label", ["PN", "REF", "MODELO"])
@pytest.mark.parametrize("value", ["M12", "ABC M12"])
def test_valid_metric_reference_does_not_authorize_thread_alias(catalog, label, value):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, ROSCA:ROSCA GROSSA, {label}:{value}")
    assert "ROSCA" not in result.attributes


@pytest.mark.parametrize("gauge", ["M12", "BITOLA:M12", "REF:M12, M12", "REF:M12, BITOLA:M12", "REF:M12 BITOLA M12"])
def test_physical_metric_gauge_still_authorizes_thread_alias(catalog, gauge):
    result = extract(catalog, "PDM001", f"PARAFUSO SEXTAVADO, ROSCA:ROSCA GROSSA, {gauge}")
    assert result.attributes["ROSCA"].value == "METRICA GROSSA"
