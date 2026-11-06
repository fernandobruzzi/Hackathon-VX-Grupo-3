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
    assert [row[1] for row in wb["Manual"].iter_rows(min_row=4, values_only=True)] == list(key["slice"])


def test_cli_generates_and_scores(packet, tmp_path, capsys):
    summary, key = packet
    sheet = fill(summary, key, tmp_path / "r1.xlsx", "Ana")
    assert main(["experiment-result", summary["key"], sheet]) == 0
    assert json.loads(capsys.readouterr().out)["package_id"] == key["package_id"]
    with pytest.raises(SystemExit):
        main(["experiment-packets", CSV, "--pdm-workbook", PDM, "--out-dir", str(tmp_path), "--pairs", "0"])
