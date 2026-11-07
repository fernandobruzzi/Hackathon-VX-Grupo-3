"""Reconstitui as evidências atuais para a política automática, sem escrever no cadastro."""

from domain.automatic_corrections import AutomaticEligibility, assess_automatic_correction
from domain.contracts import ClassificationInput, MaterialRecord, PdmCatalog
from pipelines.corrections import correction_proposals, pending_for
from pipelines.sanitize import analysis_signature, analyze_material
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.corrections.head_noun_v1 import opens_description
from repositories.extraction import get_extraction_repository
from repositories.extraction.material_fields import MATERIAL_FIELDS_VERSION, extract_material_fields
from repositories.normalization import get_normalization_repository
from repositories.proposal_payload import approval_payload
from repositories.text_loss import get_text_loss_repository


def current_rules(catalog: PdmCatalog) -> str:
    return analysis_signature(catalog, get_classification_repository(catalog), get_extraction_repository())


def assess_record(
    catalog: PdmCatalog, record: MaterialRecord, proposal_type: str, changeset: dict, current: dict, dataset_id: str
) -> AutomaticEligibility:
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    corrector, normalizer, text_loss = (
        get_correction_repository(),
        get_normalization_repository(),
        get_text_loss_repository(),
    )
    algorithms = (classifier.name, extractor.name, corrector.name, normalizer.name, text_loss.name)
    known = algorithms == ("aliases_v1", "rule_based_v1", "head_noun_v1", "rule_based_v1", "unresolved_terms_v1")
    # Revisões novas exigem medir a política novamente, mesmo com o mesmo nome de algoritmo.
    revisions = (classifier.revision, extractor.revision)
    known = (
        known
        and revisions == ("3-pilot-families-263", "11-quantity-reference-199")
        and MATERIAL_FIELDS_VERSION == "independent-fields-v1"
    )
    analyzed = analyze_material(record, catalog, classifier, extractor)
    extracted = (
        extract_material_fields(
            catalog.classes[analyzed.pdm_class_id],
            record.description,
            record.short_description,
            manufacturer=record.manufacturer,
            reference=record.reference,
            extractor=extractor,
        )
        if analyzed.pdm_class_id
        else None
    )
    corrections = corrector.correct(analyzed, catalog, normalizer)
    fresh = next(
        (
            item
            for item in correction_proposals(analyzed, corrections, catalog, corrector.name, text_loss)
            if item.proposal_type == proposal_type
        ),
        None,
    )
    reproducible = False
    if fresh is not None:
        _, payload, _ = approval_payload(fresh, {record.code: record.database_id}, dataset_id)
        # O nível persistido não autoriza: a classificação, os valores e cada mudança são refeitos.
        keys = {"after", "changes", "conversions", "sources", "pdm_version", "pdm_source_sha256"}
        reproducible = all(changeset.get(key) == payload.get(key) for key in keys)
    trusted = bool(
        known
        and analyzed.pdm_class_id
        and analyzed.item_name
        and opens_description(analyzed.item_name, record.description)
    )
    description = next(
        (change.get("after") for change in changeset.get("changes", []) if change.get("field") == "description"), None
    )
    lost = (
        text_loss.lost_terms(analyzed, catalog.classes[analyzed.pdm_class_id], description)
        if (description and analyzed.pdm_class_id)
        else ()
    )
    pending = pending_for(proposal_type, corrections.pending)
    # Recuperar um atributo da curta não amplia a autorização anterior de publicação PDM.
    # A sugestão continua disponível para aprovação humana com o trecho e a origem registrados.
    if proposal_type == "PDM_CORRECTION" and extracted and "short_description" in extracted.origins.values():
        pending += ("SHORT_DESCRIPTION_REQUIRES_REVIEW",)
    verdict = assess_automatic_correction(
        catalog,
        analyzed,
        proposal_type,
        changeset,
        current,
        normalizer,
        trusted_class=trusted,
        reproducible=reproducible and known,
        lost_terms=lost,
        pending=pending,
    )
    classification = classifier.classify(
        ClassificationInput(record.description, record.short_description or None, record.group or None)
    )
    evidence = {
        **verdict.evidence,
        "rules_signature": current_rules(catalog),
        "algorithms": list(algorithms),
        "algorithm_revisions": list(revisions),
        "field_reader_revision": MATERIAL_FIELDS_VERSION,
        "original_short_description": record.short_description,
        "trusted_class": trusted,
        "classification_evidence": [
            {"class_id": item.class_id, "matched_name": item.matched_name} for item in classification.evidence
        ],
        "attribute_evidence": {
            name: {
                "value": item.value,
                "original": item.original,
                "rule": item.rule,
                "source_field": extracted.origins[name],
            }
            for name, item in extracted.attributes.items()
        }
        if extracted
        else {},
    }
    return AutomaticEligibility(verdict.eligible, verdict.reasons, evidence)
