"""Saneamento: analisa os materiais e propõe unificações e correções. Nada é aplicado: quem decide é uma pessoa.

Etapas: classe do PDM, extração de atributos, validação e identidade, candidatos, verificação e
proposta. Cada etapa vem de um repositório trocável por configuração.
"""

import csv
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from domain.contracts import (
    AnalyzedMaterial,
    CandidateGroup,
    CandidateRepository,
    ClassificationInput,
    ClassificationRepository,
    ExtractionRepository,
    FieldStatus,
    IdentityMode,
    MaterialRecord,
    MergeProposal,
    NormalizationRepository,
    PdmCatalog,
)
from domain.identity import (
    IDENTITY_RULES_VERSION,
    compare_attributes,
    material_review_reasons,
    merge_partition,
    partial_identity_key,
)
from domain.pdm_formatter import format_description
from domain.pdm_loader import load_pdm
from domain.pdm_validator import validate_pdm
from domain.proposal_validation import approval_blockers
from pipelines.corrections import propose_corrections, summarize_corrections
from pipelines.identity_review import identity_review_report
from pipelines.ncm_corrections import propose_ncm_corrections
from repositories.candidates import get_candidate_repository
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

_REDIRECT_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")
_NAMESPACE = uuid.UUID("0e1f2a54-9d3c-4b57-8a26-7c41d2f6b390")


def analysis_signature(
    catalog: PdmCatalog, classifier: ClassificationRepository, extractor: ExtractionRepository
) -> str:
    """Regras que `analyze_material` usa: PDM pelo conteúdo, revisões dos algoritmos e da identidade.

    Duas análises só se combinam com a mesma assinatura, no índice de busca e na retomada de um job.
    """
    return "|".join(
        [
            catalog.version,
            f"pdm-sha256:{catalog.source_sha256}",
            f"classifier:{classifier.name}@{classifier.revision}",
            f"extractor:{extractor.name}@{extractor.revision}",
            IDENTITY_RULES_VERSION,
        ]
    )


def analyze_material(
    record: MaterialRecord,
    catalog: PdmCatalog,
    classifier: ClassificationRepository,
    extractor: ExtractionRepository,
) -> AnalyzedMaterial:
    description = _REDIRECT_PREFIX.sub("", record.description)
    classification = classifier.classify(
        ClassificationInput(description, record.short_description or None, record.group or None)
    )
    class_id = classification.pdm_class_id
    if class_id is None:
        return AnalyzedMaterial(record, None, None, {}, None)
    pdm_class = catalog.classes[class_id]
    item_name = _item_name(pdm_class.item_names, [evidence.matched_name for evidence in classification.evidence])
    extraction = extractor.extract(
        pdm_class,
        description,
        manufacturer=record.manufacturer or None,
        manufacturer_reference=record.reference or None,
    )
    attributes = {name: value.value for name, value in extraction.attributes.items()}
    validation = validate_pdm(catalog, class_id, attributes, item_name=item_name)
    identity_key = validation.identity_key or partial_identity_key(pdm_class, attributes)
    material = AnalyzedMaterial(record, class_id, item_name, attributes, identity_key)
    if material_review_reasons(material, pdm_class):
        return AnalyzedMaterial(record, class_id, item_name, attributes, None)
    return material


def _item_name(item_names: tuple[str, ...], evidence: Iterable[str]) -> str | None:
    if len(item_names) == 1:
        return item_names[0]
    matches = [name for name in evidence if name in item_names]
    return max(matches, key=len) if matches else None


def build_proposal(
    group: CandidateGroup,
    materials: dict[str, AnalyzedMaterial],
    catalog: PdmCatalog,
    normalizer: NormalizationRepository,
) -> MergeProposal:
    members = [materials[code] for code in group.codes]
    pdm_class = catalog.classes[members[0].pdm_class_id]
    if (
        any(member.pdm_class_id != pdm_class.id or material_review_reasons(member, pdm_class) for member in members)
        or len({(merge_partition(member)[1], member.item_name) for member in members}) != 1
    ):
        raise ValueError("MERGE recusado: fabricante, nome da peca ou referencia exige revisao")
    if group.identity_verified and (not members[0].identity_key or len({m.identity_key for m in members}) != 1):
        raise ValueError("MERGE recusado: identidade declarada nao confere com os membros")
    primary = _suggest_primary(members)
    conflicts: list[str] = []
    if not group.identity_verified:
        conflicts.append("IDENTIDADE_NAO_VERIFICADA: faltam atributos para confirmar pela regra do PDM")

    units = [normalizer.normalize_unit(member.record.unit) for member in members]
    if any(unit.status is FieldStatus.UNRESOLVED for unit in units):
        conflicts.append("UNIDADE_SEM_FATOR: consolidacao de quantidade bloqueada ate definir a conversao")
    elif len({unit.value for unit in units}) > 1:
        conflicts.append("UNIDADES_DIFERENTES: consolidacao de quantidade bloqueada ate definir a conversao")

    ncms = [normalizer.normalize_ncm(member.record.ncm).value for member in members]
    divergent_ncms = len(set(ncms)) > 1
    target_ncm = normalizer.normalize_ncm(primary.record.ncm).value
    fiscal_required = divergent_ncms or any((m.record.ncm or None) != target_ncm for m in members)
    if divergent_ncms:
        conflicts.append("NCM_DIVERGENTE: exige revisao fiscal")

    attributes = {name: value for name, value in primary.attributes.items()}
    for member in members:
        for name, value in member.attributes.items():
            attributes.setdefault(name, value)
    for other in members:
        if other is not primary:
            differing, _ = compare_attributes(pdm_class, primary.attributes, other.attributes)
            conflicts.extend(f"ATRIBUTO_DIVERGENTE: {name}" for name in differing)

    item_name = primary.item_name or next((m.item_name for m in members if m.item_name), None)
    target_unit = normalizer.normalize_unit(primary.record.unit).value or primary.record.unit
    # Mesma validação da aprovação: sem isso, a fila ofereceria o que a aprovação recusa.
    conflicts.extend(
        approval_blockers(
            catalog,
            {"pdm_class_id": pdm_class.id, "item_name": item_name, "attributes": attributes, "unit": target_unit},
            [_member(member) for member in members],
        )
    )
    conflicts = list(dict.fromkeys(conflicts))

    changeset = {
        "identity_rules_version": IDENTITY_RULES_VERSION,
        "match_type": group.match_type.value,
        "identity_verified": group.identity_verified,
        "identity_key": primary.identity_key if group.identity_verified else None,
        "identity_mode": IdentityMode(pdm_class.identity_mode).value,
        "pdm_class_id": pdm_class.id,
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "primary_material_code": primary.record.code,
        "blocked_material_codes": [m.record.code for m in members if m is not primary],
        "conflicts": conflicts,
        "ranking_score": group.score,
        "after": {
            "pdm_class_id": pdm_class.id,
            "item_name": item_name,
            "unit": target_unit,
            "ncm": target_ncm,
            "description": format_description(pdm_class, item_name, attributes) if item_name else None,
            "attributes": attributes,
        },
    }
    payload = json.dumps(changeset, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return MergeProposal(
        id=str(uuid.uuid5(_NAMESPACE, f"{catalog.version}|{group.match_type.value}|{'|'.join(group.codes)}")),
        proposal_type="MERGE",
        material_codes=group.codes,
        suggested_primary_code=primary.record.code,
        members=tuple(_member(member) for member in members),
        changeset=changeset,
        changeset_hash=digest,
        conflicts=tuple(conflicts),
        fiscal_review_required=fiscal_required,
        ranking_score=group.score,
    )


def _suggest_primary(members: list[AnalyzedMaterial]) -> AnalyzedMaterial:
    """Mais estoque em valor; no empate, o código menor, para o resultado ser repetível."""
    return min(members, key=lambda m: (-Decimal(m.record.total_value or "0"), m.record.code))


def _member(member: AnalyzedMaterial) -> dict:
    record = member.record
    return {
        "material_code": record.code,
        "observed_version": record.version,
        "status": record.status,
        "description": record.description,
        "unit": record.unit,
        "ncm": record.ncm or None,
        "value_brl": record.total_value,
        "inventory": list(record.inventory),
        "attributes": member.attributes,
        "pdm_class_id": member.pdm_class_id,
        "item_name": member.item_name,
    }


def propose_merges(
    records: Iterable[MaterialRecord],
    catalog: PdmCatalog,
    classifier: ClassificationRepository,
    extractor: ExtractionRepository,
    candidates: CandidateRepository,
    normalizer: NormalizationRepository,
) -> list[MergeProposal]:
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
    return merge_proposals(analyzed, catalog, candidates, normalizer)


def merge_proposals(
    analyzed: list[AnalyzedMaterial],
    catalog: PdmCatalog,
    candidates: CandidateRepository,
    normalizer: NormalizationRepository,
) -> list[MergeProposal]:
    by_code = {material.record.code: material for material in analyzed}
    groups = candidates.find(analyzed, catalog)
    proposals = [build_proposal(group, by_code, catalog, normalizer) for group in groups]
    return sorted(proposals, key=lambda proposal: (-proposal.ranking_score, proposal.material_codes))


def read_csv_records(path: str) -> list[MaterialRecord]:
    with open(path, encoding="utf-8-sig", newline="") as source:
        return [
            MaterialRecord(
                code=row["CODIGO_MATERIAL"],
                status=row["STATUS"],
                description=row["DESCRICAO_LONGA"],
                short_description=row["DESCRICAO_CURTA"],
                group=row["GRUPO_MERCADORIA"],
                manufacturer=row["FABRICANTE"],
                reference=row["REFERENCIA_FABRICANTE"],
                unit=row["UNIDADE_MEDIDA"],
                ncm=row["NCM"],
                total_value=str(Decimal(row["ESTOQUE_ATUAL"]) * Decimal(row["PRECO_MEDIO_UNITARIO"])),
            )
            for row in csv.DictReader(source)
        ]


def _catalog(pdm_workbook: str | None) -> PdmCatalog:
    default = "data/desafio01/03_padrao_cadastro_PDM.xlsx"
    return load_pdm(pdm_workbook or os.environ.get("PDM_WORKBOOK_PATH", default))


def _propose(
    records: list[MaterialRecord],
    catalog: PdmCatalog,
    repository_name: str | None,
    correction_repository: str | None = None,
    identity_review: dict | None = None,
) -> tuple[list[MergeProposal], list[MergeProposal], Counter[str]]:
    """Analisa cada material uma vez e gera as unificações e as correções."""
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    normalizer = get_normalization_repository()
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
    if identity_review is not None:
        identity_review.update(identity_review_report(analyzed, catalog))
    merges = merge_proposals(analyzed, catalog, get_candidate_repository(repository_name), normalizer)
    corrections, pending = propose_corrections(
        analyzed, catalog, normalizer, get_correction_repository(correction_repository)
    )
    return merges, corrections + propose_ncm_corrections(analyzed, catalog), pending


def summarize(proposals: list[MergeProposal]) -> dict:
    conflicts: Counter[str] = Counter()
    for proposal in proposals:
        conflicts.update(conflict.split(":")[0] for conflict in proposal.conflicts)
    return {
        "proposals": len(proposals),
        "materials": len({code for proposal in proposals for code in proposal.material_codes}),
        "identity_verified": sum(proposal.changeset["identity_verified"] for proposal in proposals),
        "fiscal_review_required": sum(proposal.fiscal_review_required for proposal in proposals),
        "conflicts": dict(conflicts.most_common()),
    }


def sanitize_report(
    path: str,
    pdm_workbook: str | None = None,
    repository_name: str | None = None,
    correction_repository: str | None = None,
) -> dict:
    catalog = _catalog(pdm_workbook)
    review = {}
    merges, corrections, pending = _propose(
        read_csv_records(path), catalog, repository_name, correction_repository, review
    )
    return {**summarize(merges), "corrections": summarize_corrections(corrections, pending), "identity_review": review}
