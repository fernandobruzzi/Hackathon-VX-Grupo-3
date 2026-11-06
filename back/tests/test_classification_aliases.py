"""Aliases técnicos antes da busca de nomes (#86), atravessando classificação e extração.

As linhas da base foram conferidas à mão: o texto descreve o produto da classe esperada, e os
casos negativos mostram onde o alias não pode agir.
"""

import csv
from pathlib import Path

import pytest

from domain.contracts import ClassificationInput, ClassificationStatus
from domain.pdm_loader import load_pdm
from repositories.classification import DEFAULT_REPOSITORY, get_classification_repository
from repositories.classification.aliases_v1 import expand
from repositories.extraction import get_extraction_repository

KIT = Path(__file__).parents[2] / "data" / "desafio01"
PDM = KIT / "03_padrao_cadastro_PDM.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(PDM)


@pytest.fixture(scope="module")
def aliases(catalog):
    return get_classification_repository(catalog, "aliases_v1")


@pytest.fixture(scope="module")
def previous(catalog):
    return get_classification_repository(catalog, "rule_based_v1")


@pytest.fixture(scope="module")
def rows():
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="") as source:
        return {row["CODIGO_MATERIAL"]: row for row in csv.DictReader(source)}


def material(rows, code):
    row = rows[code]
    return ClassificationInput(row["DESCRICAO_LONGA"], row["DESCRICAO_CURTA"], row["GRUPO_MERCADORIA"])


def alias_evidence(result):
    return {(e.source_field, e.matched_name, e.rule) for e in result.evidence if "/alias." in e.rule}


def test_aliases_are_the_default_and_the_previous_rules_stay_selectable(catalog):
    assert DEFAULT_REPOSITORY == "aliases_v1"
    assert get_classification_repository(catalog, "rule_based_v1").name == "rule_based_v1"


def test_valv_esf_identifies_ball_valve_and_keeps_original_text(aliases, previous):
    item = ClassificationInput('VALV ESF 2" AISI 316 NPT')
    assert previous.classify(item).status == ClassificationStatus.OUT_OF_SCOPE

    result = aliases.classify(item)
    assert (result.status, result.pdm_class_id) == (ClassificationStatus.CLASSIFIED, "PDM040")
    assert result.original == item
    assert alias_evidence(result) == {("description", "VALV ESF", "aliases_v1/alias.valvula_esfera")}


def test_valv_esf_extraction_does_not_invent_body_material(aliases, catalog):
    """Classificação e extração no mesmo fluxo: AISI 316 não diz se o corpo é forjado ou fundido."""
    text = 'VALV ESF 2" AISI 316 NPT'
    result = aliases.classify(ClassificationInput(text))
    extracted = get_extraction_repository().extract(catalog.classes[result.pdm_class_id], text)
    assert {name: value.value for name, value in extracted.attributes.items()} == {
        "DIAMETRO NOMINAL": "2POL",
        "CONEXAO": "ROSCA NPT",
    }
    assert "MATERIAL CORPO" not in extracted.attributes


@pytest.mark.parametrize(
    ("code", "expected", "before"),
    [
        # VALV ESF, DIAMETRO NOMINAL:2POL, CL:800#, CORPO:ACO CARBONO, RSC NPT, PASSAGEM:PLENA...
        ("26301283", "PDM040", ClassificationStatus.OUT_OF_SCOPE),
        # VALV. BORBOLETA, DIAMETRO: 2 IN, TIPO CORPO: WAFER, CORPO: FOFO NODULAR...
        ("20196119", "PDM044", ClassificationStatus.OUT_OF_SCOPE),
        # ELEMENTO FILTRANTE AR - FLEETGUARD - PN AF51124
        ("15063326", "PDM100", ClassificationStatus.OUT_OF_SCOPE),
        # ELEMENTO FILTRANTE OLEO LUBRIFICANTE COM FABR MANN, P/N W 524/90: antes virava OLEO LUBRIFICANTE.
        ("20496122", "PDM100", ClassificationStatus.CLASSIFIED),
    ],
)
def test_real_rows_reach_the_class_they_describe(rows, aliases, previous, code, expected, before):
    item = material(rows, code)
    assert previous.classify(item).status == before
    result = aliases.classify(item)
    assert (result.status, result.pdm_class_id) == (ClassificationStatus.CLASSIFIED, expected)
    assert alias_evidence(result)


def test_filter_oil_element_is_no_longer_read_as_lubricating_oil(rows, aliases, previous):
    item = material(rows, "20496122")
    assert previous.classify(item).pdm_class_id == "PDM090"
    assert aliases.classify(item).pdm_class_id == "PDM100"


def test_generic_filter_element_asks_instead_of_forcing_a_type(aliases):
    """Sem o tipo (AR, OLEO...), o pedido fica sem classe, com os filtros como candidatos."""
    result = aliases.classify(ClassificationInput("ELEMENTO FILTRANTE FLEETGUARD LF9009"))
    assert result.status == ClassificationStatus.UNRESOLVED
    assert result.pdm_class_id is None
    assert "PDM100" in result.candidate_class_ids
    assert ("description", "ELEMENTO FILTRANTE", "aliases_v1/alias.elemento_filtrante") in alias_evidence(result)


def test_valve_with_flange_end_now_abstains_instead_of_becoming_a_fitting(rows, aliases, previous):
    # VALV GAVETA ... EXTREMIDADES:FLANGE RF: antes virava FLANGE (conexão). Válvula e flange no mesmo
    # texto ficam em dúvida, que é melhor que uma classe errada.
    item = material(rows, "28526811")
    assert previous.classify(item).pdm_class_id == "PDM050"
    result = aliases.classify(item)
    assert result.status == ClassificationStatus.UNRESOLVED
    assert {"PDM041", "PDM050"} <= set(result.candidate_class_ids)


@pytest.mark.parametrize(
    "item",
    [
        # ROLAMENTO RIGIDO ESF: ESF fora de válvula não é expandido.
        ClassificationInput("ROLAMENTO RIGIDO ESF; REF:6209-ZZ C3; DIAMETRO INTERNO:45MM", "ROL RIGIDO ESF REF 6209"),
        ClassificationInput("ELEMENTO AQUECEDOR 220V 2000W"),
        ClassificationInput("VALVULA SEGURANCA 1POL 150#"),
    ],
)
def test_negative_examples_are_not_rewritten_into_a_class(aliases, previous, item):
    before, after = previous.classify(item), aliases.classify(item)
    assert (after.status, after.pdm_class_id) == (before.status, before.pdm_class_id)
    assert after.pdm_class_id is None
    assert not alias_evidence(after) or after.status != ClassificationStatus.CLASSIFIED


def test_unresolved_valve_abbreviation_stays_a_question(rows, aliases):
    # VALV. RET: RET não é expandido, então o tipo da válvula continua em aberto.
    result = aliases.classify(material(rows, "11056660"))
    assert result.status == ClassificationStatus.UNRESOLVED
    assert {"PDM040", "PDM043"} <= set(result.candidate_class_ids)


def test_expand_is_a_single_left_to_right_pass():
    words, used = expand(("VALV", "ESF", "VALV", "GLOBO", "ESF"))
    assert words == ("VALVULA", "ESFERA", "VALVULA", "GLOBO", "ESF")
    assert [alias.id for alias in used] == ["valvula_esfera", "valvula"]


@pytest.mark.parametrize(
    ("code", "expected", "alias"),
    [
        # RET., B1, DIAM ALOJ: 37MM, DIAMETRO EIXO: 22MM, MATERIAL: NBR: retentor (gabarito, #204).
        ("11287821", "PDM032", "retentor"),
        # RET. 110MM 15MM BASL NBR: retentor, mesmo com o grupo TUB01 divergente.
        ("12711820", "PDM032", "retentor"),
        # CONT AC3 65A COM TENSAO COMANDO 24VCC: contator.
        ("22071112", "PDM063", "contator"),
        # LAMP LED TUBULAR T8 9 W 220V G13 5000K: lâmpada LED.
        ("17321551", "PDM065", "lampada_led"),
        # FILT AR, PART NUMBER: CA95120, FAB: FRAM: filtro de ar.
        ("20019238", "PDM100", "filtro"),
        # O-RING, SECAO TRANSV:2MM, FKM (VITON): anel O-ring.
        ("13031016", "PDM031", "anel_o_ring"),
    ],
)
def test_abbreviations_reach_the_class_they_describe(rows, aliases, previous, code, expected, alias):
    item = material(rows, code)
    assert previous.classify(item).status == ClassificationStatus.OUT_OF_SCOPE
    result = aliases.classify(item)
    assert (result.status, result.pdm_class_id) == (ClassificationStatus.CLASSIFIED, expected)
    assert f"aliases_v1/alias.{alias}" in {rule for _, _, rule in alias_evidence(result)}
    assert result.original == item


def test_ball_valve_in_an_english_catalog_line_is_a_ball_valve(aliases):
    # Pedido SC-202600016, como veio: o nome do produto está só no anexo, em inglês.
    item = ClassificationInput(
        "Novo item, linha do catálogo abaixo.",
        attachment_text="Generic | Ball valve | 1POL, 150#, A216 WCB, RF flanged, reduced bore, metal-metal, lever",
    )
    result = aliases.classify(item)
    assert (result.status, result.pdm_class_id) == (ClassificationStatus.CLASSIFIED, "PDM040")
    assert ("attachment_text", "BALL VALVE", "aliases_v1/alias.valvula_esfera") in alias_evidence(result)


def test_oil_seal_with_shaft_label_is_no_longer_read_as_a_shaft(rows, aliases, previous):
    # RET., EIXO:60MM ...: antes virava a peça EIXO (sobressalente). Retentor e EIXO no mesmo texto
    # ficam em dúvida, que é melhor que a classe errada.
    item = material(rows, "28845043")
    assert previous.classify(item).pdm_class_id == "PDM110"
    result = aliases.classify(item)
    assert result.status == ClassificationStatus.UNRESOLVED
    assert {"PDM032", "PDM110"} <= set(result.candidate_class_ids)


def test_check_valve_ret_is_not_an_oil_seal(rows, aliases):
    # VALV. RET: RET depois de válvula é retenção, não retentor.
    result = aliases.classify(material(rows, "11056660"))
    assert result.pdm_class_id != "PDM032"
    assert "PDM032" not in result.candidate_class_ids


def test_tensioning_rod_synonym_stays_unchanged(rows, aliases, previous):
    # VERGALHAO TENSORA é sinônimo, não abreviação: continua como antes, para revisão humana.
    item = material(rows, "20095446")
    before, after = previous.classify(item), aliases.classify(item)
    assert (after.status, after.pdm_class_id) == (before.status, before.pdm_class_id)


def test_context_rules_of_the_new_aliases():
    # RET e CONT só no começo do campo; O RING só quando ANEL não vem antes.
    assert expand(("VALV", "RET", "2POL"))[0] == ("VALVULA", "RET", "2POL")
    assert expand(("ROLETE", "TRANSPORTADORA", "CONT"))[0] == ("ROLETE", "TRANSPORTADORA", "CONT")
    assert expand(("RET", "BASL"))[0] == ("RETENTOR", "BASL")
    assert expand(("ANEL", "O", "RING", "20X2")) == (("ANEL", "O", "RING", "20X2"), [])
    assert expand(("O", "RING", "20X2"))[0] == ("ANEL", "O", "RING", "20X2")
