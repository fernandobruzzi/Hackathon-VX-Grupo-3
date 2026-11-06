"""Extrai somente rótulos técnicos explícitos, sem deduzir medidas ou interpretar equivalências."""

import re
from decimal import Decimal

from domain.contracts import EnrichmentClaim, PdmClass

_NUMBER = r"([0-9]{1,7}(?:[.,][0-9]{1,6})?)"
_DIMENSIONS = {
    "DIAMETRO INTERNO": (
        rf"Bore diameter\s*[:|]?\s*{_NUMBER}\s*mm",
        rf"\bd\s+{_NUMBER}\s*mm\s+Bore diameter",
        rf"Inner \(d\) MM\s+{_NUMBER}",
    ),
    "DIAMETRO EXTERNO": (
        rf"Outside diameter\s*[:|]?\s*{_NUMBER}\s*mm",
        rf"\bD\s+{_NUMBER}\s*mm\s+Outside diameter",
        rf"Outer \(D\) MM\s+{_NUMBER}",
        rf"Largest Outside Diameter\s+[^;]{{0,24}}?/\s*{_NUMBER}\s*mm",
    ),
    "LARGURA": (rf"\bWidth\s*[:|]?\s*{_NUMBER}\s*mm", rf"\bB\s+{_NUMBER}\s*mm\s+Width", rf"Width \(B\) MM\s+{_NUMBER}"),
    "ALTURA": (rf"\bHeight\s*[:|]?\s*{_NUMBER}\s*mm", rf"\bHeight\s+[^;]{{0,24}}?/\s*{_NUMBER}\s*mm"),
}


def exact_reference(reference: str, text: str) -> bool:
    return re.search(r"(?<![A-Z0-9/_-])" + re.escape(reference) + r"(?![A-Z0-9/_-])", text.upper()) is not None


class CatalogLabelsV1:
    name = "catalog_labels_v1"

    def extract(self, pdm_class: PdmClass, manufacturer: str, reference: str, pages: tuple[str, ...]):
        if not pages:
            return ()
        anchor = pages[0].split("\n", 1)[0] if pages[0].startswith("HTML_PRODUCT_TITLE: ") else pages[0][:500]
        if not exact_reference(reference, anchor):
            return ()
        allowed = {attribute.name: attribute for attribute in pdm_class.attributes}
        claims = []
        for page_number, page in enumerate(pages, start=1):
            # A tabela do próprio item pode vir depois de recomendações. Só ler a sua seção técnica.
            specification = re.search(r"\b(?:Technical specification|Specification)s?\b", page, re.IGNORECASE)
            technical = page[specification.end() :] if specification else page
            technical = re.split(
                r"Related Parts|Related Products|Supporting products|Cross.Reference",
                technical,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            for attribute, patterns in _DIMENSIONS.items():
                if attribute not in allowed:
                    continue
                for pattern in patterns:
                    for match in re.finditer(pattern, technical, re.IGNORECASE):
                        value = Decimal(match[1].replace(",", "."))
                        if value > 0:
                            canonical = format(value.normalize(), "f").replace(".", ",") + "MM"
                            claims.append(EnrichmentClaim(attribute, canonical, match[0], page_number))
            if page_number == 1:
                reference_attribute = "REFERENCIA FABRICANTE" if "REFERENCIA FABRICANTE" in allowed else "REFERENCIA"
                if reference_attribute in allowed:
                    claims.append(EnrichmentClaim(reference_attribute, reference, reference, page_number))
                brand = re.search(r"(?<![A-Z0-9])" + re.escape(manufacturer) + r"(?![A-Z0-9])", page, re.IGNORECASE)
                if brand and "FABRICANTE" in allowed:
                    claims.append(EnrichmentClaim("FABRICANTE", manufacturer, brand[0], page_number))
                for match in re.finditer(
                    r"(?:Radial Internal Clearance|Radial Internal Play|Internal Clearance)\s*[:|]?\s*(C3|NORMAL)\b",
                    technical,
                    re.IGNORECASE,
                ):
                    if "FOLGA" in allowed:
                        claims.append(EnrichmentClaim("FOLGA", match[1].upper(), match[0], page_number))
        return tuple(dict.fromkeys(claims))
