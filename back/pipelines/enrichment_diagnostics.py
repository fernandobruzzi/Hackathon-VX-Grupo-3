"""Perguntas por lacuna, sem confundir validade PDM com verdade documental."""

from domain.contracts import ClassificationInput
from domain.pdm_validator import validate_pdm
from repositories.classification import get_classification_repository
from repositories.extraction.rule_based_v1 import _clean_text, labeled_spans
from repositories.extraction.rule_based_v1_tables import KEY_ALIASES


def diagnose(material, catalog, before, after, record_conflicts, source_conflicts):
    cls = catalog.classes.get(material.pdm_class_id)
    if cls is None:
        record = material.record
        result = get_classification_repository(catalog).classify(
            ClassificationInput(record.description, record.short_description, record.group)
        )
        return {
            "classification": {"status": result.status.value, "candidate_class_ids": list(result.candidate_class_ids)},
            "gaps": [
                {
                    "attribute": None,
                    "reason": f"CLASS_{result.status.value}",
                    "question": "Qual é o tipo do item e qual documento identifica sua classe de cadastro?",
                }
            ],
        }
    checked = validate_pdm(catalog, cls.id, material.attributes, item_name=material.item_name)
    questions = {a.name: a.question for a in checked.missing_attributes}
    raw = _clean_text(material.record.description + " ; " + material.record.short_description)
    labeled = set()
    for _, _, label in labeled_spans([a.name for a in cls.attributes], raw):
        labeled.update({label, *KEY_ALIASES.get(label, ())})
    gaps = []
    names = list(
        dict.fromkeys(
            after["missing_required"]
            + after["optional_missing"]
            + after["conditional_pending"]
            + list(record_conflicts)
            + list(source_conflicts)
            + [a["name"] for a in after["invalid"]]
        )
    )
    invalid = {a["name"] for a in after["invalid"]}
    for name in names:
        if name in record_conflicts:
            reason = "CONTRADICTORY_OBSERVATIONS"
            question = (
                f"Qual é o valor correto de {name}? Os textos originais apresentam valores divergentes. Anexe a fonte."
            )
        elif name in source_conflicts:
            reason = "CONFLICTING_SOURCES"
            question = f"Qual fonte confirma {name}? Há valores divergentes entre os registros."
        elif name in invalid:
            reason = "INVALID_VALUE"
            question = f"Confirme {name} com uma fonte e um valor aceito pelo PDM."
        elif name in after["conditional_pending"]:
            reason = "CONDITION_UNRESOLVED"
            question = f"Confirme o tipo e as características que determinam se {name} se aplica ao item."
        else:
            reason = (
                "TEXT_NOT_RECOGNIZED"
                if name in labeled
                else "IDENTITY_NOT_CONFIRMED"
                if not material.identity_key
                else "NO_SUPPORTED_EVIDENCE"
            )
            question = questions.get(name, f"Qual é {name}? Informe o valor e o trecho do documento que o comprova.")
        gaps.append({"attribute": name, "reason": reason, "question": question})
    return {"classification": {"status": "CLASSIFIED", "candidate_class_ids": [cls.id]}, "gaps": gaps}
