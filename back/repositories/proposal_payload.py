"""Contrato persistido da revisão, comum ao batch em memória e aos checkpoints."""

import os

from domain.proposals import proposal_hash
from repositories.classification import DEFAULT_REPOSITORY as CLASSIFICATION_DEFAULT
from repositories.normalization import get_normalization_repository


def approval_payload(proposal, ids, dataset_id):
    members = [
        {
            "material_id": ids[m["material_code"]],
            "expected_version": m["observed_version"],
            "pdm_class_id": m.get("pdm_class_id", proposal.changeset.get("pdm_class_id")),
            "item_name": m.get("item_name", proposal.changeset.get("item_name")),
            "attributes": m["attributes"],
        }
        for m in proposal.members
    ]
    if any(member["material_id"] is None for member in members):
        raise ValueError("Todos os membros precisam existir na base antes de propor uma alteração")
    primary = next(m for m in proposal.members if m["material_code"] == proposal.suggested_primary_code)
    candidate = proposal.changeset["after"]
    after = {
        "pdm_class_id": candidate.get("pdm_class_id", proposal.changeset.get("pdm_class_id")),
        "item_name": candidate.get("item_name", proposal.changeset.get("item_name")),
        "attributes": candidate["attributes"],
        "unit": candidate.get("unit", primary["unit"]),
        "ncm": candidate.get("ncm", primary.get("ncm")),
    }
    normalizer = get_normalization_repository()
    conversions = {}
    for member in proposal.members:
        for raw_unit in sorted(
            {member["unit"], *(row["unit"] for row in member["inventory"])}, key=lambda unit: unit or ""
        ):
            unit = normalizer.normalize_unit(raw_unit)
            if unit.value == after["unit"] and raw_unit != unit.value:
                conversions[raw_unit] = {
                    "from_unit": raw_unit,
                    "to_unit": unit.value,
                    "factor": "1",
                    "source": unit.rule,
                }
    changes = proposal.changeset.get("changes", [])
    conflicts = list(proposal.conflicts)
    unsupported = {change["field"] for change in changes} - {"description", "merchandise_group", "unit", "ncm"}
    conflicts.extend(f"Alteração ainda não suportada: {field}" for field in sorted(unsupported))
    group = next((change for change in changes if change["field"] == "merchandise_group"), None)
    if group is not None:
        # A API confere o grupo com a classe PDM confirmada antes de gravar.
        after["merchandise_group"] = group["after"]
    changeset = {
        "schema_version": "proposal-v1",
        "dataset_id": dataset_id,
        "pdm_version": proposal.changeset["pdm_version"],
        "pdm_source_sha256": proposal.changeset["pdm_source_sha256"],
        "primary_material_code": proposal.suggested_primary_code,
        "ranking_score": proposal.ranking_score if proposal.proposal_type == "MERGE" else None,
        "after": after,
        "conversions": list(conversions.values()),
        "conflicts": conflicts,
        "changes": changes,
        "sources": {
            "pdm_class_id": "Classificação batch: "
            + os.environ.get("CLASSIFICATION_REPOSITORY", CLASSIFICATION_DEFAULT),
            "attributes": "Extração batch: "
            + os.environ.get("EXTRACTION_REPOSITORY", "rule_based_v1")
            + "; validação PDM e originais no dataset",
            "unit": "Normalização de unidade: " + normalizer.name,
            "ncm": "Normalização do NCM original; efetivação depende da revisão fiscal",
        },
    }
    if group is not None:
        changeset["sources"]["merchandise_group"] = "Grupo da classe PDM: " + group["source"]
    for field in ("ncm_assessment", "ncm_before_assessment"):
        if field in proposal.changeset:
            changeset[field] = proposal.changeset[field]
    if proposal.proposal_type == "NCM_CORRECTION":
        changeset["sources"]["ncm"] = next(change["source"] for change in changes if change["field"] == "ncm")
    lane = proposal.changeset.get("review_lane")
    if lane is not None:
        # Como revisar: em lote após amostra (níveis 1 e 2) ou item a item (nível 3). Decisão da #36.
        changeset["review_lane"] = lane
    return members, changeset, proposal_hash(members, changeset)
