"""Extração determinística de atributos do PDM a partir de descrições livres.

Na dúvida não extrai: juntar itens diferentes custa mais do que pedir revisão. O que não fica claro
vai para `unresolved`, e um repositório futuro, por exemplo com LLM, pode tratar só esses casos.
"""

import re
import unicodedata
from fractions import Fraction

from domain.contracts import ExtractedAttribute, ExtractionResult, PdmAttribute, PdmClass
from domain.pdm_validator import is_valid_value
from repositories.extraction.rule_based_v1_tables import (
    COLON_ONLY_KEYS,
    DIGIT_ONLY_KEYS,
    DN_TO_INCHES,
    KEY_ALIASES,
    VALUE_ALIASES,
)

_NOISE = re.compile(
    r"\s*(?:(?<=\s)-\s*|,\s*)?\b(?:COMPRA LOCAL|VER DESENHO|CONF(?:ORME)? (?:AMOSTRA|CATALOGO)|ITEM CRITICO"
    r"|P/ ?MANUTENCAO|APLICACAO GERAL|REF ANTIGA|REV [A-Z]\b)"
)
_SEGMENTS = re.compile(r"\s*;\s*|,(?!\d)\s*|\s+-\s+")
_CONNECTOR = re.compile(r"^(?:DE|COM|:)(?:\s+|$)|\s+(?:DE|COM|E)$")
_DASH_SIZE_VALUE = re.compile(r"^-(\d+)$")
_DASH_SIZE = re.compile(r"\s*\(-\d+\)")

_NUMBER = r"\d+(?:[.,]\d+)?"
_MM = re.compile(rf"^({_NUMBER})\s*MM$")
_MM2 = re.compile(rf"^({_NUMBER})\s*MM2?$")
_METERS = re.compile(rf"^({_NUMBER})\s*M$")
_BAR = re.compile(rf"^({_NUMBER})\s*BAR$")
_PSI = re.compile(rf"^({_NUMBER})\s*(?:PSI|LBS)$")
_AMPS = re.compile(rf"^({_NUMBER})\s*(?:A|AMP)$")
_WATTS = re.compile(rf"^({_NUMBER})\s*W$")
_RANGE = re.compile(rf"^0\s*-\s*({_NUMBER})\s*BAR$")
_INCH_MARK = r'\s*(?:POL|"|IN)'
_INCH_MIXED = re.compile(rf"^(\d+)[ .\-](\d+/\d+){_INCH_MARK}$")
_INCH_FRACTION = re.compile(rf"^(\d+/\d+){_INCH_MARK}$")
_INCH_WHOLE = re.compile(rf"^(\d+){_INCH_MARK}$")
_INCH_DECIMAL = re.compile(rf"^(\d+),(5|25|75){_INCH_MARK}$")
_DN = re.compile(r"^DN\s*(\d+)$")
_METRIC = re.compile(r"^M[\s\-]*(\d+(?:X[\d.,]+)?)$")
_BEARING = re.compile(r"^(\d{4,5})[\s\-]*(2RS|ZZ)?(?:[\s\-/]*(C3))?$")

_POOL_METRIC = re.compile(r"\bM[\s\-]?(\d+)(?:\s*X\s*(\d+(?:[.,]\d+)?))?(?:\s*X\s*(\d+(?:[.,]\d+)?))?\b")
_POOL_INCH_PAIR = re.compile(r"(\d+(?:\.\d+)?(?:/\d+)?)POLX(\d+(?:\.\d+)?(?:/\d+)?)POL")
_POOL_SEAL = re.compile(r"(?<![\w,.])(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)\b")
_POOL_INCH = re.compile(
    r"(?<![\d/.])(?:(?:\d+[ .\-]\d+/\d+|\d+/\d+|\d+(?:,(?:5|25|75))?)\s*(?:POL\b|\"|IN\b)|DN\s?\d+\b)"
)
_POOL_MEASURE = re.compile(rf"(?<![\w,.])({_NUMBER})\s*(MM2|MM|BAR|PSI|AMP|A|W)\b")
_POOL_RING = re.compile(r"(?<![\w,.])(\d+(?:[.,]\d+)?)X(\d+(?:[.,]\d+)?)\b")
_POOL_REFERENCE = re.compile(
    r"(?<![\w/.\-])(?:[A-Z]{1,3}\s)?[A-Z0-9]*\d[A-Z0-9/.\-]*(?:\s\d[A-Z0-9/.\-]*)*(?![\w/.\-])"
)
_POOL_BEARING = re.compile(r"\b\d{4,5}[A-Z]*(?:[\s\-/]*(?:2RS|ZZ))?(?:[\s\-/]*C3)?\b")

_WORD_ALIASES = {"FEM": "FEMEA", "AC": "ACO"}
_FRACTION_FROM_DECIMAL = {"5": "1/2", "25": "1/4", "75": "3/4"}
_PSI_PER_BAR = 14.5038
_REFERENCE_ATTRIBUTES = ("REFERENCIA FABRICANTE",)
_REFERENCE_LABELS = frozenset(
    {
        "REF",
        "REFERENCIA",
        "REF FABRICANTE",
        "REFERENCIA FABRICANTE",
        "PN",
        "P/N",
        "PART NUMBER",
        "COD",
        "COD FABRICANTE",
        "CODIGO",
    }
)
_REFERENCE_TAIL = re.compile(r"((?:\s+[A-Z][A-Z]{2,})+)$")
_METRIC_ATTRIBUTES = ("BITOLA", "PARA PARAFUSO", "ROSCA CORPO", "FURO")


def _clean_text(raw: str) -> str:
    decomposed = unicodedata.normalize("NFKD", raw)
    text = "".join(c for c in decomposed if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", text).strip()


def _decimal(number: str) -> str:
    """Decimal com vírgula e sem zeros à direita: 60,0 vira 60, conforme a regra geral 5."""
    value = number.replace(".", ",")
    if "," in value:
        value = value.rstrip("0").rstrip(",")
    return value


def _inches_from_sixteenths(size: int) -> str:
    """Bitola de mangueira: o tamanho -8 significa 8/16 de polegada, o padrão SAE que a própria base usa."""
    whole, fraction = divmod(Fraction(size, 16), 1)
    if not fraction:
        return f"{whole}POL"
    return f"{whole}.{fraction}POL" if whole else f"{fraction}POL"


def _measure_candidates(raw: str) -> list[tuple[str, str]]:
    """Formas padronizadas possíveis para uma medida, cada uma com a regra que a produziu."""
    candidates = []
    if match := _MM.match(raw):
        candidates.append((f"{_decimal(match[1])}MM", "measure.mm"))
    if match := _MM2.match(raw):
        candidates.append((f"{_decimal(match[1])}MM2", "measure.mm2"))
    if match := _METERS.match(raw):
        candidates.append((f"{_decimal(match[1])}M", "measure.meters"))
    if match := _BAR.match(raw):
        candidates.append((f"{_decimal(match[1])}BAR", "measure.bar"))
    if match := _PSI.match(raw):
        candidates.append((f"{round(float(match[1].replace(',', '.')) / _PSI_PER_BAR)}BAR", "measure.psi_to_bar"))
    if match := _AMPS.match(raw):
        candidates.append((f"{_decimal(match[1])}A", "measure.amps"))
    if match := _WATTS.match(raw):
        candidates.append((f"{_decimal(match[1])}W", "measure.watts"))
    if match := _RANGE.match(raw):
        candidates.append((f"0-{_decimal(match[1])}BAR", "measure.range"))
    if match := _INCH_MIXED.match(raw):
        candidates.append((f"{match[1]}.{match[2]}POL", "measure.inches"))
    if match := _INCH_FRACTION.match(raw):
        candidates.append((f"{match[1]}POL", "measure.inches"))
    if match := _INCH_WHOLE.match(raw):
        candidates.append((f"{match[1]}POL", "measure.inches"))
    if match := _INCH_DECIMAL.match(raw):
        candidates.append((f"{match[1]}.{_FRACTION_FROM_DECIMAL[match[2]]}POL", "measure.inches"))
    if (match := _DN.match(raw)) and match[1] in DN_TO_INCHES:
        candidates.append((f"{DN_TO_INCHES[match[1]]}POL", "measure.dn_to_inches"))
    if match := _METRIC.match(raw):
        candidates.append((f"M{match[1].replace('.', ',')}", "measure.metric_thread"))
    if match := _BEARING.match(raw):
        suffix = f"-{match[2]}" if match[2] else ""
        clearance = f"/{match[3]}" if match[3] else ""
        candidates.append((f"{match[1]}{suffix}{clearance}", "bearing.reference"))
    if match := _DASH_SIZE_VALUE.match(raw):
        candidates.append((_inches_from_sixteenths(int(match[1])), "measure.dash_size"))
    if raw.isdigit():
        candidates.append((raw, "measure.integer"))
    return candidates


def _contained_value(attribute: PdmAttribute, raw: str) -> str | None:
    """O único valor permitido contido no texto, quando há exatamente um."""
    if attribute.allowed_values is None:
        return None
    found = [v for v in attribute.allowed_values if re.search(rf"(?<![\w.\-]){re.escape(v)}(?![\w.\-])", raw)]
    longest = [v for v in found if not any(v != other and v in other for other in found)]
    return longest[0] if len(longest) == 1 else None


def _compact(value: str) -> str:
    return re.sub(r"[\s\-]", "", value)


def _loose_value(attribute: PdmAttribute, raw: str) -> tuple[str, str] | None:
    """Mesma grafia sem separadores (TC12 e TC-12), ou o único valor que contém todas as palavras do texto."""
    if attribute.allowed_values is None:
        return None
    if any(c.isdigit() for c in raw):
        same = [v for v in attribute.allowed_values if _compact(v) == _compact(raw)]
        if len(same) == 1:
            return same[0], "value.spelling"
    words = {_WORD_ALIASES.get(word, word) for word in raw.split()}
    if len(words) < 2:
        return None
    matches = [v for v in attribute.allowed_values if words <= set(v.split())]
    return (matches[0], "value.unique_words") if len(matches) == 1 else None


def fit_value(attribute: PdmAttribute, raw: str) -> tuple[str, str] | None:
    """Tenta colocar o texto no padrão do atributo. Só devolve valores que o validador aceita."""
    if attribute.allowed_values is not None and raw in attribute.allowed_values:
        return raw, "value.exact"
    for candidate in VALUE_ALIASES.get(raw, ()):
        if attribute.allowed_values is not None and candidate in attribute.allowed_values:
            return candidate, "value.alias"
    for candidate, rule in _measure_candidates(raw):
        if is_valid_value(attribute, candidate):
            return candidate, rule
    if attribute.allowed_values is None and raw and is_valid_value(attribute, raw):
        return raw, "value.as_written"
    contained = _contained_value(attribute, raw)
    if contained is not None:
        return contained, "value.contained"
    return _loose_value(attribute, raw)


class _Extraction:
    def __init__(self, pdm_class: PdmClass) -> None:
        self.pdm_class = pdm_class
        self.by_name = {a.name: a for a in pdm_class.attributes}
        self.found: dict[str, ExtractedAttribute] = {}

    def set(self, name: str, value: str, original: str, rule: str) -> None:
        self.found[name] = ExtractedAttribute(value, original, rule)

    def open_attributes(self) -> list[PdmAttribute]:
        return [a for a in self.pdm_class.attributes if a.name not in self.found]

    def fit_labeled(self, key: str, raw: str) -> bool:
        if not raw:
            return False
        if key == "DN" and raw.isdigit():
            raw = f"DN {raw}"
        names = (key, *KEY_ALIASES.get(key, ())) if key in self.by_name else KEY_ALIASES.get(key, ())
        for name in names:
            attribute = self.by_name.get(name)
            if attribute is None or name in self.found:
                continue
            fitted = fit_value(attribute, raw)
            if fitted:
                self.set(name, fitted[0], f"{key}: {raw}", fitted[1])
                return True
        return False


class RuleBasedV1ExtractionRepository:
    name = "rule_based_v1"

    def extract(
        self,
        pdm_class: PdmClass,
        description: str,
        *,
        manufacturer: str | None = None,
        manufacturer_reference: str | None = None,
    ) -> ExtractionResult:
        work = _Extraction(pdm_class)
        text = _NOISE.sub("", _DASH_SIZE.sub("", _clean_text(description)))
        self._use_structured_fields(work, manufacturer, manufacturer_reference)

        free: list[str] = []
        for segment in filter(None, _SEGMENTS.split(text)):
            free.extend(self._labeled_pieces(work, segment))

        pool = " , ".join(free)
        pool = self._scan_enums(work, pool)
        pool = self._scan_metric_thread(work, pool)
        pool = self._scan_inch_pair(work, pool)
        pool = self._scan_ring_notation(work, pool)
        pool = self._scan_seal_notation(work, pool)
        pool = self._scan_measures(work, pool)
        pool = self._scan_inches(work, pool)
        pool = self._scan_bearing_reference(work, pool)
        pool = self._scan_manufacturer_reference(work, pool)
        self._apply_documented_inferences(work)

        unresolved = tuple(part.strip() for part in pool.split(" , ") if part.strip())
        ordered = {a.name: work.found[a.name] for a in pdm_class.attributes if a.name in work.found}
        return ExtractionResult(ordered, unresolved)

    def _use_structured_fields(self, work: _Extraction, manufacturer: str | None, reference: str | None) -> None:
        if manufacturer and "FABRICANTE" in work.by_name:
            cleaned = _clean_text(manufacturer)
            fitted = fit_value(work.by_name["FABRICANTE"], cleaned)
            if fitted:
                work.set("FABRICANTE", fitted[0], manufacturer, "field.manufacturer")
        if reference and "REFERENCIA FABRICANTE" in work.by_name:
            cleaned = _NOISE.sub("", _clean_text(reference)).strip()
            if cleaned:
                work.set("REFERENCIA FABRICANTE", cleaned, reference, "field.manufacturer_reference")

    @staticmethod
    def _fit_longest_prefix(work: _Extraction, label: str, value: str) -> str | None:
        """Sem separador, o valor vai até o próximo rótulo: usa o maior começo válido e devolve o resto."""
        words = value.split()
        for size in range(len(words), 0, -1):
            if work.fit_labeled(label, " ".join(words[:size])):
                return " ".join(words[size:])
        return None

    @staticmethod
    def _split_reference_tail(label: str, value: str) -> tuple[str, str]:
        """Em `PN 6728493 HITACHI`, a referência termina antes do fabricante."""
        if label not in _REFERENCE_LABELS:
            return value, ""
        match = _REFERENCE_TAIL.search(value)
        if not match or not any(c.isdigit() for c in value[: match.start()]):
            return value, ""
        return value[: match.start()].strip(), match[1].strip()

    def _labeled_pieces(self, work: _Extraction, segment: str) -> list[str]:
        """Separa `RÓTULO: VALOR` e `RÓTULO VALOR`. O que não couber em um atributo volta como texto livre."""
        free = []
        if ":" in segment:
            key, _, value = segment.partition(":")
            key, value = key.strip(), _CONNECTOR.sub("", value.strip())
            value, tail = self._split_reference_tail(key, value)
            free = [tail] if tail else []
            if key and work.fit_labeled(key, value):
                return free
            return [value, *free] if value else free
        labels = sorted({*KEY_ALIASES, *work.by_name}, key=len, reverse=True)
        spans = []
        for label in labels:
            if label in COLON_ONLY_KEYS:
                continue
            guard = r"(?=\s*\d)" if label in DIGIT_ONLY_KEYS else ""
            for match in re.finditer(rf"(?<![\w./\-]){re.escape(label)}(?![\w./\-]){guard}", segment):
                if not any(start < match.end() and match.start() < end for start, end, _ in spans):
                    spans.append((match.start(), match.end(), label))
        spans.sort()
        position = 0
        for index, (start, end, label) in enumerate(spans):
            if start > position:
                free.append(segment[position:start].strip())
            stop = spans[index + 1][0] if index + 1 < len(spans) else len(segment)
            value = _CONNECTOR.sub("", segment[end:stop].strip()).strip()
            value = _CONNECTOR.sub("", value).strip()
            value, tail = self._split_reference_tail(label, value)
            if tail:
                free.append(tail)
            rest = self._fit_longest_prefix(work, label, value)
            if rest is None:
                free.append(f"{segment[start:end].strip()} {value}".strip())
            elif rest:
                free.append(rest)
            position = stop
        if position < len(segment):
            free.append(segment[position:].strip())
        return [piece for piece in free if piece]

    def _scan_enums(self, work: _Extraction, pool: str) -> str:
        """Busca valores permitidos no texto livre. Só aceita se servirem a um único atributo em aberto."""
        options: dict[str, set[str]] = {}
        canonical: dict[tuple[str, str], str] = {}
        for attribute in work.open_attributes():
            for value in attribute.allowed_values or ():
                # Valores curtos só com rótulo: "8" ou "C" aparecem em muitos outros contextos.
                if len(value) < 3 or value.isdigit():
                    continue
                # Roscas ficam para a leitura de notação compacta: M16 pode ser M16 X 60.
                if re.fullmatch(r"M\d.*", value):
                    continue
                options.setdefault(value, set()).add(attribute.name)
                canonical[(value, attribute.name)] = value
            for alias, targets in VALUE_ALIASES.items():
                for target in targets:
                    if attribute.allowed_values and target in attribute.allowed_values:
                        options.setdefault(alias, set()).add(attribute.name)
                        canonical[(alias, attribute.name)] = target
        for phrase in sorted(options, key=len, reverse=True):
            body = re.escape(phrase)
            if any(c.isdigit() for c in phrase):
                # Modelos e normas aparecem com ou sem separador: TC-12 e TC12.
                body = re.sub(r"\\[ \-]", r"[\\s\\-]?", body)
            pattern = rf"(?<![\w./\-]){body}(?![\w./\-])"
            match = re.search(pattern, pool)
            if not match:
                continue
            names = [name for name in options[phrase] if name not in work.found]
            if len(names) != 1:
                continue
            work.set(names[0], canonical[(phrase, names[0])], phrase, "value.unlabeled")
            pool = pool[: match.start()] + pool[match.end() :]
        return pool

    def _scan_metric_thread(self, work: _Extraction, pool: str) -> str:
        """Lê M12 e M12X50. Pela regra geral 2, M12X50 é BITOLA M12 e COMPRIMENTO 50MM; M12X1,5 é rosca fina."""
        for name in _METRIC_ATTRIBUTES:
            attribute = work.by_name.get(name)
            if attribute is None or name in work.found or not attribute.allowed_values:
                continue
            for match in _POOL_METRIC.finditer(pool):
                thread = f"M{match[1]}"
                pitch = f"{thread}X{match[2].replace('.', ',')}" if match[2] else None
                if pitch and pitch in attribute.allowed_values:
                    work.set(name, pitch, match[0], "measure.metric_thread")
                    length = work.by_name.get("COMPRIMENTO")
                    if match[3] and length and "COMPRIMENTO" not in work.found:
                        value = f"{_decimal(match[3])}MM"
                        if is_valid_value(length, value):
                            work.set("COMPRIMENTO", value, match[0], "measure.compact_notation")
                elif thread in attribute.allowed_values:
                    work.set(name, thread, match[0], "measure.metric_thread")
                    length = work.by_name.get("COMPRIMENTO")
                    if match[2] and length and "COMPRIMENTO" not in work.found:
                        value = f"{_decimal(match[2])}MM"
                        if is_valid_value(length, value):
                            work.set("COMPRIMENTO", value, match[0], "measure.compact_notation")
                else:
                    continue
                return pool[: match.start()] + pool[match.end() :]
        return pool

    def _scan_inch_pair(self, work: _Extraction, pool: str) -> str:
        """Notação compacta em polegadas: 5/16POLX3POL é BITOLA e COMPRIMENTO."""
        match = _POOL_INCH_PAIR.search(pool)
        if not match or not {"BITOLA", "COMPRIMENTO"} <= work.by_name.keys():
            return pool
        if "BITOLA" in work.found or "COMPRIMENTO" in work.found:
            return pool
        gauge, length = f"{match[1]}POL", f"{match[2]}POL"
        if is_valid_value(work.by_name["BITOLA"], gauge) and is_valid_value(work.by_name["COMPRIMENTO"], length):
            work.set("BITOLA", gauge, match[0], "measure.compact_notation")
            work.set("COMPRIMENTO", length, match[0], "measure.compact_notation")
            return pool[: match.start()] + pool[match.end() :]
        return pool

    def _scan_seal_notation(self, work: _Extraction, pool: str) -> str:
        """Retentor na notação comum eixo x alojamento x largura: 60X80X10."""
        names = ("DIAMETRO EIXO", "DIAMETRO ALOJAMENTO", "LARGURA")
        if not set(names) <= work.by_name.keys() or any(name in work.found for name in names):
            return pool
        match = _POOL_SEAL.search(pool)
        if not match:
            return pool
        for name, number in zip(names, match.groups(), strict=True):
            work.set(name, f"{_decimal(number)}MM", match[0], "measure.seal_notation")
        return pool[: match.start()] + pool[match.end() :]

    def _scan_ring_notation(self, work: _Extraction, pool: str) -> str:
        """O-ring na notação comum diâmetro interno x seção: 58X2.5."""
        if not {"DIAMETRO INTERNO", "SECAO"} <= work.by_name.keys():
            return pool
        if "DIAMETRO INTERNO" in work.found or "SECAO" in work.found:
            return pool
        match = _POOL_RING.search(pool)
        if not match:
            return pool
        work.set("DIAMETRO INTERNO", f"{_decimal(match[1])}MM", match[0], "measure.ring_notation")
        work.set("SECAO", f"{_decimal(match[2])}MM", match[0], "measure.ring_notation")
        return pool[: match.start()] + pool[match.end() :]

    def _scan_measures(self, work: _Extraction, pool: str) -> str:
        """Medida sem rótulo só vale se houver um único atributo em aberto com aquela unidade e um só valor."""
        by_unit: dict[str, list[re.Match]] = {}
        for match in _POOL_MEASURE.finditer(pool):
            by_unit.setdefault(match[2], []).append(match)
        spans = []
        for matches in by_unit.values():
            if len(matches) != 1:
                continue
            raw = matches[0][0]
            fits = [(a, fit_value(a, raw)) for a in work.open_attributes() if a.allowed_values is None]
            fits = [(a, fitted) for a, fitted in fits if fitted and fitted[1] != "value.as_written"]
            if len(fits) == 1:
                attribute, fitted = fits[0]
                work.set(attribute.name, fitted[0], raw, f"{fitted[1]}.unlabeled")
                spans.append(matches[0].span())
        for start, end in sorted(spans, reverse=True):
            pool = pool[:start] + pool[end:]
        return pool

    def _scan_inches(self, work: _Extraction, pool: str) -> str:
        """Polegadas sem rótulo seguem a ordem do PDM: em T REDUCAO 1POL 3/4POL, nominal e depois reduzido."""
        open_inches = [
            a for a in work.open_attributes() if a.allowed_values is None and a.format.startswith("polegada")
        ]
        matches = list(_POOL_INCH.finditer(pool))
        if not open_inches or not matches or len(matches) > len(open_inches):
            return pool
        for attribute, match in zip(open_inches, matches, strict=False):
            fitted = fit_value(attribute, match[0].strip())
            if fitted:
                work.set(attribute.name, fitted[0], match[0].strip(), f"{fitted[1]}.unlabeled")
        for match in reversed(matches):
            pool = pool[: match.start()] + pool[match.end() :]
        return pool

    def _scan_bearing_reference(self, work: _Extraction, pool: str) -> str:
        attribute = work.by_name.get("REFERENCIA")
        if attribute is None or "REFERENCIA" in work.found:
            return pool
        matches = list(_POOL_BEARING.finditer(pool))
        if len(matches) != 1:
            return pool
        fitted = fit_value(attribute, matches[0][0])
        if not fitted:
            return pool
        work.set("REFERENCIA", fitted[0], matches[0][0], f"{fitted[1]}.unlabeled")
        return pool[: matches[0].start()] + pool[matches[0].end() :]

    def _scan_manufacturer_reference(self, work: _Extraction, pool: str) -> str:
        """Código sem rótulo em classes de referência: só se sobrar exatamente um no texto."""
        if "REFERENCIA FABRICANTE" not in work.by_name or "REFERENCIA FABRICANTE" in work.found:
            return pool
        matches = list(_POOL_REFERENCE.finditer(pool))
        if len(matches) != 1:
            return pool
        code = matches[0][0].strip()
        work.set("REFERENCIA FABRICANTE", code, code, "reference.unlabeled")
        return pool[: matches[0].start()] + pool[matches[0].end() :]

    def _apply_documented_inferences(self, work: _Extraction) -> None:
        """Só o que o próprio PDM autoriza deduzir."""
        thread = work.by_name.get("ROSCA")
        bitola = work.found.get("BITOLA")
        if thread and thread.allowed_values and "ROSCA" not in work.found and bitola and bitola.value.startswith("M"):
            value = "METRICA FINA" if "X" in bitola.value else "METRICA GROSSA"
            if value in thread.allowed_values:
                work.set("ROSCA", value, bitola.value, "pdm.thread_from_gauge")
        reference = work.found.get("REFERENCIA")
        if reference and "VEDACAO" in work.by_name and work.by_name["VEDACAO"].allowed_values:
            if "ABERTO" in work.by_name["VEDACAO"].allowed_values:
                self._infer_bearing(work, reference.value)

    def _infer_bearing(self, work: _Extraction, reference: str) -> None:
        """O FORMATO da REFERENCIA do PDM020 define o que cada sufixo significa."""
        if "VEDACAO" not in work.found:
            if "-2RS" in reference:
                seal = "BORRACHA AMBOS LADOS"
            elif "-ZZ" in reference:
                seal = "METALICA AMBOS LADOS"
            else:
                seal = "ABERTO"
            work.set("VEDACAO", seal, reference, "pdm.bearing_suffix")
        if "FOLGA" not in work.found:
            work.set("FOLGA", "C3" if "/C3" in reference else "NORMAL", reference, "pdm.bearing_suffix")
