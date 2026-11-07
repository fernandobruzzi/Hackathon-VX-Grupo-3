"""aliases_v1 com precedência do nome que abre a descrição.

O começo da descrição longa, até o primeiro separador (vírgula, ponto e vírgula, dois-pontos,
parênteses, " - ") ou a primeira palavra com dígito, é o nome do item. A barra não separa: faz
parte de nomes como `FILTRO SEPARADOR AR/OLEO` e `C/TERMINAIS`. Um nome do PDM
encontrado ali decide a classe, mesmo que outro nome de classe apareça depois como atributo
(`VALVULA ESFERA ... EXTREMIDADE FLANGE RF`, `VALVULA RETENCAO ... PISTAO`).

No trecho inicial, e só nele:

- uma abreviação vira a palavra do PDM quando é prefixo de uma única palavra dos nomes daquela
  família: `PARAF` só pode ser `PARAFUSO`; depois de `VALVULA`, `RET` só pode ser `RETENCAO`
  (`RETENTOR` não é válvula). Prefixo com mais de uma leitura fica como está;
- a flexão feminina de uma palavra da família vira a masculina (`CAB SEXTAVADA` → `SEXTAVADO`);
- os sinônimos técnicos de `SYNONYMS` valem como as palavras do PDM;
- um nome do PDM vale quando todas as suas palavras estão no trecho, começando pela primeira,
  e o mais longo vence (`PARAFUSO SEXTAVADO INTERNO` antes de `PARAFUSO SEXTAVADO`);
- toda palavra da família presente no trecho precisa estar no nome escolhido: `FILTRO SEPARADOR
  AR` não é `FILTRO AR`, porque SEPARADOR distingue outro item da família.

Nada disso cria classe por suposição: dois nomes de classes diferentes com o mesmo tamanho, nome de
uma palavra que exige o grupo ou um trecho sem nome completo voltam para as regras do aliases_v1.
Os aliases não inventam atributos: a extração continua lendo o texto original.
"""

import re

from domain.contracts import (
    ClassificationEvidence,
    ClassificationInput,
    ClassificationResult,
    ClassificationStatus,
    PdmCatalog,
)
from repositories.classification.aliases_v1 import AliasesV1ClassificationRepository, expand
from repositories.classification.rule_based_v1 import _plain, _tokens

# Mesma peça com outro nome. HEXAGONAL e SEXTAVADO descrevem a mesma cabeça de seis faces; ALLEN é
# o sextavado interno; ORING é O-RING sem o hífen.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "ALLEN": ("SEXTAVADO", "INTERNO"),
    "HEXAGONAL": ("SEXTAVADO",),
    "ORING": ("O", "RING"),
}

# Sequências que equivalem a palavras do PDM. A mangueira com terminais é a montada: o próprio PDM
# separa MANGUEIRA HIDRAULICA (sem acessórios, 4009.21.10) da MONTADA (com terminais, 4009.22.10).
# SEM TERMINAIS não aparece aqui e não vira MONTADA.
PHRASES: dict[tuple[str, ...], tuple[str, ...]] = {
    ("C", "TERMINAIS"): ("MONTADA",),
    ("C", "TERMINAL"): ("MONTADA",),
    ("COM", "TERMINAIS"): ("MONTADA",),
    ("COM", "TERMINAL"): ("MONTADA",),
}

# Palavras da língua que nunca são abreviação: COM não é COMBUSTIVEL, PARA não é PARAFUSO.
_FUNCTION_WORDS = frozenset(
    {"COM", "EM", "NA", "NAS", "NO", "NOS", "OU", "PARA", "PELA", "PELO", "POR", "SEM", "TIPO", "USO"}
)
_HEAD_END = re.compile(r"[,;:()\[\]]| - ")
_MIN_HEAD_PREFIX = 4
_MIN_PREFIX = 3


class AliasesV2ClassificationRepository(AliasesV1ClassificationRepository):
    name = "aliases_v2"
    revision = "1"

    def __init__(self, catalog: PdmCatalog):
        super().__init__(catalog)
        self.heads = frozenset(words[0] for words in self.names)
        self.family_words: dict[str, frozenset[str]] = {
            head: frozenset(word for words in self.names if words[0] == head for word in words) for head in self.heads
        }

    def head_words(self, description: str | None) -> tuple[str, ...]:
        """Palavras do nome que abre a descrição, já na grafia do PDM (primeira leitura possível)."""
        readings = self._readings(description)
        return readings[0] if readings else ()

    def _readings(self, description: str | None) -> list[tuple[str, ...]]:
        """Uma leitura por família possível da primeira palavra: MANG pode ser MANGOTE ou MANGUEIRA."""
        text = _HEAD_END.split(_plain(description), maxsplit=1)[0]
        words: list[str] = []
        for word in _tokens(text):
            if any(char.isdigit() for char in word):
                break
            words.extend(SYNONYMS.get(word, (word,)))
        words = list(expand(tuple(_phrases(words)))[0])
        if not words:
            return []
        first = words[0]
        heads = [first] if first in self.heads else _completions(first, self.heads, _MIN_HEAD_PREFIX) or [first]
        readings = []
        for head in heads:
            family = self.family_words.get(head)
            rest = words[1:] if family is None else [_family_word(word, family) for word in words[1:]]
            readings.append((head, *rest))
        return readings

    def head_match(self, description: str | None) -> tuple[str, str] | None:
        """Classe e nome do PDM decididos pelo começo da descrição, ou None se não houver um só."""
        # Entre famílias possíveis, vale a leitura que explica mais palavras com um nome do PDM;
        # empate é dúvida.
        readings = self._readings(description)
        found = {match for words in readings if (match := self._match(words))}
        if not found:
            return None
        longest = max(len(_tokens(name)) for _, name in found)
        best = {match for match in found if len(_tokens(match[1])) == longest}
        # Prefixo ambíguo (MANG) só se resolve com outra palavra do nome: MANG 4POL fica em dúvida.
        if len(readings) > 1 and longest == 1:
            return None
        return next(iter(best)) if len(best) == 1 else None

    def _match(self, words: tuple[str, ...]) -> tuple[str, str] | None:
        if not words or words[0] not in self.heads:
            return None
        present = set(words)
        matches = [name for name in self.names if name[0] == words[0] and present.issuperset(name)]
        if not matches:
            return None
        longest = max(len(name) for name in matches)
        found = {entry for name in matches if len(name) == longest for entry in self.names[name]}
        if len(found) != 1:
            return None
        class_id, name = next(iter(found))
        # Palavra que distingue um item irmão e sobra no trecho deixa o item em dúvida.
        chosen = set(_tokens(name))
        if any(word in self.family_words[words[0]] and word not in chosen for word in words):
            return None
        # Outro nome do PDM inteiro no trecho, com palavras que não são do nome escolhido, também:
        # MANTO EIXO pode ser manto ou eixo.
        for length in self.lengths:
            for start in range(len(words) - length + 1):
                other = words[start : start + length]
                if other in self.names and not chosen.issuperset(other):
                    return None
        # Nome de uma palavra presente em várias famílias (BUCHA, TAMPA) ou curto (TE) continua
        # exigindo o grupo, como no aliases_v1.
        if longest == 1 and (len(self.families[words[0]]) > 1 or len(words[0]) < 4):
            return None
        return class_id, name

    def classify(self, item: ClassificationInput) -> ClassificationResult:
        match = self.head_match(item.description)
        base = super().classify(item)
        if match is None:
            return base
        class_id, name = match
        # Outro campo que nomeia outra classe continua sendo ambiguidade. A descrição curta tem a
        # forma da longa (muitas vezes truncada), então só o seu começo conta; o anexo é texto livre.
        short = self.head_match(item.short_description)
        if (short is not None and short[0] != class_id) or any(
            e.source_field == "attachment_text" and e.class_id != class_id and "/name." in e.rule for e in base.evidence
        ):
            return base
        pdm_class = self.catalog.classes[class_id]
        evidence = [ClassificationEvidence(class_id, "description", name, f"{self.name}/head.name")]
        group = " ".join(_tokens(item.merchandise_group))
        if group:
            group_rule = "group.supports" if group == pdm_class.group else "group.mismatch"
            evidence.append(
                ClassificationEvidence(class_id, "merchandise_group", pdm_class.group, f"{self.name}/{group_rule}")
            )
        return ClassificationResult(
            original=item,
            status=ClassificationStatus.CLASSIFIED,
            pdm_class_id=class_id,
            candidate_class_ids=(class_id,),
            evidence=tuple(sorted(evidence, key=lambda e: (e.source_field, e.class_id, e.matched_name, e.rule))),
            rule=f"{self.name}/head.name",
            pdm_version=self.catalog.version,
            pdm_source_sha256=self.catalog.source_sha256,
        )


def _phrases(words: list[str]) -> list[str]:
    result: list[str] = []
    position = 0
    while position < len(words):
        phrase = next((p for p in PHRASES if tuple(words[position : position + len(p)]) == p), None)
        if phrase is None:
            result.append(words[position])
            position += 1
        else:
            result.extend(PHRASES[phrase])
            position += len(phrase)
    return result


def _completions(word: str, vocabulary: frozenset[str], minimum: int) -> list[str]:
    if len(word) < minimum or word in _FUNCTION_WORDS:
        return []
    return sorted(candidate for candidate in vocabulary if candidate.startswith(word))


def _unique_completion(word: str, vocabulary: frozenset[str], minimum: int) -> str:
    if word in vocabulary:
        return word
    completions = _completions(word, vocabulary, minimum)
    return completions[0] if len(completions) == 1 else word


def _family_word(word: str, family: frozenset[str]) -> str:
    if word in family:
        return word
    if word.endswith("A") and word[:-1] + "O" in family:
        return word[:-1] + "O"
    return _unique_completion(word, family, _MIN_PREFIX)
