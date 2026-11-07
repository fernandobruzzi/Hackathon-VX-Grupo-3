"""Revalida a origem dos atributos; evidência parcial não publica identidade canônica."""

from domain.contracts import ClassificationInput, MaterialRecord
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


def validate_internal_sources(changes, dataset, sources, primary=None, catalog=None, *, store=None):
    if changes.enrichment_context is None or changes.enrichment_context.schema_version != "internal-enrichment-v1":
        return
    files = {entry["name"]: entry for entry in dataset.files}
    supplemental = changes.enrichment_context.supplemental_source
    documents = {}
    if supplemental is not None:
        import hashlib

        from clients.storage import get_object_store
        from enrichment.internal_documents import load_supplemental_sources

        try:
            content = (store or get_object_store()).get(supplemental.object_key)
            if hashlib.sha256(content).hexdigest() != supplemental.sha256:
                raise ValueError("Hash documental divergente")
            documents = {
                source.material.record.code: source
                for source in load_supplemental_sources(content, str(dataset.id), catalog, supplemental.object_key)
            }
        except (ValueError, FileNotFoundError) as error:
            raise ApiError(409, "ENRICHMENT_BASIS_CHANGED", "Documento interno indisponível ou alterado.") from error
    for source in sources:
        matched = any(
            source.source_url
            and source.source_url.startswith(f"dataset://{dataset.id}/{name}#")
            and source.source_sha256 == entry["sha256"]
            and source.s3_object_key == entry["object_key"]
            for name, entry in files.items()
            if name in {"01_base_materiais.csv", "02_pedidos_cadastro.csv"}
        )
        if not matched and supplemental is not None:
            from domain.identity import compare_attributes
            from domain.identity_decision import decide_identity
            from pipelines.internal_enrichment import observation_conflicts, source_excerpt
            from pipelines.sanitize import analyze_material
            from repositories.extraction import get_extraction_repository

            prefix = f"dataset://{dataset.id}/internal-documents#"
            document = (
                documents.get(source.source_url[len(prefix) :])
                if source.source_url and source.source_url.startswith(prefix)
                else None
            )
            if document is not None and primary is not None:
                target = analyze_material(
                    MaterialRecord(
                        primary.material_code,
                        primary.status,
                        primary.original_description_long or "",
                        primary.original_description_short or "",
                        manufacturer=primary.manufacturer or "",
                        reference=primary.manufacturer_reference or "",
                        attributes=primary.attributes or {},
                    ),
                    catalog,
                    get_classification_repository(catalog),
                    get_extraction_repository(),
                )
                donor = document.material
                differences, _ = (
                    compare_attributes(catalog.classes[donor.pdm_class_id], target.attributes, donor.attributes)
                    if donor.pdm_class_id
                    else (["CLASS"], [])
                )
                optional_conflicts = any(
                    target.attributes.get(name) and target.attributes[name] != value
                    for name, value in donor.attributes.items()
                )
                matched = (
                    source.s3_object_key == supplemental.object_key
                    and source.source_sha256 == supplemental.sha256
                    and source.source_excerpt == source_excerpt(donor.record)
                    and source.source_title == document.title
                    and donor.attributes.get(source.attribute_name) == source.proposed_value
                    and not differences
                    and not optional_conflicts
                    and not observation_conflicts(target, catalog)
                    and not observation_conflicts(donor, catalog)
                    and decide_identity(catalog, target, donor).status == "SAME_MATERIAL"
                )
        if not matched or "INTERNAL_DATASET" not in (source.confidence_basis or []):
            raise ApiError(422, "INTERNAL_SOURCE_REQUIRED", "Fonte interna deve pertencer aos originais do dataset.")
