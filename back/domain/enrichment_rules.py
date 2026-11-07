"""Proveniência e interpretação original compartilhadas pelo produtor e pela revisão."""

import os
from collections.abc import Mapping
from datetime import UTC, datetime

from domain.contracts import ClassificationInput
from domain.identity import IDENTITY_RULES_VERSION, resolve_item_name
from domain.proposals import canonical_hash
from domain.runtime import AWS_RUNTIME_VARIABLES
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.extraction.material_fields import MATERIAL_FIELDS_VERSION, extract_material_fields


def value(record, key, default=None):
    return record.get(key, default) if isinstance(record, Mapping) else getattr(record, key, default)


def original_hash(material) -> str:
    return canonical_hash(
        {
            "material_id": str(value(material, "id")),
            "material_code": value(material, "material_code"),
            "description": value(material, "original_description_long") or "",
            "short_description": value(material, "original_description_short") or "",
            "manufacturer": value(material, "manufacturer") or "",
            "reference": value(material, "manufacturer_reference") or "",
        }
    )


def extraction_signature(catalog) -> str:
    extractor = get_extraction_repository()
    classifier = get_classification_repository(catalog)
    return (
        f"{extractor.name}@{extractor.revision}|{classifier.name}@{classifier.revision}|"
        f"{IDENTITY_RULES_VERSION}|{MATERIAL_FIELDS_VERSION}"
    )


def original_item_name(catalog, class_id: str, material) -> str | None:
    cls = catalog.classes[class_id]
    if len(cls.item_names) == 1:
        return cls.item_names[0]
    result = get_classification_repository(catalog).classify(
        ClassificationInput(value(material, "original_description_long"), value(material, "original_description_short"))
    )
    names = [
        item.matched_name
        for item in result.evidence
        if item.class_id == class_id and item.matched_name in cls.item_names
    ]
    return resolve_item_name(cls, names) if result.pdm_class_id == class_id else None


def original_attributes(catalog, class_id: str, material) -> dict[str, str]:
    extracted = extract_material_fields(
        catalog.classes[class_id],
        value(material, "original_description_long") or "",
        value(material, "original_description_short") or "",
        manufacturer=value(material, "manufacturer"),
        reference=value(material, "manufacturer_reference"),
    )
    return {name: item.value for name, item in extracted.attributes.items()} | {
        name: item for name, item in (value(material, "attributes") or {}).items() if item
    }


def evidence_hash(source) -> str:
    fields = (
        "attribute_name",
        "proposed_value",
        "source_url",
        "source_title",
        "source_excerpt",
        "source_page",
        "source_sha256",
        "s3_object_key",
        "confidence_level",
    )
    data = {field: value(source, field) for field in fields}
    data["confidence_basis"] = value(source, "confidence_basis") or []
    retrieved = value(source, "retrieved_at")
    if isinstance(retrieved, str):
        retrieved = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    if retrieved is not None and retrieved.tzinfo is None:
        raise ValueError("Data da evidencia precisa informar fuso horario")
    data["retrieved_at"] = retrieved.astimezone(UTC).isoformat() if retrieved is not None else None
    return canonical_hash(data)


def check_simulated_evidence(simulated: bool) -> None:
    if simulated and (
        os.environ.get("APP_ENV", "production") != "local" or any(os.environ.get(k) for k in AWS_RUNTIME_VARIABLES)
    ):
        raise ValueError("Evidencia simulada so pode ser usada em APP_ENV=local fora de runtime AWS")
