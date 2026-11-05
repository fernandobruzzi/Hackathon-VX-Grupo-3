import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from domain.contracts import MatchType, MaterialRecord
from domain.identity import compare_attributes, partial_identity_key
from domain.pdm_loader import load_pdm
from pipelines.sanitize import analyze_material, build_proposal, propose_merges, read_csv_records
from repositories import candidates
from repositories.candidates import REPOSITORIES, get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

DATA = Path(__file__).parents[2] / "data" / "desafio01"
REVIEW = Path(__file__).parent / "fixtures" / "merge_review.json"


@pytest.fixture(scope="module")
def catalog():
    return load_pdm(DATA / "03_padrao_cadastro_PDM.xlsx")


@pytest.fixture(scope="module")
def tools(catalog):
    return get_classification_repository(catalog), get_extraction_repository(), get_normalization_repository()


def material(catalog, tools, code, description, **fields):
    record = MaterialRecord(code=code, status=fields.pop("status", "ATIVO"), description=description, **fields)
    return analyze_material(record, catalog, tools[0], tools[1])


def group_for(repository, catalog, materials):
    return get_candidate_repository(repository).find(materials, catalog)


# Contrato: todo repositório registrado precisa cumprir, inclusive os futuros.
@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_only_active_materials_and_no_verification_without_identity(catalog, tools, name):
    first = material(catalog, tools, "1", "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009")
    second = material(catalog, tools, "2", "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF 9009")
    blocked = material(catalog, tools, "3", "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009", status="BLOQUEADO")
    obsolete = material(catalog, tools, "4", "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009", status="OBSOLETO")
    groups = REPOSITORIES[name]().find([first, second, blocked, obsolete], catalog)
    assert groups
    for group in groups:
        assert not {"3", "4"} & set(group.codes)
        assert len(group.codes) >= 2
        assert group.identity_verified is (group.match_type is MatchType.EXACT_IDENTITY)


@pytest.mark.parametrize("name", sorted(REPOSITORIES))
def test_contract_interchangeable_manufacturers_stay_distinct(catalog, tools, name):
    first = material(catalog, tools, "1", "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009")
    second = material(catalog, tools, "2", "FILTRO OLEO LUBRIFICANTE DONALDSON LF9009")
    assert REPOSITORIES[name]().find([first, second], catalog) == []


def test_default_algorithm_is_exact_and_can_be_swapped(monkeypatch):
    monkeypatch.delenv("CANDIDATE_REPOSITORY", raising=False)
    assert get_candidate_repository().name == "exact_identity_v1"
    monkeypatch.setenv("CANDIDATE_REPOSITORY", "tokens_v1")
    assert get_candidate_repository().name == "tokens_v1"
    with pytest.raises(ValueError, match="exact_identity_v1"):
        get_candidate_repository("nao_existe")


def test_new_algorithm_only_needs_registering(monkeypatch):
    class Alternative(REPOSITORIES["exact_identity_v1"]):
        name = "alternative"

    monkeypatch.setitem(candidates.REPOSITORIES, "alternative", Alternative)
    assert get_candidate_repository("alternative").name == "alternative"


def test_reference_classes_need_only_manufacturer_and_reference(catalog):
    pdm_class = catalog.classes["PDM110"]
    assert (
        partial_identity_key(pdm_class, {"FABRICANTE": "METSO", "REFERENCIA FABRICANTE": "N1-00"}) == "PDM110|METSO|N1"
    )
    assert partial_identity_key(pdm_class, {"FABRICANTE": "METSO"}) is None
    assert partial_identity_key(catalog.classes["PDM001"], {"FABRICANTE": "X", "REFERENCIA FABRICANTE": "Y"}) is None


def test_technical_class_with_missing_attribute_is_not_verified(catalog, tools):
    first = material(catalog, tools, "1", "PARAFUSO SEXTAVADO M12X50 8.8")
    second = material(catalog, tools, "2", "PARAFUSO SEXTAVADO M12X50 10.9")
    assert first.identity_key is None
    assert second.identity_key is None
    assert group_for("exact_identity_v1", catalog, [first, second]) == []


def test_measure_or_model_is_not_taken_as_reference(catalog, tools):
    found = material(catalog, tools, "1", "PLACA TRASEIRA BOMBA POLPA WARMAN 6-4 D AH WEIR")
    assert "REFERENCIA FABRICANTE" not in found.attributes
    assert found.attributes["MODELO EQUIPAMENTO"] == "WARMAN 6/4 D AH"


def test_tokens_require_no_conflict_on_known_attributes(catalog):
    pdm_class = catalog.classes["PDM001"]
    first = {"BITOLA": "M12", "NORMA": "DIN 933"}
    second = {"BITOLA": "M14", "NORMA": "DIN 933"}
    assert compare_attributes(pdm_class, first, second) == (["BITOLA"], 1)


HOSE = (
    'MANGUEIRA HIDRAULICA, PADRAO: SAE 100R2AT, DIAMETRO INTERNO: 2", PRESSAO TRABALHO: {pressure}, '
    "REFORCO: 2 TRAMAS ACO, MATERIAL COBERTURA: BORRACHA SINTETICA ANTIABRASAO"
)


def test_different_psi_pressures_do_not_share_an_identity(catalog, tools):
    """#82: 145 e 150 PSI viravam 10BAR por arredondamento e geravam merge verificado."""
    first = material(catalog, tools, "1", HOSE.format(pressure="145PSI"))
    second = material(catalog, tools, "2", HOSE.format(pressure="150PSI"))
    assert first.identity_key and first.identity_key != second.identity_key
    assert group_for("exact_identity_v1", catalog, [first, second]) == []


def test_psi_from_whole_bar_still_matches_the_bar_spelling(catalog, tools):
    first = material(catalog, tools, "1", HOSE.format(pressure="145PSI"))
    second = material(catalog, tools, "2", HOSE.format(pressure="10BAR"))
    assert first.identity_key == second.identity_key
    assert group_for("exact_identity_v1", catalog, [first, second])[0].identity_verified


def proposal_for(catalog, tools, *members):
    group = group_for("exact_identity_v1", catalog, list(members))[0]
    by_code = {member.record.code: member for member in members}
    return build_proposal(group, by_code, catalog, tools[2])


FILTER = "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009"


def test_proposal_keeps_members_versions_and_identity(catalog, tools):
    proposal = proposal_for(
        catalog,
        tools,
        material(catalog, tools, "1", FILTER, version=4, total_value="10"),
        material(catalog, tools, "2", FILTER, version=7, total_value="90"),
    )
    assert proposal.proposal_type == "MERGE"
    assert proposal.material_codes == ("1", "2")
    assert proposal.suggested_primary_code == "2"
    assert [(m["material_code"], m["observed_version"]) for m in proposal.members] == [("1", 4), ("2", 7)]
    assert proposal.changeset["identity_key"] == "PDM100|FLEETGUARD|LF9009"
    assert proposal.changeset["blocked_material_codes"] == ["1"]
    assert len(proposal.changeset_hash) == 64


def test_primary_tie_is_repeatable(catalog, tools):
    first = material(catalog, tools, "5", FILTER, total_value="10")
    second = material(catalog, tools, "2", FILTER, total_value="10")
    assert proposal_for(catalog, tools, first, second).suggested_primary_code == "2"


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        (("CX", "PC"), "UNIDADE_SEM_FATOR"),
        (("PC", "M"), "UNIDADES_DIFERENTES"),
    ],
)
def test_units_that_cannot_be_compared_block_consolidation(catalog, tools, units, expected):
    proposal = proposal_for(
        catalog,
        tools,
        material(catalog, tools, "1", FILTER, unit=units[0]),
        material(catalog, tools, "2", FILTER, unit=units[1]),
    )
    assert any(conflict.startswith(expected) for conflict in proposal.conflicts)


def test_unit_aliases_do_not_block_consolidation(catalog, tools):
    proposal = proposal_for(
        catalog,
        tools,
        material(catalog, tools, "1", FILTER, unit="PÇ"),
        material(catalog, tools, "2", FILTER, unit="PC"),
    )
    assert proposal.conflicts == ()


def test_divergent_ncm_requires_fiscal_review(catalog, tools):
    divergent = proposal_for(
        catalog,
        tools,
        material(catalog, tools, "1", FILTER, ncm="8421.23.00"),
        material(catalog, tools, "2", FILTER, ncm="8421.29.90"),
    )
    assert divergent.fiscal_review_required is True
    assert any(conflict.startswith("NCM_DIVERGENTE") for conflict in divergent.conflicts)
    same = proposal_for(
        catalog,
        tools,
        material(catalog, tools, "1", FILTER, ncm="84212300"),
        material(catalog, tools, "2", FILTER, ncm="8421.23.00"),
    )
    # Mesmo código fiscal, mas mudar a grafia persistida também exige autorização fiscal.
    assert same.fiscal_review_required is True
    assert not same.conflicts


def test_redirect_prefix_is_ignored_when_analyzing(catalog, tools):
    found = material(catalog, tools, "1", f"NAO UTILIZAR - USAR COD 22160683 - {FILTER}", status="BLOQUEADO")
    assert found.identity_key == "PDM100|FLEETGUARD|LF9009"


@pytest.fixture(scope="module")
def whole_base(catalog, tools):
    records = read_csv_records(DATA / "01_base_materiais.csv")
    analyzed = [analyze_material(record, catalog, tools[0], tools[1]) for record in records]
    return records, analyzed


def proposed_pairs(groups):
    pairs = set()
    for group in groups:
        for first in group.codes:
            for second in group.codes:
                if first < second:
                    pairs.add((first, second))
    return pairs


def reviewed():
    return json.loads(REVIEW.read_text(encoding="utf-8"))["pairs"]


def precision(pairs):
    decided = [pair for pair in reviewed() if pair["same_item"] is not None and tuple(sorted(pair["codes"])) in pairs]
    return sum(pair["same_item"] for pair in decided) / len(decided), len(decided)


# Mede com pares revisados: é a medida de junções erradas, e os mínimos só devem subir.
def test_exact_identity_precision_on_reviewed_pairs(catalog, whole_base):
    _, analyzed = whole_base
    value, decided = precision(proposed_pairs(group_for("exact_identity_v1", catalog, analyzed)))
    assert decided >= 50
    assert value == 1.0


def test_tokens_stay_out_of_the_default_because_precision_is_low(catalog, whole_base):
    _, analyzed = whole_base
    groups = group_for("tokens_v1", catalog, analyzed)
    weak = proposed_pairs(group for group in groups if not group.identity_verified)
    value, decided = precision(weak)
    # Se isso subir de verdade, reavalie o padrão em repositories/candidates.
    assert decided >= 5
    assert value < 0.8


def test_declared_duplicates_found(catalog, whole_base):
    records, analyzed = whole_base
    active = [
        replace(m, record=replace(m.record, status="ATIVO")) if m.record.status == "BLOQUEADO" else m for m in analyzed
    ]
    pairs = proposed_pairs(group_for("exact_identity_v1", catalog, active))
    status = {record.code: record.status for record in records}
    declared = {
        tuple(sorted((record.code, match[1])))
        for record in records
        if record.status == "BLOQUEADO"
        and (match := re.search(r"USAR COD (\d+)", record.description))
        and status.get(match[1]) == "ATIVO"
        and match[1] != record.code
    }
    assert len(declared) == 202
    assert len(declared & pairs) >= 70


def test_whole_base_runs_end_to_end(catalog, tools, whole_base):
    records, _ = whole_base
    proposals = propose_merges(records, catalog, tools[0], tools[1], get_candidate_repository(), tools[2])
    assert len(proposals) > 1000
    assert all(proposal.changeset["identity_verified"] for proposal in proposals)
    assert all(len(proposal.material_codes) >= 2 for proposal in proposals)
    assert len({proposal.id for proposal in proposals}) == len(proposals)
