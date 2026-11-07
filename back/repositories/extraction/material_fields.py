"""Extrai campos independentes e mantém contradições fora da identidade automática."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from domain.contracts import ExtractedAttribute, ExtractionRepository, PdmClass
from domain.identity import manufacturer_key, reference_spelling_key
from repositories.extraction import get_extraction_repository
from repositories.extraction.rule_based_v1 import (
    _LINE_BREAK,
    _REFERENCE_LABELS,
    _SEGMENTS,
    _clean_text,
    labeled_spans,
)
from repositories.extraction.rule_based_v1_tables import KEY_ALIASES

MATERIAL_FIELDS_VERSION = "independent-fields-v2"
_SHORT_LIMIT = 40
_FREE_IDENTITY_FIELDS = frozenset({"REFERENCIA FABRICANTE", "REFERENCIA"})


@dataclass(frozen=True)
class MaterialFieldExtraction:
    attributes: dict[str, ExtractedAttribute]
    conflicts: dict[str, list[str]]
    origins: dict[str, str]


def _safe_short_text(text: str) -> tuple[str, bool]:
    # O kit corta a descrição curta em 40 caracteres, inclusive no meio de PN e medidas.
    truncated = len(text) >= _SHORT_LIMIT
    if truncated:
        text = re.sub(r"\S+\s*$", "", text)
    return text, truncated


def _spelling(name: str, value: str) -> str:
    if name in {"REFERENCIA FABRICANTE", "REFERENCIA"}:
        return reference_spelling_key(value)
    return manufacturer_key(value) if name == "FABRICANTE" else value


def _open_reference_tail(cls: PdmClass, text: str, name: str, spelling: str) -> bool:
    if not spelling or re.search(r"[;,\n]\s*$", text):
        return False
    segment = _SEGMENTS.split(_clean_text(_LINE_BREAK.sub(" ; ", text)))[-1]
    if not reference_spelling_key(segment).endswith(spelling):
        return False
    spans = labeled_spans((a.name for a in cls.attributes), segment)
    if not spans:
        return True
    label = spans[-1][2]
    return label in _REFERENCE_LABELS or name in {label, *KEY_ALIASES.get(label, ())}


def extract_material_fields(
    cls: PdmClass,
    description: str,
    short_description: str = "",
    *,
    manufacturer: str = "",
    reference: str = "",
    extractor: ExtractionRepository | None = None,
) -> MaterialFieldExtraction:
    """Combina apenas leituras concordantes; nenhum campo mascara outro por precedência.

    Uma descrição curta possivelmente cortada não comprova referências livres. Medidas e
    enums completos anteriores à cauda ainda podem contribuir. Cada atributo conserva origem,
    texto e regra; valores divergentes ficam em `conflicts`, sem escolher um vencedor.
    """
    extractor = extractor or get_extraction_repository()
    observations = defaultdict(list)
    short_text, truncated = _safe_short_text(short_description or "")
    for origin, text, fields in (
        ("description", description or "", {}),
        ("short_description", short_text, {}),
        ("manufacturer", "", {"manufacturer": manufacturer or None}),
        ("reference", "", {"manufacturer_reference": reference or None}),
    ):
        if not text and not any(fields.values()):
            continue
        found = extractor.extract(cls, text, **fields).attributes
        for name, attr in found.items():
            if not (origin == "short_description" and truncated and name in _FREE_IDENTITY_FIELDS):
                observations[name].append((attr, origin))
        # A leitura inteira só retorna o primeiro rótulo; revisar rótulos repetidos separadamente
        # impede que MATERIAL: X; MATERIAL: Y se torne uma observação aparentemente inequívoca.
        pieces = []
        counts = Counter()
        attribute_names = {a.name for a in cls.attributes}
        for segment in _SEGMENTS.split(_clean_text(_LINE_BREAK.sub(" ; ", text))):
            spans = labeled_spans(attribute_names, segment)
            for index, (start, _, label) in enumerate(spans):
                stop = spans[index + 1][0] if index + 1 < len(spans) else len(segment)
                names = {label, *KEY_ALIASES.get(label, ())} & attribute_names
                if label in _REFERENCE_LABELS:
                    names |= {"REFERENCIA FABRICANTE", "REFERENCIA"} & attribute_names
                counts.update(names)
                pieces.append((names, segment[start:stop]))
        for names, piece in pieces:
            repeated = {name for name in names if counts[name] > 1}
            if not repeated:
                continue
            for name, attr in extractor.extract(cls, piece).attributes.items():
                if name in repeated and not (
                    origin == "short_description" and truncated and name in _FREE_IDENTITY_FIELDS
                ):
                    observations[name].append((attr, origin))
    conflicts, attributes, origins = {}, {}, {}
    for name, values in observations.items():
        if name in _FREE_IDENTITY_FIELDS:
            supported = {_spelling(name, attr.value) for attr, origin in values if origin != "short_description"}
            if len(supported) == 1:
                full = next(iter(supported))
                # Algumas curtas do kit têm 39 caracteres e terminam em PN parcial. Um prefixo
                # estrito na cauda aberta não é outro PN e nunca completa a identidade sozinho.
                values = [
                    (attr, origin)
                    for attr, origin in values
                    if not (
                        origin == "short_description"
                        and full.startswith(_spelling(name, attr.value))
                        and full != _spelling(name, attr.value)
                        and _open_reference_tail(cls, short_description or "", name, _spelling(name, attr.value))
                    )
                ]
        if len({_spelling(name, attr.value) for attr, _ in values}) > 1:
            conflicts[name] = sorted({attr.value for attr, _ in values})
        else:
            attributes[name], origins[name] = values[0]
    return MaterialFieldExtraction(attributes, conflicts, origins)
