"""Precisão das unificações numa amostra aleatória da base inteira, revisada à mão.

Diferente de `merge_review.json`, que tem pares escolhidos durante o desenvolvimento, esta amostra é
sorteada entre todas as propostas MERGE, então estima a precisão do que vai para a fila.
"""

import json
from pathlib import Path

import pytest

from pipelines.merge_sample import SEED, SIZE, sample_merges
from pipelines.sanitize import _catalog, _propose, read_csv_records

KIT = Path(__file__).parents[2] / "data" / "desafio01"
SAMPLE = Path(__file__).parent / "fixtures" / "merge_precision_sample.json"


@pytest.fixture(scope="module")
def sample():
    merges, _, _ = _propose(
        read_csv_records(str(KIT / "01_base_materiais.csv")), _catalog(str(KIT / "03_padrao_cadastro_PDM.xlsx")), None
    )
    return sample_merges(merges)


@pytest.fixture(scope="module")
def reviewed():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_is_the_one_that_was_reviewed(sample, reviewed):
    # Se falhar, as propostas mudaram: sorteie e revise de novo antes de comparar precisão.
    assert (reviewed["seed"], reviewed["size"]) == (SEED, SIZE)
    assert [list(proposal.material_codes) for proposal in sample] == [item["codes"] for item in reviewed["reviewed"]]


def test_merge_precision_on_random_sample(reviewed):
    decided = [item for item in reviewed["reviewed"] if item["same_item"] is not None]
    precision = sum(item["same_item"] for item in decided) / len(decided)
    assert len(decided) == SIZE
    # Medido: 38 de 40. O mínimo só deve subir.
    assert precision >= 0.95
