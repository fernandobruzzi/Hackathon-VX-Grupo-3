"""Equivalências técnicas e dúvidas de identidade, separadas das propostas aplicáveis."""

import hashlib
import json
from collections import defaultdict

from clients.storage import ObjectStore
from domain.contracts import AnalyzedMaterial, IdentityMode, PdmCatalog
from domain.identity import IDENTITY_RULES_VERSION, material_manufacturer, material_review_reasons


def _evidence(material: AnalyzedMaterial) -> dict:
    return {
        "material_code": material.record.code,
        "observed_version": material.record.version,
        "original_description": material.record.description,
        "original_manufacturer": material.record.manufacturer,
        "original_reference": material.record.reference,
        "pdm_class_id": material.pdm_class_id,
        "item_name": material.item_name,
        "attributes": material.attributes,
    }


def identity_review_report(materials: list[AnalyzedMaterial], catalog: PdmCatalog) -> dict:
    pending = []
    technical: dict[tuple, list[AnalyzedMaterial]] = defaultdict(list)
    for material in sorted(materials, key=lambda m: m.record.code):
        if material.record.status != "ATIVO" or material.pdm_class_id is None:
            continue
        pdm_class = catalog.classes[material.pdm_class_id]
        reasons = material_review_reasons(material, pdm_class)
        if reasons:
            pending.append({"reasons": list(reasons), "evidence": _evidence(material)})
        elif (
            material.identity_key
            and material_manufacturer(material)
            and pdm_class.identity_mode is IdentityMode.TECHNICAL_ATTRIBUTES
        ):
            technical[(material.identity_key, material.item_name)].append(material)
    equivalences = [
        {
            "rule": "same_technical_identity_different_manufacturers",
            "status": "REVIEW_REQUIRED",
            "identity_verified": False,
            "members": [_evidence(m) for m in members],
        }
        for _, members in sorted(technical.items(), key=lambda item: str(item[0]))
        if len({material_manufacturer(m) for m in members}) > 1
    ]
    return {
        "schema": "identity-review-v1",
        "rules_version": IDENTITY_RULES_VERSION,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "master_data_modified": False,
        "equivalence_candidates": equivalences,
        "manual_review": pending,
    }


def store_identity_review(report: dict, store: ObjectStore, tenant_id: str) -> str:
    """Registro imutável e repetível; não autoriza substituição, bloqueio ou consolidação."""
    content = json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    key = f"runs/{tenant_id}/identity-review/{digest}.json"
    return store.put_if_absent(key, content).key
