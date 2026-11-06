"""Identidades conferidas nos 15 registros reais; URLs são escolhidas aqui, nunca pelo solicitante."""

from dataclasses import dataclass

from enrichment.trusted_sources import SourceSpec


@dataclass(frozen=True)
class RealProduct:
    manufacturer: str
    reference: str
    pdm_class_id: str
    sources: tuple[SourceSpec, ...]


def source(id: str, url: str, title: str, host: str, kind: str = "MANUFACTURER") -> SourceSpec:
    return SourceSpec(id, url, title, (host,), kind)


SKF6205 = source(
    "skf-6205", "https://www.skf.com/fr/productinfo/productid-6205-2RSH%2FC3", "SKF 6205-2RSH/C3", "www.skf.com"
)
SKF6310 = source(
    "skf-6310",
    "https://www.emarketplace.in.skf.com/deep-groove-ball-bearing/6310-2z-c3",
    "SKF 6310-2Z/C3",
    "www.emarketplace.in.skf.com",
)
NSK6205 = source(
    "nsk-6205",
    "https://www.nsk.com/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/single-row-deep-groove-ball-bearings/6205dduc3-apn.html",
    "NSK 6205DDUC3",
    "www.nsk.com",
)
FAG6205 = source(
    "fag-6205",
    "https://www.abf.store/s/en/bearings/6205-C-2HRS-C3-FAG/478040",
    "FAG 6205-C-2HRS-C3 — ABF",
    "www.abf.store",
    "DISTRIBUTOR",
)
FAG6310 = source(
    "fag-6310",
    "https://www.abf.store/s/en/bearings/6310-C-2Z-C3-FAG/1052402",
    "FAG 6310-C-2Z-C3 — ABF",
    "www.abf.store",
    "DISTRIBUTOR",
)
LF9009 = source(
    "fleetguard-lf9009", "https://www.fleetguard.com/product/LF9009", "Fleetguard LF9009", "www.fleetguard.com"
)
LF9009_PDF = source(
    "fleetguard-lf9009-pdf",
    "https://www.fleetguard.com/DefaultStore/apex/FIL_FGP_prodSpecPdfPg?cclcl=en_US&prodSku=LF9009",
    "Fleetguard LF9009 — ficha técnica",
    "www.fleetguard.com",
)
LF3970 = source(
    "fleetguard-lf3970", "https://www.fleetguard.com/product/LF3970", "Fleetguard LF3970", "www.fleetguard.com"
)
LF691A = source(
    "fleetguard-lf691a", "https://www.fleetguard.com/product/LF691A", "Fleetguard LF691A", "www.fleetguard.com"
)
CAT1808 = source("cat-1r1808", "https://parts.cat.com/en/catcorp/product/1R-1808", "Cat 1R-1808", "parts.cat.com")
P551808 = source(
    "donaldson-p551808",
    "https://shop.donaldson.com/store/en-us/product/P551808/80",
    "Donaldson P551808",
    "shop.donaldson.com",
)
DBL7300 = source(
    "donaldson-dbl7300",
    "https://shop.donaldson.com/store/en-us/product/DBL7300/11889",
    "Donaldson DBL7300",
    "shop.donaldson.com",
)
B40142 = source(
    "baldwin-b40142",
    "https://www.baldwinfilters.com/content/dam/Parker-com/Literature/EMAM/EMAM_Baldwin_ProductPicks_B40142.pdf",
    "Baldwin B40142 — ficha do fabricante",
    "www.baldwinfilters.com",
)

REAL_PRODUCTS = {
    "11315577": RealProduct("CATERPILLAR", "1R-1808", "PDM100", (CAT1808,)),
    "12456213": RealProduct("FLEETGUARD", "LF3970", "PDM100", (LF3970,)),
    "14840397": RealProduct("FAG", "6310-C-2Z-C3", "PDM020", (FAG6310,)),
    "16031971": RealProduct("FLEETGUARD", "LF9009", "PDM100", (LF9009, LF9009_PDF)),
    # Fontes das variantes /EM, /5K ou EC não comprovam a referência exata da entrada.
    "16303905": RealProduct("NTN", "6310ZZC3", "PDM020", ()),
    "18308575": RealProduct("DONALDSON", "DBL7300", "PDM100", (DBL7300,)),
    "20388699": RealProduct("DONALDSON", "P551808", "PDM100", (P551808,)),
    "20866024": RealProduct("SKF", "6205-2RSH/C3", "PDM020", (SKF6205,)),
    "21927396": RealProduct("BALDWIN", "B40142", "PDM100", (B40142,)),
    "23476944": RealProduct("FLEETGUARD", "LF691A", "PDM100", (LF691A,)),
    "27026717": RealProduct("FAG", "6205-C-2HRS-C3", "PDM020", (FAG6205,)),
    "27841570": RealProduct("FLEETGUARD", "LF9009", "PDM100", (LF9009, LF9009_PDF)),
    "28490077": RealProduct("NSK", "6205DDUC3", "PDM020", (NSK6205,)),
    "29364361": RealProduct("SKF", "6310-2Z/C3", "PDM020", (SKF6310,)),
    "29458054": RealProduct("CATERPILLAR", "1R-1808", "PDM100", (CAT1808,)),
}
