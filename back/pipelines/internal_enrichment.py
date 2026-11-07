"""Completude e sugestões dos originais internos; nunca altera o cadastro nem presume identidade."""

import csv
import hashlib
import io
from collections import Counter, defaultdict
from dataclasses import dataclass

from botocore.exceptions import ClientError

from domain.contracts import AnalyzedMaterial, MaterialRecord
from domain.identity import compare_attributes, manufacturer_key, reference_spelling_key
from domain.identity_decision import decide_identity
from domain.pdm_validator import _applies, validate_pdm
from domain.proposals import canonical_hash
from pipelines.import_orders import read_orders
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository
from repositories.extraction.rule_based_v1 import _LINE_BREAK, _SEGMENTS, _clean_text, labeled_spans

VERSION = "internal-enrichment-v2"


@dataclass(frozen=True)
class InternalSource:
    material: AnalyzedMaterial
    filename: str
    sha256: str
    object_key: str
    title: str | None = None


def source_excerpt(record):
    excerpt = record.description
    if record.short_description:
        excerpt += f"\nDESCRICAO_CURTA: {record.short_description}"
    if record.manufacturer or record.reference:
        excerpt += f"\nFABRICANTE: {record.manufacturer}\nREFERENCIA_FABRICANTE: {record.reference}"
    return excerpt


def read_sources(files, store, catalog):
    """Lê somente bytes vinculados ao dataset. Arquivo ausente é pendência; hash divergente é erro."""
    sources, unavailable = [], []
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    for entry in sorted(files, key=lambda e: e["name"]):
        name = entry["name"]
        if name not in {"01_base_materiais.csv", "02_pedidos_cadastro.csv"}:
            continue
        try:
            content = store.get(entry["object_key"])
        except (FileNotFoundError, ClientError) as error:
            if isinstance(error, ClientError) and error.response["Error"]["Code"] not in {"NoSuchKey", "404"}:
                raise
            unavailable.append(name)
            continue
        if len(content) > 20_000_000 or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Hash ou tamanho da fonte interna inválido: {name}")
        if name == "01_base_materiais.csv":
            rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
            records = [
                MaterialRecord(
                    r["CODIGO_MATERIAL"],
                    r["STATUS"],
                    r["DESCRICAO_LONGA"],
                    r["DESCRICAO_CURTA"],
                    r["GRUPO_MERCADORIA"],
                    r["FABRICANTE"],
                    r["REFERENCIA_FABRICANTE"],
                    r["UNIDADE_MEDIDA"],
                    r["NCM"],
                )
                for r in rows
            ]
        else:
            records = [
                MaterialRecord(
                    o.source_order_id, "ATIVO", "\n".join(p for p in (o.original_text, o.attachment_text) if p)
                )
                for o in read_orders(content)
            ]
        if len({r.code for r in records}) != len(records):
            raise ValueError(f"Identificadores repetidos na fonte interna: {name}")
        sources.extend(
            InternalSource(
                analyze_material(r, catalog, classifier, extractor), name, entry["sha256"], entry["object_key"]
            )
            for r in records
        )
    found = {entry["name"] for entry in files}
    unavailable += sorted({"01_base_materiais.csv", "02_pedidos_cadastro.csv"} - found)
    return sources, unavailable


def completeness(material, catalog, attributes=None):
    attrs = material.attributes if attributes is None else attributes
    checked = validate_pdm(catalog, material.pdm_class_id, attrs, item_name=material.item_name)
    cls = catalog.classes.get(material.pdm_class_id)
    known = {a.name: a for a in cls.attributes} if cls else {}
    applicable = {a.name: _applies(a, known, attrs, material.item_name) for a in known.values()}
    return {
        "status": checked.status.value,
        "missing_required": [a.name for a in checked.missing_attributes],
        "invalid": [{"name": a.name, "reason": a.reason_code} for a in checked.invalid_attributes],
        "not_applicable": list(checked.not_applicable_attributes),
        "conditional_pending": [name for name, applies in applicable.items() if applies is None],
        "optional_missing": [
            a.name for a in known.values() if not a.required and applicable[a.name] is True and not attrs.get(a.name)
        ],
    }


def observation_conflicts(material, catalog):
    """Observações independentes não podem ser ocultadas pela precedência do extrator."""
    cls = catalog.classes.get(material.pdm_class_id)
    if cls is None:
        return {}
    extractor = get_extraction_repository()
    observed = defaultdict(set)
    from repositories.extraction.material_fields import extract_material_fields

    record = material.record
    fields = extract_material_fields(
        cls,
        record.description,
        record.short_description,
        manufacturer=record.manufacturer,
        reference=record.reference,
        extractor=extractor,
    )
    for name, values in fields.conflicts.items():
        observed[name].update(values)
    for name, value in material.attributes.items():
        observed[name].add(value)
    pieces = []
    # A curta já foi lida pelo helper com a proteção contra a cauda truncada.
    for segment in _SEGMENTS.split(_clean_text(_LINE_BREAK.sub(" ; ", record.description))):
        starts = sorted({0, *(start for start, _, _ in labeled_spans(observed, segment)), len(segment)})
        pieces.extend(segment[start:stop] for start, stop in zip(starts, starts[1:], strict=False))
    pieces += [f"FABRICANTE: {record.manufacturer}", f"REFERENCIA FABRICANTE: {record.reference}"]
    for piece in pieces:
        if not piece.strip():
            continue
        for name, attr in extractor.extract(cls, piece).attributes.items():
            observed[name].add(attr.value)

    def spelling(name, value):
        if name in {"REFERENCIA FABRICANTE", "REFERENCIA"}:
            return reference_spelling_key(value)
        return manufacturer_key(value) if name == "FABRICANTE" else value

    return {
        name: sorted(values)
        for name, values in observed.items()
        if len({spelling(name, value) for value in values}) > 1
    }


def internal_report(materials, sources, catalog, dataset_id, *, assistant=None):
    from pipelines.enrichment_diagnostics import diagnose

    index = defaultdict(list)
    unusable_sources = []
    for source in sources:
        if source.material.review_reasons:
            unusable_sources.append(
                {
                    "source": f"{source.filename}#{source.material.record.code}",
                    "reasons": list(source.material.review_reasons),
                    "conflicts": observation_conflicts(source.material, catalog),
                }
            )
        if source.material.identity_key and source.material.record.status == "ATIVO":
            index[source.material.identity_key].append(source)
    results, before_counts, after_counts, missing = [], Counter(), Counter(), Counter()
    source_ambiguities = {}
    for target in materials:
        evidence, rejected = [], []
        conflicts, candidates = defaultdict(set), defaultdict(set)
        before = completeness(target, catalog)
        cls = catalog.classes.get(target.pdm_class_id)
        record_conflicts = observation_conflicts(target, catalog)
        if cls and target.identity_key and target.record.status == "ATIVO" and not record_conflicts:
            for source in index.get(target.identity_key, []):
                donor = source.material
                if source.filename == "01_base_materiais.csv" and donor.record.code == target.record.code:
                    continue
                source_id = f"{source.filename}#{donor.record.code}"
                if source_id not in source_ambiguities:
                    source_ambiguities[source_id] = observation_conflicts(donor, catalog)
                if source_ambiguities[source_id]:
                    rejected.append(
                        {
                            "source": source_id,
                            "reasons": ["CONTRADICTORY_SOURCE_OBSERVATIONS"],
                            "conflicts": source_ambiguities[source_id],
                        }
                    )
                    continue
                identity = decide_identity(catalog, target, donor)
                differences, _ = compare_attributes(cls, target.attributes, donor.attributes)
                differences += [
                    a.name
                    for a in cls.attributes
                    if not a.required
                    and target.attributes.get(a.name)
                    and donor.attributes.get(a.name)
                    and target.attributes[a.name] != donor.attributes[a.name]
                ]
                if identity.status != "SAME_MATERIAL" or differences:
                    for name in differences:
                        conflicts[name].update((target.attributes[name], donor.attributes[name]))
                    rejected.append(
                        {"source": f"{source.filename}#{donor.record.code}", "reasons": list(identity.reasons)}
                    )
                    continue
                checked = validate_pdm(catalog, cls.id, donor.attributes, item_name=donor.item_name)
                if checked.invalid_attributes or checked.not_applicable_attributes:
                    continue
                for name, value in sorted(donor.attributes.items()):
                    if target.attributes.get(name):
                        continue
                    candidates[name].add(value)
                    url = f"dataset://{dataset_id}/{source.filename}#{donor.record.code}"
                    record = donor.record
                    excerpt = source_excerpt(record)
                    fact = {
                        "attribute": name,
                        "proposed_value": value,
                        "source_url": url,
                        "source_title": source.title or f"{source.filename} — {record.code}",
                        "source_excerpt": excerpt,
                        "source_sha256": source.sha256,
                        "object_key": source.object_key,
                        "source_page": None,
                        "confidence_level": "MEDIUM",
                        "confidence_basis": ["INTERNAL_DATASET", "SHARED_IDENTITY_CONFIRMED"],
                        "extraction_rule": "shared-extraction-and-identity",
                    }
                    evidence.append({"id": canonical_hash(fact), **fact})
        suggestions = {}
        for name, values in candidates.items():
            if len(values) > 1:
                conflicts[name].update(values)
            elif name not in conflicts:
                suggestions[name] = next(iter(values))
        after = completeness(target, catalog, target.attributes | suggestions)
        # Uma sugestão que cria atributo inaplicável ou inválido não entra na aprovação.
        if after["invalid"] or after["not_applicable"]:
            suggestions = {}
            after = before
        before_counts[before["status"]] += 1
        after_counts[after["status"]] += 1
        missing.update(f"{target.pdm_class_id}/{name}" for name in before["missing_required"])
        diagnosis = diagnose(target, catalog, before, after, record_conflicts, conflicts)
        assisted = None
        if assistant is not None and cls and not record_conflicts:
            missing_names = after["missing_required"] + after["optional_missing"]
            assisted = assistant.suggest(
                cls.id,
                missing_names,
                {
                    field: text
                    for field, text in {
                        "description": target.record.description,
                        "short_description": target.record.short_description,
                    }.items()
                    if text.strip()
                },
            )
        results.append(
            {
                "material_code": target.record.code,
                "pdm_class_id": target.pdm_class_id,
                "item_name": target.item_name,
                "original": {
                    "description": target.record.description,
                    "short_description": target.record.short_description,
                    "manufacturer": target.record.manufacturer,
                    "reference": target.record.reference,
                    "attributes": dict(target.attributes),
                },
                **diagnosis,
                "assisted_candidates": assisted["candidates"] if assisted else [],
                "assisted_extraction": assisted,
                "record_conflicts": record_conflicts,
                "before": before,
                "after_suggestions": after,
                "suggestions": suggestions,
                "conflicts": {n: sorted(v) for n, v in sorted(conflicts.items())},
                "rejected_sources": rejected,
                "evidence": sorted(evidence, key=lambda e: e["id"]),
            }
        )
    return {
        "pipeline_version": VERSION,
        "dataset_id": str(dataset_id),
        "pdm_version": catalog.version,
        "pdm_source_sha256": catalog.source_sha256,
        "summary": {
            "materials_total": len(results),
            "before": dict(before_counts),
            "after_suggestions": dict(after_counts),
            "sources_total": len(sources),
            "materials_with_suggestions": sum(bool(r["suggestions"]) for r in results),
            "suggested_attributes": sum(len(r["suggestions"]) for r in results),
            "materials_with_conflicts": sum(bool(r["conflicts"]) for r in results),
            "materials_with_source_conflicts": sum(bool(r["conflicts"]) for r in results),
            "materials_with_record_conflicts": sum(bool(r["record_conflicts"]) for r in results),
            "classification": dict(Counter(r["classification"]["status"] for r in results)),
            "gap_reasons": dict(Counter(g["reason"] for r in results for g in r["gaps"])),
            "missing_required_by_attribute": dict(missing.most_common()),
        },
        "results": results,
        "unusable_sources": unusable_sources,
        "assisted_usage": assistant.usage if assistant is not None else None,
    }


def report_kit(directory, *, supplemental_path=None, assistant=None):
    """Diagnóstico local reproduzível; não publica propostas nem consulta fontes externas."""
    from pathlib import Path

    from clients.storage import LocalObjectStore
    from domain.pdm_loader import load_pdm

    directory = Path(directory)
    catalog = load_pdm(directory / "03_padrao_cadastro_PDM.xlsx")
    files = [
        {"name": name, "object_key": name, "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()}
        for name in ("01_base_materiais.csv", "02_pedidos_cadastro.csv")
    ]
    sources, unavailable = read_sources(files, LocalObjectStore(directory), catalog)
    materials = [s.material for s in sources if s.filename == "01_base_materiais.csv"]
    if supplemental_path is not None:
        from enrichment.internal_documents import bundle_object_key, load_supplemental_sources

        content = Path(supplemental_path).read_bytes()
        sources += load_supplemental_sources(content, "kit", catalog, bundle_object_key(content, "kit"))
    return internal_report(materials, sources, catalog, "kit", assistant=assistant) | {
        "source_files": files,
        "unavailable_sources": unavailable,
    }
