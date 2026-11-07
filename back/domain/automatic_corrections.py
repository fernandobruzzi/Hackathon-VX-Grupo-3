"""Política determinística de autorização automática; nível de revisão não autoriza escrita."""

from dataclasses import dataclass
from typing import Any

from domain.contracts import AnalyzedMaterial, FieldStatus, NormalizationRepository, PdmCatalog
from domain.pdm_validator import validate_pdm
from domain.proposal_validation import is_approvable

POLICY_VERSION = "safe-corrections-v1"
AUTOMATIC_TYPES = frozenset({"UNIT_CORRECTION", "PDM_CORRECTION"})
ALLOWED_MATERIAL_FIELDS = {
    "UNIT_CORRECTION": frozenset({"unit", "version"}),
    "PDM_CORRECTION": frozenset(
        {"pdm_class_id", "pdm_version", "pdm_description", "attributes", "identity_key", "is_canonical", "version"}
    ),
}


@dataclass(frozen=True)
class AutomaticEligibility:
    eligible: bool
    reasons: tuple[str, ...]
    evidence: dict[str, Any]
    policy_version: str = POLICY_VERSION


def assess_automatic_correction(
    catalog: PdmCatalog,
    analyzed: AnalyzedMaterial,
    proposal_type: str,
    changeset: dict,
    current: dict,
    normalizer: NormalizationRepository,
    *,
    trusted_class: bool,
    reproducible: bool,
    lost_terms: tuple[str, ...] = (),
    pending: tuple[str, ...] = (),
) -> AutomaticEligibility:
    """A mesma decisão atende relatório, simulação e aplicação; falha de evidência fecha a autorização."""
    record = analyzed.record
    reasons: list[str] = []
    changes = changeset.get("changes", [])
    after = changeset.get("after", {})
    evidence = {
        "material_code": record.code,
        "material_version": record.version,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "pdm_class_id": analyzed.pdm_class_id,
        "item_name": analyzed.item_name,
        "attributes": analyzed.attributes,
        "original_description": record.description,
        "changes": changes,
        "lost_terms": list(lost_terms),
        "pending": list(pending),
    }
    if proposal_type not in AUTOMATIC_TYPES:
        reasons.append("UNSUPPORTED_TYPE")
    if record.status != "ATIVO" or current.get("active_code_target"):
        reasons.append("MATERIAL_NOT_ACTIVE")
    if not trusted_class or analyzed.review_reasons or not analyzed.identity_key:
        # Identidade incompleta não impede alias de unidade se a classe for inequívoca.
        if proposal_type != "UNIT_CORRECTION" or not trusted_class or analyzed.review_reasons:
            reasons.append("UNTRUSTED_CLASS")
    if not reproducible:
        reasons.append("PROPOSAL_NOT_REPRODUCIBLE")
    if changeset.get("conflicts") or pending:
        reasons.append("CONFLICT")
    lane = changeset.get("review_lane")
    if lane and lane.get("reasons"):
        reasons.append("REVIEW_REASONS_PRESENT")
    if changeset.get("pdm_version") != catalog.version or changeset.get("pdm_source_sha256") != catalog.source_sha256:
        reasons.append("REFERENCE_CHANGED")
    if after.get("ncm") != current.get("ncm") or any(change.get("field") == "ncm" for change in changes):
        reasons.append("FISCAL_CHANGE")
    if changeset.get("ncm_assessment") or changeset.get("ncm_before_assessment"):
        reasons.append("FISCAL_CONTEXT")
    for conversion in changeset.get("conversions", []):
        source = normalizer.normalize_unit(conversion.get("from_unit"))
        if (
            source.rule != "rule_based_v1/unit.alias"
            or source.value != conversion.get("to_unit")
            or conversion.get("factor") != "1"
            or conversion.get("source") != "rule_based_v1/unit.alias"
        ):
            reasons.append("PHYSICAL_CONVERSION")
    if after.get("pdm_class_id") != analyzed.pdm_class_id or after.get("item_name") != analyzed.item_name:
        reasons.append("UNTRUSTED_CLASS")
    if after.get("attributes") != analyzed.attributes:
        reasons.append("UNSUPPORTED_ATTRIBUTES")
    current_class = current.get("pdm_class_id")
    current_attributes = current.get("attributes") or {}
    if current_class and current_class != analyzed.pdm_class_id:
        reasons.append("CURRENT_TECHNICAL_CONTRADICTION")
    if any(value != analyzed.attributes.get(name) for name, value in current_attributes.items()):
        reasons.append("CURRENT_TECHNICAL_CONTRADICTION")
    pdm_class = catalog.classes.get(analyzed.pdm_class_id)
    if proposal_type == "UNIT_CORRECTION":
        unit = normalizer.normalize_unit(record.unit)
        if (
            len(changes) != 1
            or changes[0].get("field") != "unit"
            or changes[0].get("source") != "rule_based_v1/unit.alias"
            or unit.status is not FieldStatus.NORMALIZED
            or unit.value != after.get("unit")
            or not pdm_class
            or unit.value != pdm_class.default_unit
            or (changes[0].get("before"), changes[0].get("after")) != (record.unit, unit.value)
        ):
            reasons.append("UNIT_NOT_SAFE_ALIAS")
    elif proposal_type == "PDM_CORRECTION":
        if (
            len(changes) != 1
            or changes[0].get("field") != "description"
            or changes[0].get("source") != "head_noun_v1/description.pdm_format"
            or after.get("merchandise_group") is not None
            or after.get("unit") != current.get("unit")
        ):
            reasons.append("OUT_OF_SCOPE_CHANGE")
        validation = validate_pdm(
            catalog, analyzed.pdm_class_id, analyzed.attributes, item_name=analyzed.item_name, unit=after.get("unit")
        )
        if (
            not is_approvable(validation)
            or not validation.identity_key
            or not changes
            or changes[0].get("after") != validation.formatted_description
        ):
            reasons.append("PDM_INCOMPLETE_OR_INVALID")
        if lost_terms:
            reasons.append("TEXT_LOSS")
        if current.get("pdm_description") == validation.formatted_description:
            reasons.append("ALREADY_STANDARDIZED")
        for field, attribute in [("manufacturer", "FABRICANTE"), ("manufacturer_reference", "REFERENCIA FABRICANTE")]:
            if analyzed.attributes.get(attribute, current.get(field)) != current.get(field):
                reasons.append("OUT_OF_SCOPE_CHANGE")
    return AutomaticEligibility(not reasons, tuple(dict.fromkeys(reasons)) or ("SAFE_CORRECTION",), evidence)
