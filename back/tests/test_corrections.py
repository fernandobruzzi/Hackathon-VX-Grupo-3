"""Correções de descrição, grupo e unidade, com linhas reais da base conferidas à mão."""

from dataclasses import replace
from pathlib import Path

import pytest

from domain.contracts import FieldStatus
from domain.pdm_loader import load_pdm
from pipelines.corrections import correction_proposals, propose_corrections, summarize_corrections
from pipelines.sanitize import analyze_material, read_csv_records
from repositories.classification import get_classification_repository
from repositories.corrections import REPOSITORIES, get_correction_repository
from repositories.corrections.head_noun_v1 import opens_description
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

DATA = Path(__file__).parents[2] / "data" / "desafio01"


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
def analyze(catalog, records, tools):
    def run(code, **changes):
        record = replace(records[code], **changes)
        return analyze_material(record, catalog, tools[0], tools[1])

    return run


def correct(analyze, catalog, tools, code, repository=None, **changes):
    return get_correction_repository(repository).correct(analyze(code, **changes), catalog, tools[2])


def by_field(result):
    return {change.field: change for change in result.corrections}


def test_group_diverging_from_class_is_proposed(analyze, catalog, tools):
    # 15755818: DISJUNTOR DIN 3P 25A B 3KA, cadastrado em TRA01; disjuntor é ELE01 no PDM.
    change = by_field(correct(analyze, catalog, tools, "15755818"))["merchandise_group"]

    assert (change.proposal_type, change.before, change.after) == ("PDM_CORRECTION", "TRA01", "ELE01")
    assert change.rule == "head_noun_v1/group.from_pdm_class"


def test_description_follows_pdm_with_original_kept(analyze, catalog, tools):
    # 16454102: as quatro informações do texto livre viram atributos do PDM, na ordem da classe.
    change = by_field(correct(analyze, catalog, tools, "16454102"))["description"]

    assert change.before == "ANEL O-RING DIAMETRO DE 15MM, COM SECAO TRANSV 2 MM, NBR, DUREZA DE 70 SHORE A"
    assert change.after == "ANEL O-RING; DIAMETRO INTERNO: 15MM; SECAO: 2MM; MATERIAL: NBR; DUREZA: 70 SHORE A"
    assert change.rule == "head_noun_v1/description.pdm_format"


def test_unit_alias_becomes_unit_correction(analyze, catalog, tools):
    # 24794045: amortecedor em PCA; PCA é grafia de peça.
    change = by_field(correct(analyze, catalog, tools, "24794045"))["unit"]

    assert (change.proposal_type, change.before, change.after) == ("UNIT_CORRECTION", "PCA", "PC")
    assert change.rule == "rule_based_v1/unit.alias"


def test_packaging_unit_without_factor_stays_pending(analyze, catalog, tools):
    # 27475738: anel labirinto em CX. Sem saber quantas peças há na caixa, nada é convertido.
    result = correct(analyze, catalog, tools, "27475738")

    assert "unit" not in by_field(result)
    assert "UNIDADE_SEM_FATOR: CX exige fator de conversao para PC" in result.pending
    assert "description" in by_field(result)


ALIAS_WITHOUT_CLASS = "head_noun_v1/unit.alias_without_class (rule_based_v1/unit.alias)"


@pytest.mark.parametrize(
    ("code", "before", "after"),
    [
        # Parafuso Allen não classificado, em PÇ.
        ("24477027", "PÇ", "PC"),
        # Calçado de segurança não classificado, em PAR: continua par, só muda a grafia.
        ("20443888", "PAR", "PR"),
    ],
)
def test_material_without_class_gets_only_unit_alias(analyze, catalog, tools, code, before, after):
    result = correct(analyze, catalog, tools, code)

    assert [(c.proposal_type, c.field, c.before, c.after, c.rule) for c in result.corrections] == [
        ("UNIT_CORRECTION", "unit", before, after, ALIAS_WITHOUT_CLASS)
    ]
    assert result.pending == ("SEM_CLASSE_CONFIAVEL: o classificador nao decidiu a classe",)


def test_unconfirmed_class_gets_only_unit_alias(analyze, catalog, tools):
    # 15487300: "PARAF.  SEXTAVADO ... REVEST" em PCA; a classe achada no meio do texto não é usada.
    result = correct(analyze, catalog, tools, "15487300")

    assert [(c.field, c.before, c.after, c.rule) for c in result.corrections] == [
        ("unit", "PCA", "PC", ALIAS_WITHOUT_CLASS)
    ]
    assert result.pending == ("CLASSE_NAO_CONFIRMADA: o nome do item nao abre a descricao",)


def test_packaging_unit_without_class_stays_untouched(analyze, catalog, tools):
    # 18494522: parafuso não classificado em CX. Sem classe e sem fator, nada é proposto.
    result = correct(analyze, catalog, tools, "18494522")

    assert result.corrections == ()
    assert result.pending == ("SEM_CLASSE_CONFIAVEL: o classificador nao decidiu a classe",)


def test_class_found_mid_text_is_not_trusted(analyze, catalog, tools):
    # 18495654: parafuso abreviado classificado como sobressalente pela palavra REVESTIMENTO.
    material = analyze("18495654")
    assert material.pdm_class_id == "PDM110" and material.item_name == "REVESTIMENTO"

    result = correct(analyze, catalog, tools, "18495654")

    assert result.corrections == ()
    assert result.pending == ("CLASSE_NAO_CONFIRMADA: o nome do item nao abre a descricao",)


def test_incomplete_description_is_not_rewritten(analyze, catalog, tools):
    # 25571564: a extração não reconhece material e conexão; a descrição fica como está.
    result = correct(analyze, catalog, tools, "25571564")

    assert "description" not in by_field(result)
    assert "DESCRICAO_FORA_DO_PADRAO: faltam MATERIAL, CONEXAO" in result.pending


@pytest.mark.parametrize("status", ["BLOQUEADO", "OBSOLETO"])
def test_inactive_material_gets_no_correction(analyze, catalog, tools, status):
    result = correct(analyze, catalog, tools, "15755818", status=status)

    assert result.corrections == ()
    assert result.pending == (f"MATERIAL_NAO_ATIVO: {status}",)


def test_redirect_prefix_does_not_hide_item_name():
    description = "NAO UTILIZAR - USAR COD 18316702 - TAMPA SUCCAO COMPRESSOR, GA90"

    assert opens_description("TAMPA SUCCAO", description)
    assert not opens_description("COMPRESSOR", description)


def test_proposals_carry_before_after_and_rule(analyze, catalog, tools):
    material = analyze("24794045")
    result = get_correction_repository().correct(material, catalog, tools[2])

    proposals = {p.proposal_type: p for p in correction_proposals(material, result, catalog, "head_noun_v1")}

    unit = proposals["UNIT_CORRECTION"].changeset
    assert unit["changes"] == [{"field": "unit", "before": "PCA", "after": "PC", "source": "rule_based_v1/unit.alias"}]
    assert unit["after"]["unit"] == "PC"
    assert unit["after"]["description"] == material.record.description
    pdm = proposals["PDM_CORRECTION"].changeset
    assert [change["field"] for change in pdm["changes"]] == ["description"]
    assert pdm["after"]["unit"] == "PCA"
    assert all(not p.fiscal_review_required and p.material_codes == ("24794045",) for p in proposals.values())


def test_proposal_ids_are_stable(analyze, catalog, tools):
    materials = [analyze(code) for code in ("15755818", "24794045")]
    first, _ = propose_corrections(materials, catalog, tools[2], get_correction_repository())
    second, _ = propose_corrections(materials, catalog, tools[2], get_correction_repository())

    assert [p.id for p in first] == [p.id for p in second]
    assert len({p.id for p in first}) == len(first)


def test_summary_counts_proposals_changes_and_pending(analyze, catalog, tools):
    materials = [analyze("15755818"), analyze("27475738"), analyze("14867234"), analyze("14867234", status="ATIVO")]
    proposals, pending = propose_corrections(materials, catalog, tools[2], get_correction_repository())

    summary = summarize_corrections(proposals, pending)

    assert summary["pending"]["MATERIAL_NAO_ATIVO"] == 1
    assert summary["pending"]["SEM_CLASSE_CONFIAVEL"] == 1
    assert summary["pending"]["UNIDADE_SEM_FATOR"] == 1
    assert summary["changes"]["merchandise_group"] == 1


# Contrato: todo repositório registrado precisa cumprir, inclusive os futuros.
@pytest.mark.parametrize("name", sorted(REPOSITORIES))
@pytest.mark.parametrize(
    "code",
    ["15755818", "16454102", "24794045", "27475738", "14867234", "18495654", "11979418", "24477027", "15487300"]
    + ["18494522"],
)
def test_contract_changes_are_traceable_and_safe(analyze, catalog, tools, name, code):
    material = analyze(code)
    result = REPOSITORIES[name]().correct(material, catalog, tools[2])

    if material.record.status != "ATIVO":
        assert result.corrections == ()
    if material.pdm_class_id is None:
        # Sem classe, só a grafia da mesma unidade: nunca a unidade padrão de uma classe.
        assert all(change.field == "unit" for change in result.corrections)
    for change in result.corrections:
        assert change.proposal_type in {"PDM_CORRECTION", "UNIT_CORRECTION"}
        assert change.rule and change.after and change.after != change.before
        if change.field == "unit":
            # Só grafias da mesma unidade: embalagem sem fator nunca é convertida.
            assert tools[2].normalize_unit(change.before).status is FieldStatus.NORMALIZED


def test_each_proposal_carries_only_its_own_pending(analyze, catalog, tools):
    # 10436289: disjuntor em UN, grafia de PC, com descrição sem CURVA. A descrição incompleta
    # fica pendente no material, mas não impede corrigir a grafia da unidade.
    material = analyze("10436289")
    result = get_correction_repository().correct(material, catalog, tools[2])
    assert any(reason.startswith("DESCRICAO_FORA_DO_PADRAO") for reason in result.pending)

    proposals = {p.proposal_type: p for p in correction_proposals(material, result, catalog, "head_noun_v1")}

    assert proposals["UNIT_CORRECTION"].conflicts == ()
    assert proposals["UNIT_CORRECTION"].changeset["conflicts"] == []
    assert "PDM_CORRECTION" not in proposals


def test_packaging_without_factor_keeps_the_description_proposal_but_not_approvable(analyze, catalog, tools):
    # 10017576: embalagem CT sem fator. A correção de descrição e grupo continua proposta, mas a
    # aprovação publica a identidade PDM com a unidade atual e recusa CT. O batch marca o mesmo motivo,
    # para a fila não oferecer como aprovável o que a aprovação recusaria.
    material = analyze("10017576")
    result = get_correction_repository().correct(material, catalog, tools[2])
    assert any(reason.startswith("UNIDADE_SEM_FATOR") for reason in result.pending)

    proposals = correction_proposals(material, result, catalog, "head_noun_v1")

    assert [p.proposal_type for p in proposals] == ["PDM_CORRECTION"]
    assert not any(reason.startswith("UNIDADE_SEM_FATOR") for reason in proposals[0].conflicts)
    assert proposals[0].conflicts == (
        "PDM_INVALIDO: resultado não atende ao PDM (UNIDADE inválido (UNIT_NOT_CLASS_DEFAULT))",
    )
    assert proposals[0].changeset["conflicts"] == list(proposals[0].conflicts)


def test_class_unit_difference_still_blocks_the_unit_correction(analyze, catalog, tools):
    # 11472033: óleo em UN, grafia de PC; a classe mede em L. Corrigir a grafia esconderia a unidade errada.
    material = analyze("11472033")
    result = get_correction_repository().correct(material, catalog, tools[2])

    unit = next(
        p
        for p in correction_proposals(material, result, catalog, "head_noun_v1")
        if p.proposal_type == "UNIT_CORRECTION"
    )

    assert unit.conflicts == ("UNIDADE_DIFERENTE_DA_CLASSE: PC, padrao da classe L",)
