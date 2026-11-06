"""Regras do rule_based_v1 com aliases técnicos inequívocos aplicados antes da busca de nomes.

O texto original continua em `ClassificationResult.original`. Cada alias usado vira uma evidência
com o trecho como foi escrito e a regra `aliases_v1/alias.<id>`, para quem revisa saber de onde a
classe veio. Os aliases não inventam atributos: a extração lê o texto original.
"""

from domain.contracts import ClassificationEvidence
from repositories.classification.aliases_v1_tables import ALIASES, Alias
from repositories.classification.rule_based_v1 import RuleBasedV1ClassificationRepository, _Note


def expand(words: tuple[str, ...], aliases: tuple[Alias, ...] = ALIASES) -> tuple[tuple[str, ...], list[Alias]]:
    """Troca cada padrão pela forma do PDM, da esquerda para a direita, sem reaplicar no resultado."""
    result: list[str] = []
    used: list[Alias] = []
    position = 0
    while position < len(words):
        alias = next((a for a in aliases if words[position : position + len(a.pattern)] == a.pattern), None)
        if alias is None:
            result.append(words[position])
            position += 1
            continue
        result.extend(alias.replacement)
        used.append(alias)
        position += len(alias.pattern)
    return tuple(result), used


class AliasesV1ClassificationRepository(RuleBasedV1ClassificationRepository):
    name = "aliases_v1"
    revision = "1"

    def _words(self, field, text, notes):
        words, used = expand(super()._words(field, text, notes))
        notes.extend(_Note(field, " ".join(alias.pattern), f"alias.{alias.id}") for alias in used)
        return words

    def _note_evidence(self, notes, class_ids):
        return [
            ClassificationEvidence(class_id, note.source, note.original, f"{self.name}/{note.rule}")
            for note in notes
            for class_id in sorted(class_ids)
        ]
