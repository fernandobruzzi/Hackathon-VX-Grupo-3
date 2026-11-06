"""Amostra reproduzível de propostas de unificação, para revisão manual da precisão.

A amostra é sorteada com semente fixa entre todas as unificações da base, ordenadas pelo id. Assim,
quem prepara uma nova revisão consegue reproduzir a seleção. Coortes já revisadas permanecem
congeladas em `pipelines/evaluation_data/`; uma nova amostra não substitui seus rótulos.
"""

import random

from domain.contracts import MergeProposal

SEED = 32
SIZE = 40


def sample_merges(merges: list[MergeProposal], size: int = SIZE, seed: int = SEED) -> list[MergeProposal]:
    ordered = sorted(merges, key=lambda proposal: proposal.id)
    return random.Random(seed).sample(ordered, min(size, len(ordered)))


def describe(proposal: MergeProposal) -> dict:
    """O que um revisor precisa ler: textos originais, fabricante, referência e atributos extraídos."""
    return {
        "codes": list(proposal.material_codes),
        "pdm_class_id": proposal.changeset["pdm_class_id"],
        "match_type": proposal.changeset["match_type"],
        "conflicts": list(proposal.conflicts),
        "members": [
            {
                "code": member["material_code"],
                "description": member["description"],
                "unit": member["unit"],
                "ncm": member["ncm"],
                "attributes": member["attributes"],
            }
            for member in proposal.members
        ],
    }
