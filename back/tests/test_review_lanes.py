"""Níveis de revisão das correções (#119) e o sinal de perda de texto, com linhas reais da base.

Cada caso foi conferido lendo a descrição original e a proposta. Na dúvida a proposta vai para o
nível 3: o custo é revisar item a item, nunca aplicar em lote uma descrição que perdeu informação.
"""

from pathlib import Path

import pytest

from domain.contracts import FieldCorrection
from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from domain.review_lanes import assign_lane, lot_key
from pipelines.corrections import correction_proposals, propose_corrections, summarize_corrections
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository
from repositories.proposal_payload import approval_payload
from repositories.text_loss import REPOSITORIES, get_text_loss_repository

DATA = Path(__file__).parents[2] / "data" / "desafio01"


@pytest.fixture(scope="module", autouse=True)
def fallback_stack():
    """Casos revisados à mão na pilha literal, mantida como fallback de auditoria.

    O padrão (aliases_v2 + head_noun_v2) tem seus casos em test_corrections_head_v2.py.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CLASSIFICATION_REPOSITORY", "aliases_v1")
        patch.setenv("CORRECTION_REPOSITORY", "head_noun_v1")
        yield


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def records():
    return {record.code: record for record in read_csv_records(DATA / "01_base_materiais.csv")}


@pytest.fixture(scope="module")
def tools(catalog):
    return get_classification_repository(catalog), get_extraction_repository(), get_normalization_repository()


@pytest.fixture(scope="module")
def proposals(catalog, records, tools):
    """Propostas de correção de um material, por tipo, com a regra de perda de texto padrão."""

    def run(code, text_loss=None):
        material = analyze_material(records[code], catalog, tools[0], tools[1])
        result = get_correction_repository().correct(material, catalog, tools[2])
        loss = text_loss or get_text_loss_repository()
        built = correction_proposals(material, result, catalog, "head_noun_v1", loss)
        return {proposal.proposal_type: proposal for proposal in built}

    return run


def lane(proposal):
    return proposal.changeset["review_lane"]


# Descrição proposta perde informação do original: vai para o nível 3.
LOST = {
    # TAMPA PRES vira TAMPA: outra peça. PRES (pressão) não é atributo da classe.
    "19812163": "PRES",
    # MATERIAL:ACO ESPECIAL some: a classe de sobressalentes não tem material "especial".
    "13885106": "ESPECIAL",
    # PRESSAO: 286KGF/CM2 não tem atributo na mangueira montada.
    "28611241": "286KGF/CM2",
    # Classe AR do fusível ultrarrápido não vira atributo.
    "11472263": "AR",
    # Diâmetro interno e externo e espessura da arruela (19 MM 34MM 3 MM) somem.
    "21431375": "34MM",
}

# A #133 retém o original antes de propor a descrição: FEMEA 90 JIC não informa CURVA/GRAUS.
INCOMPLETE_LOST = {"28611241": "TERMINAL B"}
COMPLETE_LOST = LOST.keys() - INCOMPLETE_LOST.keys()

# Nada se perde: o texto está na descrição proposta com outra grafia, ou é rótulo, ou ruído documentado.
KEPT = {
    "12769099": "MA é a rosca métrica grossa, que está na proposta",
    "27229887": "BORRACHA EPDM vira MATERIAL: EPDM",
    "10837553": "8597 0256 05 é a mesma referência, sem espaços",
    "13792890": "EXTREMIDADES BW vira CONEXAO: SOLDA TOPO BW",
    "14448961": "rótulos GRAU e TIPO CABECA; valores todos na proposta",
    "24003993": "VER DESENHO é ruído que o padrão não inclui; o original fica no antes",
    "15195267": "SCHNEIDER continua no campo de fabricante do cadastro",
}

# A leitura independente conserva a referência como escrita na descrição longa.
# O caso revisado continua sem perda; o texto já corresponde ao formato PDM e dispensa proposta.
ALREADY_STANDARDIZED = {"10837553"}


@pytest.mark.parametrize("code", sorted(COMPLETE_LOST))
def test_text_loss_sends_description_to_individual_review(proposals, code):
    pdm = proposals(code)["PDM_CORRECTION"]

    assert lane(pdm)["tier"] == 3
    assert lane(pdm)["reasons"] == ["TEXT_LOSS"]


@pytest.mark.parametrize("code", sorted(COMPLETE_LOST))
def test_lost_terms_name_what_disappeared(catalog, records, tools, proposals, code):
    material = analyze_material(records[code], catalog, tools[0], tools[1])
    proposed = next(
        change["after"]
        for change in proposals(code)["PDM_CORRECTION"].changeset["changes"]
        if change["field"] == "description"
    )

    lost = get_text_loss_repository().lost_terms(material, catalog.classes[material.pdm_class_id], proposed)

    assert LOST[code] in lost


@pytest.mark.parametrize("code", sorted(INCOMPLETE_LOST))
def test_incomplete_values_stay_pending_before_description_review(catalog, records, tools, proposals, code):
    material = analyze_material(records[code], catalog, tools[0], tools[1])
    validation = validate_pdm(catalog, material.pdm_class_id, material.attributes, item_name=material.item_name)

    assert INCOMPLETE_LOST[code] in {attribute.name for attribute in validation.missing_attributes}
    assert "PDM_CORRECTION" not in proposals(code)


@pytest.mark.parametrize("code", sorted(KEPT.keys() - ALREADY_STANDARDIZED))
def test_description_without_loss_can_go_in_a_lot(proposals, code):
    pdm = proposals(code)["PDM_CORRECTION"]

    assert "TEXT_LOSS" not in lane(pdm)["reasons"], KEPT[code]
    # Sem conflito vai para lote; com conflito, como a unidade KG fora do padrão da classe (#122), não.
    assert lane(pdm)["tier"] == (3 if pdm.changeset["conflicts"] else 2), KEPT[code]


def test_spaced_reference_already_matches_pdm_and_needs_no_rewrite(catalog, records, tools, proposals):
    material = analyze_material(records["10837553"], catalog, tools[0], tools[1])
    checked = validate_pdm(catalog, material.pdm_class_id, material.attributes, item_name=material.item_name)
    assert material.attributes["REFERENCIA FABRICANTE"] == "8597 0256 05"
    assert checked.formatted_description == material.record.description
    assert "PDM_CORRECTION" not in proposals("10837553")


def test_unit_alias_with_trusted_class_is_tier_one(proposals):
    # 24794045: unidade PCA, mesma unidade que PC; classe confirmada pela descrição.
    unit = proposals("24794045")["UNIT_CORRECTION"]

    assert lane(unit) == {"tier": 1, "lot_key": "UNIT_CORRECTION|rule_based_v1/unit.alias|PDM110", "reasons": []}


def test_unit_alias_without_trusted_class_is_individual(proposals):
    # 10109628: RETENTOR em UN sem classe confirmada; só a grafia da unidade é corrigida.
    unit = proposals("10109628")["UNIT_CORRECTION"]

    assert lane(unit)["tier"] == 3
    assert lane(unit)["reasons"] == ["UNTRUSTED_CLASS"]


def test_unit_with_pending_reason_is_individual(proposals):
    # 11472033: óleo em UN; a classe pede litro, então a unidade fica pendente de revisão.
    unit = proposals("11472033")["UNIT_CORRECTION"]

    assert lane(unit)["tier"] == 3
    assert lane(unit)["reasons"] == ["CONFLICT"]


def test_group_with_pending_description_is_individual(proposals):
    # 15755818: grupo TRA01 -> ELE01, mas a descrição do disjuntor está fora do padrão.
    pdm = proposals("15755818")["PDM_CORRECTION"]

    assert lane(pdm)["tier"] == 3
    assert lane(pdm)["reasons"] == ["CONFLICT"]
    assert lane(pdm)["lot_key"] == "PDM_CORRECTION|head_noun_v1/group.from_pdm_class|PDM062"


def test_lot_key_joins_type_rules_and_class():
    changes = [
        FieldCorrection("PDM_CORRECTION", "merchandise_group", "ELE01", "FIX01", "head_noun_v1/group.from_pdm_class"),
        FieldCorrection("PDM_CORRECTION", "description", "A", "B", "head_noun_v1/description.pdm_format"),
    ]

    assert lot_key("PDM_CORRECTION", changes, "PDM002") == (
        "PDM_CORRECTION|head_noun_v1/description.pdm_format+head_noun_v1/group.from_pdm_class|PDM002"
    )
    assert lot_key("UNIT_CORRECTION", changes[:1], None).endswith("|SEM_CLASSE")


def test_every_reason_is_listed():
    changes = [FieldCorrection("PDM_CORRECTION", "description", "A", "B", "head_noun_v1/description.pdm_format")]

    result = assign_lane("PDM_CORRECTION", changes, ("DESCRICAO_FORA_DO_PADRAO: x",), None, ("ACO",))

    assert result.tier == 3
    assert result.reasons == ("UNTRUSTED_CLASS", "TEXT_LOSS", "CONFLICT")


def test_review_lane_reaches_the_persisted_changeset(proposals, records):
    pdm = proposals("12769099")["PDM_CORRECTION"]

    _, changeset, _ = approval_payload(pdm, {"12769099": "00000000-0000-0000-0000-000000000001"}, "dataset")

    assert changeset["review_lane"] == lane(pdm)


def test_summary_counts_tiers_reasons_and_lots(catalog, records, tools):
    codes = ["24794045", "10109628", "19812163", "12769099", "15755818"]
    materials = [analyze_material(records[code], catalog, tools[0], tools[1]) for code in codes]
    built, pending = propose_corrections(materials, catalog, tools[2], get_correction_repository())

    lanes = summarize_corrections(built, pending)["review_lanes"]

    # A descrição de 24794045 leva a unidade atual PCA, que a aprovação recusa (#122): nível 3. A correção
    # da unidade PCA para PC continua no nível 1.
    assert lanes["tiers"] == {"1": 1, "2": 1, "3": 4}
    assert lanes["reasons"] == {"UNTRUSTED_CLASS": 1, "TEXT_LOSS": 1, "CONFLICT": 2}
    assert lanes["eligible_lots"] == 0  # nenhum lote chega a 20 itens com cinco materiais


# Contrato: toda regra de perda de texto registrada precisa reconhecer as perdas e os casos sem perda.
@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_registered_repositories_meet_the_reviewed_cases(proposals, name):
    repository = get_text_loss_repository(name)

    assert all(lane(proposals(code, repository)["PDM_CORRECTION"])["tier"] == 3 for code in COMPLETE_LOST)
    assert all(
        "TEXT_LOSS" not in lane(proposals(code, repository)["PDM_CORRECTION"])["reasons"]
        for code in KEPT.keys() - ALREADY_STANDARDIZED
    )
    assert all("PDM_CORRECTION" not in proposals(code, repository) for code in ALREADY_STANDARDIZED)


@pytest.mark.parametrize("code", ["24794045", "22976650"])
def test_description_the_approval_would_refuse_is_individual(proposals, code):
    # Unidade PCA e JG fora do padrão da classe: a aprovação recusa por PDM (#122), então nada de lote.
    pdm = proposals(code)["PDM_CORRECTION"]

    assert any(conflict.startswith("PDM_INVALIDO") for conflict in pdm.changeset["conflicts"])
    assert lane(pdm)["tier"] == 3
    assert "CONFLICT" in lane(pdm)["reasons"]
