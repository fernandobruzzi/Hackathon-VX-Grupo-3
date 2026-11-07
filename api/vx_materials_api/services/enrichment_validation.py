"""Revalida a origem dos atributos; evidência parcial não publica identidade canônica."""

from domain.contracts import ClassificationInput
from domain.enrichment_rules import (
    check_simulated_evidence,
    extraction_signature,
    original_attributes,
    original_hash,
    original_item_name,
)
from domain.proposals import canonical_hash
from enrichment.catalog import REAL_PRODUCTS
from repositories.classification import get_classification_repository
from vx_materials_api.errors import ApiError


def validate_enrichment_context(changes, primary, dataset, catalog):
    if changes.enrichment_context is None:
        return dict(primary.attributes or {})
    context = changes.enrichment_context.model_dump()
    internal = context.get("schema_version") == "internal-enrichment-v1"
    product = REAL_PRODUCTS.get(primary.material_code)
    class_id = changes.after.pdm_class_id if internal else (product.pdm_class_id if product else None)
    if internal:
        classification = get_classification_repository(catalog).classify(
            ClassificationInput(primary.original_description_long, primary.original_description_short)
        )
        if classification.pdm_class_id != class_id or context["manifest_sha256"] != canonical_hash(dataset.files):
            raise ApiError(409, "ENRICHMENT_BASIS_CHANGED", "A classe ou os arquivos internos mudaram.")
    if not internal and (product is None or primary.material_code not in dataset.real_material_codes):
        raise ApiError(422, "REAL_PRODUCT_REQUIRED", "Enriquecimento permitido somente nos 15 produtos originais.")
    if (
        context.get("schema_version") not in {"enrichment-v1", "internal-enrichment-v1"}
        or context.get("original_hash") != original_hash(primary)
        or context.get("extraction_signature") != extraction_signature(catalog)
        or changes.after.pdm_class_id != class_id
        or changes.after.item_name != original_item_name(catalog, class_id, primary)
        or (primary.pdm_class_id is not None and primary.pdm_class_id != class_id)
    ):
        raise ApiError(409, "ENRICHMENT_BASIS_CHANGED", "O original ou as regras mudaram. Gere outra proposta.")
    if changes.after.unit != primary.unit or changes.after.ncm != primary.ncm:
        raise ApiError(422, "ENRICHMENT_SCOPE", "Enriquecimento nao altera unidade ou NCM.")
    baseline = original_attributes(catalog, class_id, primary)
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


def validate_internal_sources(changes, dataset, sources):
    if changes.enrichment_context is None or changes.enrichment_context.schema_version != "internal-enrichment-v1":
        return
    files = {entry["name"]: entry for entry in dataset.files}
    for source in sources:
        matched = any(
            source.source_url
            and source.source_url.startswith(f"dataset://{dataset.id}/{name}#")
            and source.source_sha256 == entry["sha256"]
            and source.s3_object_key == entry["object_key"]
            for name, entry in files.items()
            if name in {"01_base_materiais.csv", "02_pedidos_cadastro.csv"}
        )
        if not matched or "INTERNAL_DATASET" not in (source.confidence_basis or []):
            raise ApiError(422, "INTERNAL_SOURCE_REQUIRED", "Fonte interna deve pertencer aos originais do dataset.")
