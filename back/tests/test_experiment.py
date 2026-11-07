"""Experimento manual x solução (#207): pacote determinista, planilha cega e resultado com regras da #85."""

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cli import main
from pipelines.experiment import PACKAGE_CELL, REVIEWER_CELL, experiment_packets, select, workbook
from pipelines.experiment_result import ExperimentError, experiment_result

DATA = Path(__file__).parents[2] / "data" / "desafio01"
CSV = str(DATA / "01_base_materiais.csv")
PDM = str(DATA / "03_padrao_cadastro_PDM.xlsx")
SIZES = {"pairs_size": 4, "corrections_size": 3, "slice_size": 12}


@pytest.fixture(scope="module")
def packet(tmp_path_factory):
    out = tmp_path_factory.mktemp("experiment")
    summary = experiment_packets(CSV, PDM, str(out), 207, **SIZES)
    return summary, json.loads(Path(summary["key"]).read_text())


def fill(summary, key, path, reviewer, flip_pairs=(), unsure=(), wrong_descriptions=()):
    """Revisor sintético: concorda com o sistema, exceto nos casos indicados."""
    wb = load_workbook(summary["sheet"])
    wb["Como revisar"][REVIEWER_CELL] = reviewer
    for row in wb["Mesmo item"].iter_rows(min_row=2):
        case = row[0].value
        same = key["pairs"][case]["system_same_item"] != (case in flip_pairs)
        row[2].value = "NAO SEI" if case in unsure else ("SIM" if same else "NAO")
        row[3].value = "evidência"
    for row in wb["Descrição"].iter_rows(min_row=2):
        row[4].value = "NAO" if row[0].value in wrong_descriptions else "SIM"
        row[5].value = "NAO"
        row[6].value = "evidência sintética de teste"
    manual = wb["Manual"]
    manual["B1"], manual["D1"] = "14:00", "14:30"
    for row in manual.iter_rows(min_row=4):
        identity = key["slice"][str(row[1].value)]["identity_key"]
        row[4].value = identity or f"so-{row[1].value}"
    wb.save(path)
    return str(path)


def test_same_inputs_and_seed_give_the_same_packet():
    first = select(CSV, PDM, 207, **SIZES)
    assert first == select(CSV, PDM, 207, **SIZES)
    assert first["package_id"] != select(CSV, PDM, 208, **SIZES)["package_id"]
    assert {case["part"] for case in first["pairs"].values()} == {"A", "B"}
    assert len(first["pairs"]) == 8 and len(first["corrections"]) == 3 and len(first["slice"]) == 12


def test_sheet_hides_parts_and_system_decisions(packet):
    summary, key = packet
    wb = load_workbook(summary["sheet"])
    assert wb["Como revisar"][PACKAGE_CELL].value == key["package_id"]
    pairs = wb["Mesmo item"]
    assert [cell.value for cell in pairs[1]] == ["Caso", pairs["B1"].value, "MESMO ITEM?", "Evidência"]
    assert pairs.max_column == 4
    text = "\n".join(str(cell.value or "") for row in pairs.iter_rows() for cell in row)
    for leak in ("system", "sistema diz", "PARTE", "tokens_v1", "identity"):
        assert leak not in text
    assert all(row[2] is None for row in pairs.iter_rows(min_row=2, values_only=True))
    assert not any("identity_key" in str(cell.value) for row in wb["Manual"].iter_rows() for cell in row)


def test_reviewer_agreeing_with_the_system(packet, tmp_path):
    summary, key = packet
    result = experiment_result(summary["key"], [fill(summary, key, tmp_path / "r1.xlsx", "Ana")])
    precision = result["merges_proposed"]["precision"]
    assert precision["numerator"] == precision["denominator"] == 4
    assert precision["interval"]["method"] == "WILSON" and precision["interval"]["upper"] == 1.0
    assert result["similar_pairs_not_merged"]["missed_duplicates"] == 0
    assert result["lot_descriptions"]["correct"]["value"] == 1.0
    assert result["manual_task"][0]["minutes"] == 30
    assert result["system_errors"] == [] and result["authorizes_merge"] is False


def test_disagreement_and_doubt_become_inconclusive_without_majority(packet, tmp_path):
    summary, key = packet
    a_case = next(c for c, v in key["pairs"].items() if v["part"] == "A")
    b_case = next(c for c, v in key["pairs"].items() if v["part"] == "B")
    other_a = next(c for c, v in key["pairs"].items() if v["part"] == "A" and c != a_case)
    first = fill(summary, key, tmp_path / "r1.xlsx", "Ana", flip_pairs={a_case})
    second = fill(summary, key, tmp_path / "r2.xlsx", "Bruno", flip_pairs={b_case}, unsure={other_a})
    result = experiment_result(summary["key"], [first, second])
    assert result["merges_proposed"]["inconclusive"] == 2  # divergência em a_case, dúvida em other_a
    assert result["merges_proposed"]["precision"]["denominator"] == 2
    assert result["similar_pairs_not_merged"]["inconclusive"] == 1
    assert result["reviewer_agreement_on_pairs"]["denominator"] == 7

    single = experiment_result(summary["key"], [first])
    assert [error["case"] for error in single["system_errors"]] == [a_case]


def test_wrong_package_same_reviewer_or_tampered_key_are_refused(packet, tmp_path):
    summary, key = packet
    sheet = fill(summary, key, tmp_path / "r1.xlsx", "Ana")
    with pytest.raises(ExperimentError, match="mesmo revisor"):
        experiment_result(summary["key"], [sheet, fill(summary, key, tmp_path / "r2.xlsx", "ana")])
    other = tmp_path / "other.json"
    tampered = {**key, "seed": 1}
    other.write_text(json.dumps(tampered))
    with pytest.raises(ExperimentError, match="alterada"):
        experiment_result(str(other), [sheet])
    wb = load_workbook(sheet)
    wb["Como revisar"][PACKAGE_CELL] = "outro"
    wb.save(tmp_path / "wrong.xlsx")
    with pytest.raises(ExperimentError, match="pacote"):
        experiment_result(summary["key"], [str(tmp_path / "wrong.xlsx")])
    unnamed = load_workbook(sheet)
    unnamed["Como revisar"][REVIEWER_CELL] = None
    unnamed.save(tmp_path / "unnamed.xlsx")
    with pytest.raises(ExperimentError, match="sem nome"):
        experiment_result(summary["key"], [str(tmp_path / "unnamed.xlsx")])


def test_workbook_rows_follow_the_key(packet):
    _, key = packet
    wb = workbook(key)
    assert [row[0] for row in wb["Mesmo item"].iter_rows(min_row=2, values_only=True)] == list(key["pairs"])
    assert [row[1] for row in wb["Manual"].iter_rows(min_row=4, values_only=True)] == key["slice_order"]


def test_cli_generates_and_scores(packet, tmp_path, capsys):
    summary, key = packet
    sheet = fill(summary, key, tmp_path / "r1.xlsx", "Ana")
    assert main(["experiment-result", summary["key"], sheet]) == 0
    assert json.loads(capsys.readouterr().out)["package_id"] == key["package_id"]
    with pytest.raises(SystemExit):
        main(["experiment-packets", CSV, "--pdm-workbook", PDM, "--out-dir", str(tmp_path), "--pairs", "0"])


@pytest.mark.parametrize(
    "sheet,cell,value",
    [
        ("Mesmo item", "A3", "P001"),
        ("Mesmo item", "B2", "edited material"),
        ("Descrição", "C2", "edited original"),
        ("Manual", "B4", "unknown"),
        ("Mesmo item", "C2", "SI"),
        ("Mesmo item", "C2", "=1+1"),
    ],
)
def test_mutated_review_is_rejected(packet, tmp_path, sheet, cell, value):
    summary, key = packet
    path = fill(summary, key, tmp_path / "mutated.xlsx", "Ana")
    wb = load_workbook(path)
    wb[sheet][cell] = value
    wb.save(path)
    with pytest.raises(ExperimentError):
        experiment_result(summary["key"], [path])


def test_missing_evidence_is_inconclusive(packet, tmp_path):
    summary, key = packet
    path = fill(summary, key, tmp_path / "empty.xlsx", "Ana")
    wb = load_workbook(path)
    for row in wb["Mesmo item"].iter_rows(min_row=2):
        row[3].value = None
    wb.save(path)
    result = experiment_result(summary["key"], [path])
    assert result["merges_proposed"]["precision"]["denominator"] == 0


def test_cardinality_balanced_and_complete_digest(packet):
    from collections import Counter

    from pipelines.experiment import package_id

    _, key = packet
    assert Counter(len(v["codes"]) for v in key["pairs"].values() if v["part"] == "A") == Counter(
        len(v["codes"]) for v in key["pairs"].values() if v["part"] == "B"
    )
    for field in ("frames", "sizes", "implementation"):
        changed = {**key, field: {"tampered": True}}
        assert package_id(changed) != key["package_id"]


def test_raw_formula_text_stays_plain(packet, tmp_path):
    import copy

    _, key = packet
    key = copy.deepcopy(key)
    case = next(iter(key["corrections"].values()))
    case["original"] = "=1+1"
    case["proposed"] = "=2+2"
    wb = workbook(key)
    assert wb["Descrição"]["C2"].data_type == "s"
    assert wb["Descrição"]["C2"].value == "=1+1"
    path = tmp_path / "literal.xlsx"
    wb.save(path)
    restored = load_workbook(path)
    assert restored["Descrição"]["C2"].data_type == "s"
    assert restored["Descrição"]["D2"].value == "=2+2"


def test_row_reordering_is_valid(packet, tmp_path):
    summary, key = packet
    path = fill(summary, key, tmp_path / "reordered.xlsx", "Ana")
    wb = load_workbook(path)
    sheet = wb["Mesmo item"]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    for index, values in enumerate(reversed(rows), 2):
        for column, value in enumerate(values, 1):
            sheet.cell(index, column).value = value
    wb.save(path)
    assert experiment_result(summary["key"], [path])["merges_proposed"]["precision"]["denominator"] == 4


@pytest.mark.parametrize("field", ["implementation", "frames", "sizes", "system_merge_pairs", "layout"])
def test_key_provenance_mutation_is_rejected(packet, tmp_path, field):
    summary, key = packet
    modified = {**key, field: "modified"}
    key_path = tmp_path / "bad.json"
    key_path.write_text(json.dumps(modified))
    path = fill(summary, key, tmp_path / "valid.xlsx", "Ana")
    with pytest.raises(ExperimentError, match="alterada"):
        experiment_result(str(key_path), [path])


def test_same_key_is_not_a_merge_decision(packet, tmp_path):
    import copy

    from pipelines.experiment import package_id

    summary, key = packet
    modified = copy.deepcopy(key)
    for item in modified["slice"].values():
        item["identity_key"] = "same retrieval key with conflicting attributes"
    modified["system_merge_pairs"] = []
    modified["package_id"] = package_id(modified)
    key_path = tmp_path / "key.json"
    key_path.write_text(json.dumps(modified))
    base = tmp_path / "base.xlsx"
    workbook(modified).save(base)
    path = fill({"sheet": str(base)}, modified, tmp_path / "review.xlsx", "Ana")
    manual = experiment_result(str(key_path), [path])["manual_task"][0]
    assert manual["duplicate_pairs"]["person"] > 0
    assert manual["duplicate_pairs"]["system_among_grouped"] == 0


def test_duplicate_reviewer_names_normalize_whitespace(packet, tmp_path):
    summary, key = packet
    paths = [fill(summary, key, tmp_path / f"{i}.xlsx", name) for i, name in enumerate(["Ana Maria", "  ANA   MARIA "])]
    with pytest.raises(ExperimentError, match="mesmo revisor"):
        experiment_result(summary["key"], paths)


def test_csv_hash_and_analysis_use_one_snapshot(monkeypatch):
    import hashlib

    actual_read = Path.read_bytes
    calls = []

    def changing_read(path):
        if str(path) == CSV:
            calls.append(path)
            return actual_read(path) if len(calls) == 1 else b"changed after snapshot"
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", changing_read)
    key = select(CSV, PDM, **SIZES)
    assert len(calls) == 1
    assert key["dataset_sha256"] == hashlib.sha256(actual_read(Path(CSV))).hexdigest()


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "extra", "swapped_code", "edited_unit", "formula_note"])
def test_schema_and_all_row_ids_bound(packet, tmp_path, mutation):
    summary, key = packet
    path = fill(summary, key, tmp_path / "bad-rows.xlsx", "Ana")
    wb = load_workbook(path)
    sheet = wb["Manual"]
    if mutation == "duplicate":
        for column in range(1, 7):
            sheet.cell(5, column).value = sheet.cell(4, column).value
    elif mutation == "missing":
        sheet.delete_rows(4)
    elif mutation == "extra":
        sheet.append(["extra", "unknown", "text", "PC"])
    elif mutation == "swapped_code":
        sheet["B4"], sheet["B5"] = sheet["B5"].value, sheet["B4"].value
    elif mutation == "edited_unit":
        sheet["D4"] = "edited"
    else:
        wb["Descrição"]["G2"] = "=1+1"
    wb.save(path)
    with pytest.raises(ExperimentError):
        experiment_result(summary["key"], [path])


def test_unsubstantiated_corrections_are_inconclusive(packet, tmp_path):
    summary, key = packet
    path = fill(summary, key, tmp_path / "no-notes.xlsx", "Ana")
    wb = load_workbook(path)
    for row in wb["Descrição"].iter_rows(min_row=2):
        row[6].value = None
    wb.save(path)
    result = experiment_result(summary["key"], [path])
    assert result["lot_descriptions"]["correct"]["denominator"] == 0
    assert result["lot_descriptions"]["lost_information"]["denominator"] == 0


def test_control_groups_keep_unproposed_pair_and_full_a_groups(packet):
    from pipelines.experiment import _pairs

    _, key = packet
    proposals = {tuple(item["codes"]) for item in key["frames"]["merges_frame"]}
    proposed_pairs = set().union(*(_pairs(codes) for codes in proposals))
    for case in key["pairs"].values():
        if case["part"] == "A":
            assert tuple(sorted(case["codes"])) in proposals
        else:
            assert _pairs(case["codes"]) - proposed_pairs


def nullable_packet_key():
    return {
        "package_id": "nullable-protected-roundtrip",
        "pairs": {"P001": {"members": [""]}},
        "corrections": {"D001": {"code": "001", "original": "", "proposed": None}},
        "slice_order": ["001"],
        "slice": {"001": {"description": "", "unit": ""}},
    }


def test_nullable_protected_cells_roundtrip(tmp_path):
    from pipelines.experiment_result import _validate_workbook

    key = nullable_packet_key()
    path = tmp_path / "nullable.xlsx"
    workbook(key).save(path)
    restored = load_workbook(path)
    assert restored["Manual"]["D4"].value is None
    assert restored["Manual"]["B4"].value == "001"
    assert restored["Manual"]["B4"].data_type == "s"
    _validate_workbook(restored, key)


@pytest.mark.parametrize(
    "sheet,cell,value",
    [
        ("Manual", "D4", " "),
        ("Manual", "B4", 1),
        ("Descrição", "C2", " "),
        ("Descrição", "D2", "=1+1"),
    ],
)
def test_nullable_protected_cells_still_reject_changes(tmp_path, sheet, cell, value):
    from pipelines.experiment_result import _validate_workbook

    key = nullable_packet_key()
    path = tmp_path / "nullable-edited.xlsx"
    wb = workbook(key)
    wb[sheet][cell] = value
    wb.save(path)
    with pytest.raises(ExperimentError):
        _validate_workbook(load_workbook(path), key)
