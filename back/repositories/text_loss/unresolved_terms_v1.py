"""Perda de texto pelo que a extração não interpretou e a descrição proposta não traz.

A extração devolve em `unresolved` os trechos que nenhuma regra segura usou. Muitos já estão na
descrição proposta (nome do item, referência com outra pontuação), no campo de fabricante do
cadastro, ou são só rótulos e conectivos. Sobra o que se perderia: `ACO ESPECIAL` sem atributo de material, `TAMPA MOLA`
virando `TAMPA`, a classe `AR` de um fusível, a espessura de um rolamento.

Frases que a extração descarta como ruído (`REV A`, `REF ANTIGA`, `VER DESENHO`) não contam: o texto
original continua no "antes" da proposta, e o padrão do PDM não as inclui.
"""

import re
import unicodedata

from domain.contracts import AnalyzedMaterial, ExtractionRepository, PdmClass
from repositories.extraction.rule_based_v1_tables import KEY_ALIASES, VALUE_ALIASES

_REDIRECT_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")
_WORD = re.compile(r"[A-Z0-9]+(?:[./,-][A-Z0-9]+)*")
_PART = re.compile(r"[A-Z0-9]+")
_CONNECTORS = frozenset({"A", "C", "COM", "DA", "DAS", "DE", "DO", "DOS", "E", "EM", "NA", "NO", "O", "P", "PARA"})
# Rótulos de campo: o valor que vem depois deles é o que importa, e ele é conferido à parte.
_LABELS = frozenset(word for key in KEY_ALIASES for word in _PART.findall(key)) | frozenset(
    {
        "APLIC",
        "APLICACAO",
        "COD",
        "CODIGO",
        "CORR",
        "EQUIP",
        "EQUIPAMENTO",
        "ESP",
        "EXTREMIDADE",
        "EXTREMIDADES",
        "FAB",
        "FABR",
        "FABRICANTE",
        "LIGACAO",
        "MARCA",
        "MAT",
        "MATERIAL",
        "MOD",
        "MODELO",
        "NOM",
        "NUMBER",
        "NUMERO",
        "PART",
        "PN",
        "REF",
        "REFERENCIA",
        "TIPO",
        "USO",
    }
)
# Grafias que a extração não converte, mas cujo valor do PDM aparece na descrição proposta.
_COVERED_SPELLINGS: dict[str, tuple[str, ...]] = {
    **VALUE_ALIASES,
    "MA": ("METRICA GROSSA",),  # Rosca métrica grossa, designação ABNT.
    # "BORRACHA EPDM" vira "EPDM"; borracha sem o elastômero continua contando como perda.
    "BORRACHA": ("EPDM", "FKM", "NBR", "NEOPRENE", "SBR", "SILICONE"),
    "ROSCADA": ("ROSCA",),
}
# Código escrito em grupos (`8597 0256 05`): confere o código inteiro, não cada grupo.
_CODE_RUN = re.compile(r"(?<![A-Z0-9])[A-Z0-9./-]*\d[A-Z0-9./-]*(?:\s+[A-Z0-9./-]*\d[A-Z0-9./-]*)+")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.upper())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _fold(text))


class UnresolvedTermsV1TextLossRepository:
    name = "unresolved_terms_v1"

    def __init__(self, extractor: ExtractionRepository) -> None:
        self.extractor = extractor

    def lost_terms(self, material: AnalyzedMaterial, pdm_class: PdmClass, proposed: str) -> tuple[str, ...]:
        record = material.record
        unresolved = self.extractor.extract(
            pdm_class,
            _REDIRECT_PREFIX.sub("", record.description),
            manufacturer=record.manufacturer or None,
            manufacturer_reference=record.reference or None,
        ).unresolved
        after = _fold(proposed)
        # O fabricante tem campo próprio no cadastro, que a correção não altera: repeti-lo não é perda.
        after_words = set(_PART.findall(after)) | set(_PART.findall(_fold(record.manufacturer)))
        after_compact = _compact(proposed)
        lost: list[str] = []
        for piece in unresolved:
            piece = self._without_covered_codes(self._without_covered_spellings(_fold(piece), after), after_compact)
            for word in _WORD.findall(piece):
                if self._covered(word, after_words, after_compact):
                    continue
                lost.append(word)
        return tuple(dict.fromkeys(lost))

    @staticmethod
    def _without_covered_spellings(piece: str, after: str) -> str:
        for spelling, values in _COVERED_SPELLINGS.items():
            if any(value in after for value in values):
                piece = re.sub(rf"(?<![A-Z0-9]){re.escape(spelling)}(?![A-Z0-9])", " ", piece)
        return piece

    @staticmethod
    def _without_covered_codes(piece: str, after_compact: str) -> str:
        return _CODE_RUN.sub(lambda match: " " if _compact(match.group(0)) in after_compact else match.group(0), piece)

    @staticmethod
    def _covered(word: str, after_words: set[str], after_compact: str) -> bool:
        parts = _PART.findall(word)
        if all(part in _CONNECTORS or part in _LABELS or part in after_words for part in parts):
            return True
        # Códigos com outra pontuação: 742-2155 está em 7422155. Só com dígitos, para não casar palavras.
        compact = _compact(word)
        return any(char.isdigit() for char in compact) and len(compact) >= 3 and compact in after_compact
