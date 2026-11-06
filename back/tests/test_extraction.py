from pathlib import Path

import pytest

from domain.identity import build_identity_key
from domain.pdm_loader import load_pdm
from domain.pdm_validator import is_valid_value, validate_pdm
from pipelines.measure_extraction import measure, measure_against_columns, measure_known_pairs, read_rows
from repositories import extraction
from repositories.extraction import REPOSITORIES, get_extraction_repository
from repositories.extraction.rule_based_v1 import RuleBasedV1ExtractionRepository

KIT = Path(__file__).parents[2] / "data" / "desafio01" / "03_padrao_cadastro_PDM.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(KIT)


def values(catalog, class_id, description, **fields):
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes[class_id], description, **fields)
    return {name: attribute.value for name, attribute in result.attributes.items()}


# Contrato: todo repositório registrado precisa cumprir, inclusive os futuros.
@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_values_follow_the_pdm_and_keep_their_origin(catalog, name):
    repository = REPOSITORIES[name]()
    pdm_class = catalog.classes["PDM001"]
    known = {a.name: a for a in pdm_class.attributes}
    result = repository.extract(pdm_class, "PARAFUSO SEXTAVADO M12X50 8.8 ACO CARBONO DIN 933")
    assert result.attributes
    for attribute_name, attribute in result.attributes.items():
        assert is_valid_value(known[attribute_name], attribute.value)
        assert attribute.original
        assert attribute.rule


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_text_without_data_extracts_nothing(catalog, name):
    assert REPOSITORIES[name]().extract(catalog.classes["PDM001"], "").attributes == {}


def test_new_repository_replaces_active_one_while_previous_stays_registered(monkeypatch):
    class Alternative(RuleBasedV1ExtractionRepository):
        name = "alternative"

    monkeypatch.setitem(extraction.REPOSITORIES, "alternative", Alternative)
    assert get_extraction_repository().name == "rule_based_v1"
    monkeypatch.setenv("EXTRACTION_REPOSITORY", "alternative")
    assert get_extraction_repository().name == "alternative"
    assert get_extraction_repository("rule_based_v1").name == "rule_based_v1"


def test_unknown_repository_lists_options():
    with pytest.raises(ValueError, match="rule_based_v1"):
        get_extraction_repository("nao_existe")


# Exemplos do briefing.
def test_the_three_briefing_valves_converge(catalog):
    descriptions = [
        "VALVULA ESFERA 2POL INOX 316 ROSCA NPT",
        'VALV ESF 2" AISI 316 NPT',
        "VALVULA DE ESFERA DN 50 CORPO INOX 316 EXTREMIDADE NPT",
    ]
    results = [values(catalog, "PDM040", text) for text in descriptions]
    assert results == [{"DIAMETRO NOMINAL": "2POL", "CONEXAO": "ROSCA NPT"}] * 3


def test_inox_316_is_not_guessed_as_forged_or_cast(catalog):
    assert "MATERIAL CORPO" not in values(catalog, "PDM040", "VALVULA ESFERA 2POL INOX 316 ROSCA NPT")
    assert values(catalog, "PDM040", "VALVULA ESFERA 3POL, MATERIAL DE CF8M")["MATERIAL CORPO"] == (
        "ACO INOX FUNDIDO A351 CF8M"
    )


def test_briefing_bolt_splits_compact_notation_and_finds_the_gap(catalog):
    found = values(catalog, "PDM001", "PARAFUSO SEXTAVADO M12X50 ZINCADO")
    assert found == {"ROSCA": "METRICA GROSSA", "BITOLA": "M12", "COMPRIMENTO": "50MM"}
    missing = [m.name for m in validate_pdm(catalog, "PDM001", found).missing_attributes]
    assert "CLASSE RESISTENCIA" in missing


def test_briefing_order_in_free_text(catalog):
    found = values(catalog, "PDM001", "preciso de 10 parafuso sextavado m16 x 60 galvanizado 8.8 din 933 pra peneira")
    assert found["BITOLA"] == "M16"
    assert found["COMPRIMENTO"] == "60MM"
    assert found["ROSCA"] == "METRICA GROSSA"
    assert found["CLASSE RESISTENCIA"] == "8.8"
    assert found["NORMA"] == "DIN 933"


def test_filter_spellings_share_one_identity(catalog):
    pdm_class = catalog.classes["PDM100"]
    keys = set()
    for text in ("FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009", "ELEM FILTRANTE OLEO LF 9009 FLEETGUARD"):
        found = values(catalog, "PDM100", text)
        assert found["FABRICANTE"] == "FLEETGUARD"
        keys.add(build_identity_key(pdm_class, "FILTRO OLEO LUBRIFICANTE", found))
    assert keys == {"PDM100|FLEETGUARD|LF9009"}


def test_other_manufacturer_with_same_code_stays_distinct(catalog):
    pdm_class = catalog.classes["PDM100"]
    first = values(catalog, "PDM100", "FILTRO OLEO FLEETGUARD LF9009")
    second = values(catalog, "PDM100", "FILTRO OLEO DONALDSON LF9009")
    item = "FILTRO OLEO LUBRIFICANTE"
    assert build_identity_key(pdm_class, item, first) != build_identity_key(pdm_class, item, second)


# Linhas reais da base, com o resultado conferido à mão.
@pytest.mark.parametrize(
    ("class_id", "description", "expected"),
    [
        (
            "PDM001",
            "PARAFUSO SEXTAVADO ROSCA DE UNC BITOLA DE 1.1/8 IN C 1.1/2 IN SAE GRAU 5 MAT AC CARBONO",
            {
                "ROSCA": "UNC",
                "BITOLA": "1.1/8POL",
                "COMPRIMENTO": "1.1/2POL",
                "CLASSE RESISTENCIA": "SAE GRAU 5",
                "MATERIAL": "ACO CARBONO",
            },
        ),
        (
            "PDM002",
            "PARAF. SEXT. ALLEN, TIPO CABECA:ESCAREADA, DIAMETRO:M 12, C:40 MM, A2-70, MATERIAL:AISI 304, "
            "REVESTIMENTO:NATURAL",
            {
                "TIPO CABECA": "ESCAREADA",
                "BITOLA": "M12",
                "COMPRIMENTO": "40MM",
                "CLASSE RESISTENCIA": "A2-70",
                "MATERIAL": "ACO INOX 304",
                "ACABAMENTO": "NATURAL",
            },
        ),
        (
            "PDM001",
            "PARAFUSO SEXTAVADO UNC 5/16POLX3POL SAE GRAU 8 OXIDADO PRETO ASME B18.2.1",
            {
                "ROSCA": "UNC",
                "BITOLA": "5/16POL",
                "COMPRIMENTO": "3POL",
                "CLASSE RESISTENCIA": "SAE GRAU 8",
                "ACABAMENTO": "OXIDADO PRETO",
                "NORMA": "ASME B18.2.1",
            },
        ),
        (
            "PDM040",
            "VALVULA ESFERA, PASSAGEM:PLENA, PRESSAO NOMINAL:600#, MAT CORPO:ACO CARBONO FUNDIDO A216 WCB, "
            'TIPO CONEXAO:FLG RF, BITOLA:1", VEDACAO SEDE:METAL-METAL',
            {
                "DIAMETRO NOMINAL": "1POL",
                "CLASSE PRESSAO": "600#",
                "MATERIAL CORPO": "ACO CARBONO FUNDIDO A216 WCB",
                "CONEXAO": "FLANGE RF",
                "PASSAGEM": "PLENA",
                "VEDACAO SEDE": "METAL-METAL",
            },
        ),
        (
            "PDM050",
            "COTOVELO  90 GRAUS - MATERIAL:ACO CARBONO FORJADO A105 - 6000# - DIAMETRO NOMINAL:DN 8 "
            "- NORMA CONSTRUCAO:ASME B16.11",
            {
                "DIAMETRO NOMINAL": "1/4POL",
                "CLASSE PRESSAO": "6000#",
                "MATERIAL": "ACO CARBONO FORJADO A105",
                "NORMA": "ASME B16.11",
            },
        ),
        (
            "PDM031",
            "ANEL O RING 58X2.5 BORRACHA NITRILICA 90 SHORE A",
            {"DIAMETRO INTERNO": "58MM", "SECAO": "2,5MM", "MATERIAL": "NBR", "DUREZA": "90 SHORE A"},
        ),
        (
            "PDM032",
            "RETENTOR 60X80X10 BA BORRACHA NITRILICA",
            {"DIAMETRO EIXO": "60MM", "DIAMETRO ALOJAMENTO": "80MM", "LARGURA": "10MM", "MATERIAL": "NBR"},
        ),
        (
            "PDM020",
            "ROLAMENTO RIG ESFERAS, REF:6216-2RS-C3, DIAM INT:80MM, VEDACAO:VEDADO, LARG:26MM, DE:140,0MM, FOLGA:C3",
            {
                "REFERENCIA": "6216-2RS/C3",
                "DIAMETRO INTERNO": "80MM",
                "DIAMETRO EXTERNO": "140MM",
                "LARGURA": "26MM",
                "VEDACAO": "BORRACHA AMBOS LADOS",
                "FOLGA": "C3",
            },
        ),
        (
            "PDM110",
            "AMORTECEDOR, PARA:PENEIRA VIBRATORIA, MODELO:LH 8X20, FABRICANTE:METSO, PART NUMBER:N07743V15",
            {
                "APLICACAO": "PENEIRA VIBRATORIA",
                "MODELO EQUIPAMENTO": "LH 8X20",
                "FABRICANTE": "METSO",
                "REFERENCIA FABRICANTE": "N07743V15",
            },
        ),
        (
            "PDM110",
            "RODA GUIA ESCAVADEIRA HIDRAULICA EX2600 PN 6728493 HITACHI",
            {
                "APLICACAO": "ESCAVADEIRA HIDRAULICA",
                "MODELO EQUIPAMENTO": "EX2600",
                "FABRICANTE": "HITACHI",
                "REFERENCIA FABRICANTE": "6728493",
            },
        ),
        (
            "PDM011",
            "MANGUEIRA HID MONTADA, EN 853 2SN, DIAM INT:3/8 POL, COMPRIMENTO:900,0MM, TERM A:FEMEA BSP",
            {
                "NORMA": "EN 853 2SN",
                "DIAMETRO INTERNO": "3/8POL",
                "COMPRIMENTO": "900MM",
                # "FEMEA BSP" não informa que o terminal é reto (#133).
            },
        ),
        (
            "PDM012",
            "MANGUEIRA INDUSTRIAL; USO:MULTIUSO; MATERIAL:BORRACHA SBR; DIAMETRO INTERNO:1 1/2 POL; "
            "PRESSAO TRABALHO:580 PSI; REFORCO:LONAS TEXTEIS",
            {
                "APLICACAO": "MULTIUSO",
                "MATERIAL": "SBR",
                "DIAMETRO INTERNO": "1.1/2POL",
                "PRESSAO TRABALHO": "40BAR",
                "REFORCO": "LONAS TEXTEIS",
            },
        ),
    ],
)
def test_real_descriptions(catalog, class_id, description, expected):
    assert values(catalog, class_id, description) == expected


def test_value_with_suffix_is_not_cut_short(catalog):
    assert values(catalog, "PDM082", "BROCA HELICOIDAL, MODELO:HSS-CO")["TIPO"] == "HSS COBALTO"
    assert "TIPO" not in values(catalog, "PDM082", "BROCA HELICOIDAL, MODELO:HSS-XX")


def test_noise_does_not_become_data(catalog):
    found = values(catalog, "PDM001", "PARAFUSO SEXTAVADO, NORMA:DIN 931, VER DESENHO, ACAB:NATURAL - COMPRA LOCAL")
    assert found == {"NORMA": "DIN 931", "ACABAMENTO": "NATURAL"}


def test_ambiguous_material_is_left_out(catalog):
    assert "MATERIAL" not in values(catalog, "PDM050", "NIPLE, MATERIAL:INOX")
    assert "ACABAMENTO" not in values(catalog, "PDM001", "PARAFUSO SEXTAVADO M6X70 ZINC")


def test_structured_fields_win_and_keep_origin(catalog):
    repository = RuleBasedV1ExtractionRepository()
    result = repository.extract(
        catalog.classes["PDM110"],
        "PLACA PART NUMBER:OUTRO123",
        manufacturer="METSO",
        manufacturer_reference="S9143E72 REV A",
    )
    reference = result.attributes["REFERENCIA FABRICANTE"]
    assert reference.value == "S9143E72 REV A"
    assert reference.original == "S9143E72 REV A"
    assert reference.rule == "field.manufacturer_reference"
    assert result.attributes["FABRICANTE"].rule == "field.manufacturer"


def test_whole_base_only_produces_values_the_pdm_accepts(catalog):
    report = measure(catalog, read_rows()[::7])
    assert report["invalid_values"] == 0
    assert report["valid_percent"] > 40


@pytest.mark.parametrize(
    ("description", "reference"),
    [
        ("MANDIBULA MOVEL BRITADOR MANDIBULA CJ615 COD 711.8073-81 SANDVIK", "711.8073-81"),
        ("ADAPTADOR ESCAVADEIRA HIDRAULICA COD 7557293 HITACHI", "7557293"),
    ],
)
def test_code_label_is_not_part_of_the_reference(catalog, description, reference):
    assert values(catalog, "PDM110", description)["REFERENCIA FABRICANTE"] == reference


def test_neutral_suffix_does_not_change_identity(catalog):
    pdm_class = catalog.classes["PDM110"]
    base = {"FABRICANTE": "ATLAS COPCO", "APLICACAO": "COMPRESSOR", "MODELO EQUIPAMENTO": "GA75"}
    first = build_identity_key(pdm_class, "CARCACA", {**base, "REFERENCIA FABRICANTE": "2908 8890 82"})
    second = build_identity_key(pdm_class, "CARCACA", {**base, "REFERENCIA FABRICANTE": "2908 8890 82-00"})
    assert first == second


def test_other_suffix_keeps_identity_distinct(catalog):
    pdm_class = catalog.classes["PDM110"]
    base = {"FABRICANTE": "METSO", "APLICACAO": "COMPRESSOR", "MODELO EQUIPAMENTO": "GA75"}
    first = build_identity_key(pdm_class, "CARCACA", {**base, "REFERENCIA FABRICANTE": "N123-01"})
    second = build_identity_key(pdm_class, "CARCACA", {**base, "REFERENCIA FABRICANTE": "N123-02"})
    assert first != second


# Proxy de colunas ocultas em FIL01/SOB01; não valida diâmetro, material ou pressão.
def test_columns_hidden_from_the_extractor_confirm_its_results(catalog):
    report = measure_against_columns(catalog, read_rows())
    assert report["FABRICANTE"]["precision_percent"] >= 99
    assert report["REFERENCIA FABRICANTE"]["precision_percent"] >= 95
    assert report["REFERENCIA FABRICANTE"]["coverage_percent"] >= 90


def test_known_duplicate_pairs_do_not_regress(catalog):
    report = measure_known_pairs(catalog, read_rows())
    assert report["pairs"] == 202
    assert report["same_identity"] >= 50
    assert report["different_identity"] <= 3


# Mesmo significado, mesmo resultado.
@pytest.mark.parametrize(
    ("class_id", "description", "variant"),
    [
        (
            "PDM040",
            "VALVULA ESFERA, DIAM NOMINAL:2POL, CLASSE:150#, CONEXAO:ROSCA NPT, PASSAGEM:PLENA",
            "VALVULA ESFERA, PASSAGEM:PLENA, CONEXAO:ROSCA NPT, CLASSE:150#, DIAM NOMINAL:2POL",
        ),
        (
            "PDM001",
            "PARAFUSO SEXTAVADO; BITOLA: M12; COMPRIMENTO: 50MM; MATERIAL: ACO CARBONO",
            "parafuso sextavado; bitola: m12; comprimento: 50mm; material: aço carbono",
        ),
        (
            "PDM050",
            'NIPLE, DIAMETRO NOMINAL:1/2", CONEXAO:ROSCA BSP',
            "NIPLE,  DIAMETRO NOMINAL:1/2 POL ,  CONEXAO:BSP",
        ),
    ],
)
def test_same_meaning_gives_same_result(catalog, class_id, description, variant):
    assert values(catalog, class_id, description) == values(catalog, class_id, variant)


HOSE = (
    'MANGUEIRA HIDRAULICA, PADRAO: SAE 100R2AT, DIAMETRO INTERNO: 2", PRESSAO TRABALHO: {pressure}, '
    "REFORCO: 2 TRAMAS ACO, MATERIAL COBERTURA: BORRACHA SINTETICA ANTIABRASAO"
)


# A base escreve pressões em bar inteiro convertidas para PSI e arredondadas a 5 PSI: 145 é 10 bar.
# Só esse caminho de volta é aceito. 150 PSI não vem de bar inteiro, então fica sem valor (#82).
@pytest.mark.parametrize(
    ("pressure", "expected"),
    [
        ("145PSI", "10BAR"),
        ("580 PSI", "40BAR"),
        ("85PSI", "6BAR"),
        ("5075 PSI", "350BAR"),
        ("150PSI", None),
        ("35PSI", None),
        ("6000PSI", None),
    ],
)
def test_psi_converts_only_when_it_comes_from_whole_bar(catalog, pressure, expected):
    assert values(catalog, "PDM010", HOSE.format(pressure=pressure)).get("PRESSAO TRABALHO") == expected


def test_psi_conversion_keeps_the_original_and_the_rule(catalog):
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes["PDM010"], HOSE.format(pressure="145PSI"))
    pressure = result.attributes["PRESSAO TRABALHO"]
    assert (pressure.value, pressure.rule) == ("10BAR", "measure.psi_to_bar")
    assert "145" in pressure.original


@pytest.mark.parametrize("finish", ["ZINCADO BRANCO", "GALVANIZADO A FOGO"])
def test_unseparated_label_stops_before_other_attributes(catalog, finish):
    text = f"parafuso sextavado M12 x 50 classe 8.8 aco carbono {finish} DIN 933."
    result = RuleBasedV1ExtractionRepository().extract(catalog.classes["PDM001"], text)
    found = {name: attribute.value for name, attribute in result.attributes.items()}
    assert found["CLASSE RESISTENCIA"] == "8.8"
    assert found["MATERIAL"] == "ACO CARBONO"
    assert found["NORMA"] == "DIN 933"
    assert found["ACABAMENTO"] == finish
    assert result.attributes["CLASSE RESISTENCIA"].original == "CLASSE: 8.8"


@pytest.mark.parametrize("finish", ["ZINCADO", "ZINCADO A FOGO"])
def test_label_tail_does_not_guess_an_unsupported_finish(catalog, finish):
    result = RuleBasedV1ExtractionRepository().extract(
        catalog.classes["PDM001"], f"parafuso sextavado M12 x 50 classe 8.8 aco carbono {finish} DIN 933"
    )
    assert "ACABAMENTO" not in result.attributes
    assert result.attributes["MATERIAL"].value == "ACO CARBONO"
    assert result.attributes["NORMA"].value == "DIN 933"
    assert any(finish in text for text in result.unresolved)


@pytest.mark.parametrize("strength", ["8.8X", "8.8.1", "8.9"])
def test_invalid_labeled_value_does_not_consume_other_attributes(catalog, strength):
    result = RuleBasedV1ExtractionRepository().extract(
        catalog.classes["PDM001"], f"parafuso sextavado classe {strength} aco carbono zincado branco DIN 933"
    )
    assert "CLASSE RESISTENCIA" not in result.attributes
    assert result.attributes["MATERIAL"].value == "ACO CARBONO"
    assert result.attributes["ACABAMENTO"].value == "ZINCADO BRANCO"
    assert any(strength in text for text in result.unresolved)


def test_real_order_keeps_values_when_strength_is_labeled(catalog):
    from pipelines.import_orders import read_orders

    orders = read_orders((KIT.parent / "02_pedidos_cadastro.csv").read_bytes())
    text = next(order.original_text for order in orders if order.source_order_id == "SC-202600037")
    original = values(catalog, "PDM001", text)
    assert values(catalog, "PDM001", text.replace("5.8", "classe 5.8")) == original
    assert original["MATERIAL"] == "ACO CARBONO"
    assert original["ACABAMENTO"] == "ZINCADO BRANCO"
    assert original["NORMA"] == "DIN 933"


def test_real_attachment_preserves_multiword_labeled_material(catalog):
    from pipelines.import_orders import read_orders

    orders = read_orders((KIT.parent / "02_pedidos_cadastro.csv").read_bytes())
    order = next(order for order in orders if order.source_order_id == "SC-202600351")
    text = order.attachment_text
    assert text
    original = values(catalog, "PDM040", text)
    unseparated = text.replace(":", " ").replace("\n", " ")
    assert values(catalog, "PDM040", unseparated) == original
    assert original["MATERIAL CORPO"] == "ACO CARBONO FORJADO A105"


def test_partial_terminal_prefix_does_not_invent_a_more_specific_terminal(catalog):
    # Linha 23969949: ORFS FEMEA não informa curva90; o texto completo seguinte informa DKO.
    text = (
        "MANGUEIRA HIDRAULICA MONTADA EN 856 4SP 1POL PRESSAO TRAB 280 BAR C DE 900MM "
        "TERMINAL A DE ORFS FEMEA FEMEA CURVA 90 GRAUS DKO COM MATERIAL TERMINAIS ACO ZINCADO"
    )
    found = values(catalog, "PDM011", text)
    assert found.get("TERMINAL A") != "FEMEA CURVA 90 GRAUS ORFS"


def test_fraction_inside_length_is_not_the_bolt_gauge(catalog):
    # Linha 17048908: 1POL é a bitola, 2 1/4POL é a medida seguinte.
    found = values(
        catalog,
        "PDM001",
        (
            "PARAFUSO SEXTAVADO ROSCA DE UNF 1POL 2 1/4POL CL SAE GRAU 5 "
            "COM MAT ACO CARB ACAB DE ZINCADO BRANCO ASME B18.2.1"
        ),
    )
    assert found.get("BITOLA") == "1POL"


@pytest.mark.parametrize("code", ["28442101", "17764693"])
def test_reinforced_ptfe_tail_keeps_its_explicit_qualification(catalog, code):
    from pipelines.measure_extraction import read_rows

    text = next(row.description for row in read_rows() if row.code == code)
    assert values(catalog, "PDM040", text)["VEDACAO SEDE"] == "RPTFE"
