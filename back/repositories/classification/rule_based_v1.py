"""Nomes do PDM com limites de palavras; duvida nunca vira classe por pontuacao."""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from domain.contracts import (
    ClassificationEvidence,
    ClassificationInput,
    ClassificationResult,
    ClassificationStatus,
    PdmCatalog,
)

_CONNECTORS = frozenset({"DA", "DAS", "DE", "DO", "DOS"})
_TEXT_FIELDS = ("description", "short_description", "attachment_text")


def _plain(text: str | None) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").upper())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _tokens(text: str | None) -> tuple[str, ...]:
    return tuple(word for word in re.findall(r"[A-Z0-9]+", _plain(text)) if word not in _CONNECTORS)


@dataclass(frozen=True)
class _Match:
    class_id: str
    name: str
    source: str
    start: int
    end: int


class RuleBasedV1ClassificationRepository:
    name = "rule_based_v1"

    def __init__(self, catalog: PdmCatalog):
        self.catalog = catalog
        names: dict[tuple[str, ...], list[tuple[str, str]]] = defaultdict(list)
        self.families: dict[str, set[str]] = defaultdict(set)
        for class_id, pdm_class in sorted(catalog.classes.items()):
            for name in pdm_class.item_names:
                words = _tokens(name)
                if not words:
                    raise ValueError(f"Nome vazio na classe {class_id}")
                names[words].append((class_id, name))
                self.families[words[0]].add(class_id)
        self.names = dict(names)
        self.lengths = sorted({len(words) for words in names})
        labels = sorted(
            {_plain(attribute.name) for pdm_class in catalog.classes.values() for attribute in pdm_class.attributes},
            key=lambda name: (-len(name), name),
        )
        self.attribute_labels = re.compile(r"\b(?:" + "|".join(re.escape(label) for label in labels) + r")\s*:")

    def classify(self, item: ClassificationInput) -> ClassificationResult:
        matches = []
        partial_candidates: set[str] = set()
        has_text = False
        for field in _TEXT_FIELDS:
            # EIXO em "DIAMETRO EIXO:" e REVESTIMENTO como rotulo nao sao produtos.
            # O marcador impede unir palavras dos dois lados de um rotulo removido.
            words = _tokens(self.attribute_labels.sub(" ATRIBUTOPDM ", _plain(getattr(item, field))))
            has_text |= bool(words)
            for word in words:
                partial_candidates.update(self.families.get(word, ()))
            field_matches = []
            for length in self.lengths:
                for start in range(len(words) - length + 1):
                    for class_id, name in self.names.get(words[start : start + length], ()):
                        if name == "EIXO" and start and words[start - 1] in {"DIAMETRO", "DIAM"}:
                            continue
                        field_matches.append(_Match(class_id, name, field, start, start + length))
            # INTERNO deve prevalecer sobre PARAFUSO SEXTAVADO no mesmo trecho;
            # referencias a classes diferentes em trechos distintos continuam ambiguas.
            matches.extend(
                match
                for match in field_matches
                if not any(
                    other.start <= match.start
                    and match.end <= other.end
                    and other.end - other.start > match.end - match.start
                    for other in field_matches
                )
            )

        evidence = []
        candidates: set[str] = set()
        ambiguous_name = False
        group = " ".join(_tokens(item.merchandise_group))
        for match in matches:
            words = _tokens(match.name)
            alternatives = self.families[words[0]] if len(words) == 1 else {match.class_id}
            needs_group = len(alternatives) > 1 or (len(words) == 1 and len(words[0]) < 4)
            if needs_group and group != self.catalog.classes[match.class_id].group:
                candidates.update(alternatives)
                ambiguous_name = True
                rule = "name.requires_group"
            else:
                candidates.add(match.class_id)
                rule = "name.exact_with_group" if needs_group else "name.exact"
            evidence.append(ClassificationEvidence(match.class_id, match.source, match.name, f"{self.name}/{rule}"))

        if len(candidates) == 1 and not ambiguous_name:
            class_id = next(iter(candidates))
            pdm_class = self.catalog.classes[class_id]
            if group:
                group_rule = "group.supports" if group == pdm_class.group else "group.mismatch"
                evidence.append(
                    ClassificationEvidence(class_id, "merchandise_group", pdm_class.group, f"{self.name}/{group_rule}")
                )
            status, rule = ClassificationStatus.CLASSIFIED, "name.unique"
        else:
            class_id = None
            candidates.update(partial_candidates)
            if not has_text:
                status, rule = ClassificationStatus.UNRESOLVED, "text.missing"
            elif candidates:
                status, rule = ClassificationStatus.UNRESOLVED, "name.ambiguous_or_incomplete"
            else:
                status, rule = ClassificationStatus.OUT_OF_SCOPE, "name.no_match"

        return ClassificationResult(
            original=item,
            status=status,
            pdm_class_id=class_id,
            candidate_class_ids=tuple(sorted(candidates)),
            evidence=tuple(sorted(set(evidence), key=lambda e: (e.source_field, e.class_id, e.matched_name, e.rule))),
            rule=f"{self.name}/{rule}",
            pdm_version=self.catalog.version,
            pdm_source_sha256=self.catalog.source_sha256,
        )
