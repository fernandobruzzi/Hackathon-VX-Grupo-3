"""Identidade exata, mais pares parecidos em texto e sem nenhum conflito nos campos conhecidos.

Tokens só encontram candidatos: M12 e M14 são quase iguais como texto. Quem decide é a comparação
de atributos, e esses pares seguem como não verificados, para revisão de uma pessoa.
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict

from domain.contracts import AnalyzedMaterial, CandidateGroup, MatchType, PdmCatalog
from domain.identity import compare_attributes
from repositories.candidates.exact_identity_v1 import ELIGIBLE_STATUS, ExactIdentityV1CandidateRepository

_STOP_WORDS = frozenset({"A", "COM", "DA", "DE", "DO", "E", "O", "P/", "PARA"})
_ABBREVIATIONS = {
    "AC": "ACO",
    "APLIC": "APLICACAO",
    "COMP": "COMPRIMENTO",
    "COMPR": "COMPRIMENTO",
    "DIAM": "DIAMETRO",
    "ELET": "ELETRICO",
    "ESF": "ESFERA",
    "FAB": "FABRICANTE",
    "FABR": "FABRICANTE",
    "FILT": "FILTRO",
    "HID": "HIDRAULICA",
    "HIDR": "HIDRAULICA",
    "MANG": "MANGUEIRA",
    "MANG.": "MANGUEIRA",
    "MAT": "MATERIAL",
    "MONT": "MONTADA",
    "PARAF": "PARAFUSO",
    "PARAF.": "PARAFUSO",
    "ROL": "ROLAMENTO",
    "ROL.": "ROLAMENTO",
    "SEXT": "SEXTAVADO",
    "SEXT.": "SEXTAVADO",
    "SEXTAVADA": "SEXTAVADO",
    "VALV": "VALVULA",
    "VALV.": "VALVULA",
}
# Um token raro de verdade identifica poucos itens; acima disso só gera ruído.
_MAX_POSTINGS = 60
_MIN_SCORE = 0.35
_MIN_MATCHING_REQUIRED = 2
_TOP_PER_MATERIAL = 3
# Sempre abaixo da identidade exata, que vale 1.0.
_SCORE_CEILING = 0.9


def tokens(text: str) -> list[str]:
    """Normaliza medidas, abreviações e códigos, para grafias diferentes virarem o mesmo token."""
    decomposed = unicodedata.normalize("NFKD", text)
    upper = "".join(c for c in decomposed if not unicodedata.combining(c)).upper()
    upper = re.sub(r"\b(\d+)\s*(MM2|MM|POL|BAR|PSI)\b", r"\1\2", upper)
    upper = re.sub(r'(\d)"', r"\1POL", upper)
    upper = re.sub(r"\bM[\s\-](\d)", r"M\1", upper)
    result: list[str] = []
    number = ""
    for word in re.split(r"[\s,;:]+", upper):
        word = _ABBREVIATIONS.get(word, word).strip(".-")
        if not word or word in _STOP_WORDS:
            continue
        if any(c.isdigit() for c in word):
            word = re.sub(r"[.\-/]", "", re.sub(r"-00$", "", word))
        # Código partido, como 2908 8890 82, vira um token só.
        if word.isdigit():
            number += word
            continue
        if number:
            result.append(number)
            number = ""
        result.append(word)
    if number:
        result.append(number)
    return result


class TokensV1CandidateRepository:
    name = "tokens_v1"

    def find(self, materials: list[AnalyzedMaterial], catalog: PdmCatalog) -> list[CandidateGroup]:
        groups = ExactIdentityV1CandidateRepository().find(materials, catalog)
        already_grouped = {code for group in groups for code in group.codes}
        by_class: dict[str, list[AnalyzedMaterial]] = defaultdict(list)
        for material in materials:
            if material.pdm_class_id and material.record.status == ELIGIBLE_STATUS:
                by_class[material.pdm_class_id].append(material)
        for class_id, members in sorted(by_class.items()):
            groups.extend(self._compatible_pairs(members, catalog.classes[class_id], already_grouped))
        return groups

    def _compatible_pairs(self, members, pdm_class, already_grouped) -> list[CandidateGroup]:
        documents = {}
        for material in members:
            text = " ".join([material.record.description, *material.attributes.values()])
            documents[material.record.code] = Counter(tokens(text))
        frequency = Counter(token for document in documents.values() for token in document)
        total = len(documents)
        weights = {token: math.log((1 + total) / (1 + count)) for token, count in frequency.items()}
        norms = {
            code: math.sqrt(sum((weights[token] * count) ** 2 for token, count in document.items())) or 1.0
            for code, document in documents.items()
        }
        postings: dict[str, list[str]] = defaultdict(list)
        for code, document in documents.items():
            for token in document:
                if frequency[token] <= _MAX_POSTINGS:
                    postings[token].append(code)

        by_code = {material.record.code: material for material in members}
        pairs: dict[tuple[str, str], float] = {}
        for code, document in sorted(documents.items()):
            scores: Counter[str] = Counter()
            for token, count in document.items():
                for other in postings.get(token, ()):
                    if other != code:
                        scores[other] += weights[token] * count * weights[token] * documents[other][token]
            ranked = sorted(scores, key=lambda other: (-scores[other], other))
            accepted = 0
            for other in ranked:
                score = scores[other] / (norms[code] * norms[other])
                if score < _MIN_SCORE or accepted == _TOP_PER_MATERIAL:
                    break
                if {code, other} <= already_grouped and by_code[code].identity_key == by_code[other].identity_key:
                    continue
                if self._compatible(pdm_class, by_code[code], by_code[other]):
                    pairs[tuple(sorted((code, other)))] = round(min(score, 1.0) * _SCORE_CEILING, 4)
                    accepted += 1
        return [
            CandidateGroup(codes, MatchType.COMPATIBLE_ATTRIBUTES, False, score)
            for codes, score in sorted(pairs.items())
        ]

    @staticmethod
    def _compatible(pdm_class, first: AnalyzedMaterial, second: AnalyzedMaterial) -> bool:
        if first.item_name and second.item_name and first.item_name != second.item_name:
            return False
        conflicts, matching = compare_attributes(pdm_class, first.attributes, second.attributes)
        return not conflicts and matching >= _MIN_MATCHING_REQUIRED
