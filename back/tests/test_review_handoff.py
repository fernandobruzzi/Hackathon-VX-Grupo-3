"""O preparo da revisão preserva entradas e nunca produz um gabarito."""

import csv
import hashlib
import json
import random
from pathlib import Path

import pytest

from cli import main
from pipelines.review_handoff import review_handoff

KIT = Path(__file__).parents[2] / "data/desafio01"
PDM = KIT / "03_padrao_cadastro_PDM.xlsx"


@pytest.fixture
def source(tmp_path):
    # Dois grupos elegíveis e um par REV A retido pela #73; nenhum rótulo entra no preparo.
    codes = {"17497904", "26546628", "15360049", "19452731", "18540640", "20031324"}
    with (KIT / "01_base_materiais.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = [row for row in reader if row["CODIGO_MATERIAL"] in codes]
    path = tmp_path / "materials.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path, rows


def test_handoff_is_repeatable_with_a_frozen_frame_and_blank_reviews(source):
    path, rows = source
    packet = review_handoff(str(path), str(PDM), size=1, seed=113)
    assert packet == review_handoff(str(path), str(PDM), size=1, seed=113)
    assert packet["kind"] == "REVIEW_PREPARATION"
    assert packet["independent_review"] is False
    assert packet["authorizes_publication"] is False
    assert packet["authorizes_merge"] is False
    assert "precision" not in packet
    assert packet["sources"]["dataset_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert packet["sources"]["pdm_sha256"] == hashlib.sha256(PDM.read_bytes()).hexdigest()
    assert "pipelines/review_handoff.py" in packet["implementation"]["files"]
    assert len(packet["sampling"]["frame"]) == 2
    assert len(packet["review_cases"]) == 1
    frame = packet["sampling"]["frame"]
    assert {tuple(item["codes"]) for item in frame} == {
        ("15360049", "19452731"),
        ("18540640", "20031324"),
    }
    assert packet["sampling"]["selected_ids"] == [p["id"] for p in random.Random(113).sample(frame, 1)]
    assert (
        packet["sampling"]["frame_sha256"]
        == hashlib.sha256(json.dumps(frame, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    )
    assert (
        packet["packet_sha256"]
        == hashlib.sha256(
            json.dumps(
                {k: v for k, v in packet.items() if k != "packet_sha256"}, ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
    )
    assert set(packet["sampling"]["selected_ids"]) <= {p["id"] for p in packet["sampling"]["frame"]}
    originals = {row["CODIGO_MATERIAL"]: row for row in rows}
    for case in packet["review_cases"]:
        assert "attributes" not in case and "pdm_class_id" not in case
        assert case["group_review"] == {
            "author": None,
            "participated_in_rule_adjustment": None,
            "label": None,
            "evidence": [],
            "conflicts": [],
        }
        prediction = packet["predictions"][case["id"]]
        assert {m["code"] for m in prediction["members"]} == set(case["codes"])
        for member in case["members"]:
            assert member["original"] == originals[member["code"]]
            assert member["class_review"]["value"] is None
            assert member["class_review"]["author"] is None
            assert member["field_reviews"]
            assert all(
                f["value"] is None and f["author"] is None and not f["evidence"] for f in member["field_reviews"]
            )
    assert packet["historical_sources"] == []


def test_history_is_preserved_separately_without_inheriting_a_label(source, tmp_path):
    path, _ = source
    history = tmp_path / "history.json"
    document = {
        "source_commit": "historical-commit",
        "reviewed": [{"codes": ["17497904", "26546628"], "same_item": True, "note": "REV A sem confirmação"}],
    }
    history.write_text(json.dumps(document), encoding="utf-8")
    packet = review_handoff(str(path), str(PDM), size=40, historical_paths=[str(history)])
    assert len(packet["review_cases"]) == 2
    assert packet["historical_sources"] == [
        {
            "path": str(history),
            "sha256": hashlib.sha256(history.read_bytes()).hexdigest(),
            "document": document,
        }
    ]
    assert all(case["group_review"]["label"] is None for case in packet["review_cases"])


def test_cli_exports_only_json_and_refuses_an_invalid_size(source, capsys):
    path, _ = source
    assert main(["review-handoff", str(path), "--pdm-workbook", str(PDM), "--size", "1", "--seed", "113"]) == 0
    assert len(json.loads(capsys.readouterr().out)["review_cases"]) == 1
    with pytest.raises(ValueError, match="positivo"):
        review_handoff(str(path), str(PDM), size=0)


def test_duplicate_material_codes_are_refused(source):
    path, rows = source
    with path.open("a", encoding="utf-8", newline="") as stream:
        csv.DictWriter(stream, fieldnames=rows[0]).writerow(rows[0])
    with pytest.raises(ValueError, match="repetido"):
        review_handoff(str(path), str(PDM))
