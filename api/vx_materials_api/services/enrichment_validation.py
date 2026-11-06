"""Revalida a origem dos atributos; evidência parcial não publica identidade canônica."""

from domain.enrichment_rules import (
    check_simulated_evidence,
    extraction_signature,
    original_attributes,
    original_hash,
    original_item_name,
)
from enrichment.catalog import REAL_PRODUCTS
from vx_materials_api.errors import ApiError


def validate_enrichment_context(changes, primary, dataset, catalog):
    if changes.enrichment_context is None:
        return dict(primary.attributes or {})
    context = changes.enrichment_context.model_dump()
    product = REAL_PRODUCTS.get(primary.material_code)
    if product is None or primary.material_code not in dataset.real_material_codes:
        raise ApiError(422, "REAL_PRODUCT_REQUIRED", "Enriquecimento permitido somente nos 15 produtos originais.")
    if (
        context.get("schema_version") != "enrichment-v1"
        or context.get("original_hash") != original_hash(primary)
        or context.get("extraction_signature") != extraction_signature(catalog)
        or changes.after.pdm_class_id != product.pdm_class_id
        or changes.after.item_name != original_item_name(catalog, product.pdm_class_id, primary)
        or (primary.pdm_class_id is not None and primary.pdm_class_id != product.pdm_class_id)
    ):
        raise ApiError(409, "ENRICHMENT_BASIS_CHANGED", "O original ou as regras mudaram. Gere outra proposta.")
    if changes.after.unit != primary.unit or changes.after.ncm != primary.ncm:
        raise ApiError(422, "ENRICHMENT_SCOPE", "Enriquecimento nao altera unidade ou NCM.")
    baseline = original_attributes(catalog, product.pdm_class_id, primary)
    if any(changes.after.attributes.get(name) != current for name, current in baseline.items()):
        raise ApiError(422, "ENRICHMENT_SCOPE", "Enriquecimento nao remove nem substitui atributos conhecidos.")
    held = set(context.get("divergent_attributes", [])) | set(context.get("blocked_attributes", []))
    if any(changes.after.attributes.get(name) != baseline.get(name) for name in held):
        raise ApiError(
            422, "ENRICHMENT_DIVERGENCE", "Atributos divergentes ou invalidos nao fazem parte desta aprovacao."
        )
    return baseline


def check_source_environment(sources):
    try:
        check_simulated_evidence(any("SIMULATED" in (source.confidence_basis or []) for source in sources))
    except ValueError as error:
        raise ApiError(422, "SIMULATED_EVIDENCE_FORBIDDEN", str(error)) from None
