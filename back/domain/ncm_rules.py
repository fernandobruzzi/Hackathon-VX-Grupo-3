"""Coerência segundo o PDM; apenas avalia, nunca aprova ou grava alterações."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from domain.contracts import PdmCatalog, PdmClass
from domain.ncm_snapshot import NcmSnapshot, check_snapshot_ncm
from repositories.normalization import get_normalization_repository

RULES_VERSION = "pdm-ncm-v2"
# Política do batch para propor, mais restrita que a coerência: ver `ncm_proposal_blockers`.
PROPOSAL_POLICY_VERSION = "ncm-proposal-v1"
REFERENCE_SOURCE = "03_padrao_cadastro_PDM.xlsx#NCM_REFERENCIA"

# Texto condicional novo exige conferir a implementação, sem interpretar texto livre.
_CONDITIONAL_HASHES = {
    "PDM012": "4466a755617b654fc3b9d49091ef9a14036d8ec24899b7c950c4d9c24580fdab",
    "PDM014": "f51dc259135faf12aa368c221228791caae69aaf7feba1399e55f41db21c2bc2",
    "PDM030": "f7f5a292a649c0e66d9a406ec199d353a714de83c987ed3a69a1de8cae121213",
    "PDM034": "b8f35835f6a358f9deaf1ba5b820d92241093ceadbbcda3b70beb0c8507f77fa",
    "PDM050": "f53cd2f041750208cf19da75a76b0cbdb6cf168be4d485969b078e2d3bb2df34",
    "PDM051": "9849597f1b3cfed7bacd943a0d5b2daca7459c535b1b67c9d939ef8cb8628da0",
    "PDM070": "f35f8fb790fdb2df33c322b057d6b2dca94406a19aa579ac70fbade8e606f5af",
    "PDM071": "e7a39a441f8cda59dbbb47aada8d4155646d948c141a63f77c3af2d13a244268",
    "PDM081": "f49e0bb278f91e787968ded5a6779f46778d6d1660d71e1fc489e65fff42e4fb",
    "PDM100": "56410251522e6b335c5005a27b8400f68414a71e424ac5beb41fedc6aec4f0af",
    "PDM110": "14c8666eb941a3d2ce824e50b0f347ed904ed023c3eced6d273d74d2c6fff932",
}


@dataclass(frozen=True)
class NcmConsistencyResult:
    input_ncm: str | None
    normalized_ncm: str | None
    syntax_valid: bool
    exists_in_snapshot: bool | None
    valid_in_snapshot: bool | None
    technical_consistency: str
    suggested_ncm_codes: tuple[str, ...]
    missing_attributes: tuple[str, ...]
    rule_id: str
    requires_fiscal_review: bool
    fiscal_approval_status: str
    pdm_version: str
    pdm_source_sha256: str
    reference_source: str
    rules_version: str
    evaluation_hash: str
    pending_checks: tuple[str, ...]
    ncm_version: str | None
    ncm_source_sha256: str | None
    ncm_snapshot_date: str | None
    ncm_source_kind: str | None


def check_ncm_consistency(
    catalog: PdmCatalog,
    pdm_class_id: str,
    attributes: dict[str, str | None],
    ncm: str | None,
    *,
    item_name: str | None = None,
    ncm_version: str | None = None,
    snapshot: NcmSnapshot | None = None,
) -> NcmConsistencyResult:
    """O consumidor deve reavaliar dados alterados e vincular a aprovação ao changeset.

    Sem snapshot, existência/vigência ficam desconhecidas. A origem não verificada
    mantém revisão fiscal, mesmo quando o conteúdo confere com o PDM.
    """
    if ncm_version is not None and (snapshot is None or ncm_version != snapshot.version):
        raise ValueError(f"Snapshot oficial NCM indisponível: {ncm_version}")
    snapshot_check = check_snapshot_ncm(snapshot, ncm) if snapshot is not None else None
    reference = {
        "ncm_version": snapshot.version if snapshot else None,
        "ncm_source_sha256": snapshot.source_sha256 if snapshot else None,
        "ncm_snapshot_date": snapshot.snapshot_date.isoformat() if snapshot else None,
        "ncm_source_kind": snapshot.source_kind.value if snapshot else None,
    }
    normalizer = get_normalization_repository()
    normalized = normalizer.normalize_ncm(ncm).value
    if normalized is not None and not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", normalized):
        normalized = None
    payload = {
        "class": pdm_class_id,
        "attributes": attributes,
        "item_name": item_name,
        "ncm": ncm,
        "pdm_version": catalog.version,
        "pdm_sha256": catalog.source_sha256,
        "rules": RULES_VERSION,
        "normalization": normalizer.name,
        "ncm_reference": reference,
    }
    evaluation_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    pending = list(snapshot_check.reasons) if snapshot_check else ["OFFICIAL_SNAPSHOT_UNAVAILABLE"]
    pdm_class = catalog.classes.get(pdm_class_id)
    codes, missing, resolved = (), (), False
    if pdm_class is None:
        consistency = "OUT_OF_SCOPE"
    else:
        codes, missing, resolved = _select_codes(pdm_class, attributes, item_name)
        if not resolved or normalized is None:
            consistency = "UNDETERMINED"
        else:
            consistency = "CONSISTENT" if normalized in codes else "INCONSISTENT"
        if not resolved:
            pending.append("PDM_CONDITION_UNRESOLVED")
    requires_review = (
        consistency != "CONSISTENT"
        or normalized != ncm
        or bool(snapshot_check and snapshot_check.requires_fiscal_review)
    )
    return NcmConsistencyResult(
        input_ncm=ncm,
        normalized_ncm=normalized,
        syntax_valid=normalized is not None,
        exists_in_snapshot=snapshot_check.exists_in_snapshot if snapshot_check else None,
        valid_in_snapshot=snapshot_check.valid_in_snapshot if snapshot_check else None,
        technical_consistency=consistency,
        suggested_ncm_codes=codes,
        missing_attributes=missing,
        rule_id=f"{pdm_class_id}_NCM",
        requires_fiscal_review=requires_review,
        fiscal_approval_status="PENDING" if requires_review else "NOT_REQUIRED",
        pdm_version=catalog.version,
        pdm_source_sha256=catalog.source_sha256,
        reference_source=REFERENCE_SOURCE,
        rules_version=RULES_VERSION,
        evaluation_hash=evaluation_hash,
        pending_checks=tuple(pending),
        **reference,
    )


# Anel ou vedação de sobressalente pode ser junta (8484), artefato de borracha (4016) ou parte de
# máquina: o equipamento de aplicação não decide sem material, construção e desenho.
_SEAL_HEADS = frozenset({"ANEL", "VEDACAO"})
# Atributos que provam a matéria do item. Classe de resistência de fixador (ISO 898-1, SAE J429,
# ISO 3506: 8.8, SAE GRAU 5, A2-70...) só é definida para aço carbono, liga ou inoxidável.
_MATTER_EVIDENCE = frozenset({"MATERIAL", "CLASSE RESISTENCIA"})


def ncm_proposal_blockers(cls: PdmClass, attrs: Mapping[str, str | None], item: str | None) -> tuple[str, ...]:
    """Motivos para o batch não propor um NCM que a coerência do PDM aceitaria.

    A coerência segue o PDM ao pé da letra e continua igual para chat e aprovação. Propor um código
    exige mais: a posição do NCM depende da matéria (cap. 73 é ferro/aço; 4016, borracha
    vulcanizada), então o código único da classe só vale com a matéria provada por um atributo
    admitido. Anéis e vedações de sobressalente vão para revisão manual.
    """
    reasons = []
    evidence = [a for a in cls.attributes if a.name in _MATTER_EVIDENCE]
    if evidence and not any(
        attrs.get(a.name) and (not a.allowed_values or attrs[a.name] in a.allowed_values) for a in evidence
    ):
        reasons.append("NCM_MATTER_UNPROVEN")
    if cls.id == "PDM110" and item and item.split()[0] in _SEAL_HEADS:
        reasons.append("NCM_SEAL_FUNCTION_UNRESOLVED")
    return tuple(reasons)


def requires_snapshot_fiscal_review(assessment: Mapping[str, object]) -> bool:
    """Pendência da referência, separada de uma possível mudança de grafia do NCM.

    Consumidores conferem mudanças reais no changeset com seus guards existentes.
    A avaliação global continua indicando a revisão de uma normalização proposta.
    """
    return assessment["ncm_version"] is not None and (
        assessment["exists_in_snapshot"] is not True
        or assessment["valid_in_snapshot"] is not True
        or assessment["ncm_source_kind"] != "OFFICIAL_DOWNLOAD"
    )


def _select_codes(cls: PdmClass, attrs: dict[str, str | None], item: str | None):
    candidates = tuple(dict.fromkeys(code for ref in cls.ncm_references for code in ref.codes))
    if len(candidates) == 1:
        return candidates, (), True
    signature = hashlib.sha256(cls.ncm_references[0].rule.encode()).hexdigest()
    if _CONDITIONAL_HASHES.get(cls.id) != signature:
        return candidates, (), False
    missing = []

    def value(name):
        raw = attrs.get(name)
        definition = next((a for a in cls.attributes if a.name == name), None)
        if not raw or (definition and definition.allowed_values and raw not in definition.allowed_values):
            missing.append(name)
            return None
        return raw

    def item_name():
        if item not in cls.item_names:
            missing.append("SUBSTANTIVO")
            return None
        return item

    selected = None
    match cls.id:
        case "PDM012":
            material = value("MATERIAL")
            if material == "PVC":
                selected = "3917.39.00"
            elif material in ("EPDM", "NBR", "SBR"):
                selected = {"LONAS TEXTEIS": "4009.31.00", "ESPIRAL ACO + LONAS TEXTEIS": "4009.41.00"}.get(
                    value("REFORCO")
                )
        case "PDM014":
            selected = {
                "BORRACHA COM ESPIRAL ACO": "4009.41.00",
                "PVC COM ESPIRAL ACO": "3917.39.00",
                "PVC COM ESPIRAL PVC RIGIDO": "3917.39.00",
            }.get(value("MATERIAL"))
        case "PDM030":
            raw = value("COMPRIMENTO EXTERNO")
            length = _length_mm(raw)
            if length is not None:
                selected = (
                    "4010.39.00"
                    if length <= 600 or length > 2400
                    else ("4010.32.00" if length <= 1800 else "4010.34.00")
                )
            elif raw:
                missing.append("COMPRIMENTO EXTERNO")
        case "PDM034":
            selected = {"PTFE EXPANDIDO": "3926.90.90", "EPDM": "4016.93.00", "NBR": "4016.93.00"}.get(
                value("MATERIAL")
            )
        case "PDM050":
            material, name = value("MATERIAL"), item_name()
            if material and name:
                if material == "FERRO MALEAVEL GALVANIZADO":
                    selected = "7307.19.90"
                else:
                    stainless = material in ("ACO INOX A403 WP316", "ACO INOX FORJADO A182 F316")
                    if name == "FLANGE":
                        selected = "7307.21.00" if stainless else "7307.91.00"
                    else:
                        connection = value("CONEXAO")
                        if connection == "SOLDA TOPO BW":
                            selected = "7307.23.00" if stainless else "7307.93.00"
                        elif connection in ("ROSCA BSP", "ROSCA NPT") and name in (
                            "COTOVELO 45 GRAUS",
                            "COTOVELO 90 GRAUS",
                            "LUVA",
                            "LUVA REDUCAO",
                        ):
                            selected = "7307.22.00" if stainless else "7307.92.00"
                        elif connection:
                            selected = "7307.29.00" if stainless else "7307.99.00"
        case "PDM051":
            material, seam = value("MATERIAL"), value("COSTURA")
            if material == "ACO CARBONO API 5L GR B":
                selected = "7304.19.00" if seam == "SEM COSTURA" else None
            elif material == "ACO GALVANIZADO NBR 5580":
                selected = "7306.30.00" if seam == "COM COSTURA" else None
            elif material == "ACO INOX A312 TP316L":
                selected = "7306.40.00" if seam == "COM COSTURA" else None
            elif material == "ACO CARBONO A106 GR B" and seam == "SEM COSTURA":
                diameter = value("DIAMETRO NOMINAL")
                inches = _inches(diameter)
                if inches is not None and inches <= 8:
                    selected = "7304.39.10"
                elif inches in (10, 12):
                    selected = "7304.39.90"
                elif diameter:
                    missing.append("DIAMETRO NOMINAL")
        case "PDM070":
            selected = {
                "VAQUETA": "4203.29.00",
                "RASPA": "4203.29.00",
                "LATEX": "4015.19.00",
                "NITRILICA": "4015.19.00",
                "MALHA REVESTIDA PU": "6116.10.00",
            }.get(value("MATERIAL"))
        case "PDM071":
            selected = {"ACO": "6403.40.00", "COMPOSITE": "6403.99.90"}.get(value("BIQUEIRA"))
        case "PDM081":
            selected = {"CORTE": "6804.22.11", "DESBASTE": "6804.22.11", "FLAP": "6805.10.00"}.get(value("TIPO"))
        case "PDM100":
            selected = {
                "FILTRO AR": "8421.31.00",
                "FILTRO COMBUSTIVEL": "8421.23.00",
                "FILTRO HIDRAULICO": "8421.29.90",
                "FILTRO OLEO LUBRIFICANTE": "8421.23.00",
                "FILTRO SEPARADOR AR/OLEO": "8421.39.90",
            }.get(item_name())
        case "PDM110":
            name = item_name()
            exception = next((r for r in cls.ncm_references if r.rule == f"exceção: substantivo {name}"), None)
            if name and exception and len(exception.codes) == 1:
                selected = exception.codes[0]
            elif name:
                application = value("APLICACAO")
                reference = next((r for r in cls.ncm_references if r.rule == f"sobressalente de {application}"), None)
                if reference and len(reference.codes) == 1:
                    selected = reference.codes[0]
    if selected is not None and selected in candidates:
        return (selected,), (), True
    return candidates, tuple(dict.fromkeys(missing)), False


def _length_mm(raw: str | None) -> Decimal | None:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(MM|CM|M)", raw or "")
    if match:
        value = Decimal(match[1]) * {"MM": 1, "CM": 10, "M": 1000}[match[2]]
        return value if value > 0 else None
    return None


def _inches(raw: str | None) -> Decimal | None:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(?:/([1-9][0-9]*))?POL", raw or "")
    if match:
        value = Decimal(match[1]) / Decimal(match[2] or 1)
        return value if value > 0 else None
    return None
