"""Congela candidatos por atributo e mede revisões explícitas, sem publicar dados."""

from collections import defaultdict
from copy import deepcopy
from random import Random

from domain.evaluation import ratio, resolve_reviews, wilson95
from domain.proposals import canonical_hash

SCHEMA = "enrichment-review-packet-v1"
LABELS = {"SUPPORTED": True, "UNSUPPORTED": False, "INCONCLUSIVE": None}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo textual obrigatório: {field}")
    return value


def _case(code, class_id, attribute, value, kind, evidence, target):
    body = {
        "material_code": _text(code, "material_code"),
        "pdm_class_id": class_id,
        "attribute": _text(attribute, "attribute"),
        "value": _text(value, "value"),
        "kind": kind,
        "evidence": sorted(deepcopy(evidence), key=canonical_hash),
        "target": deepcopy(target),
    }
    body["id"] = canonical_hash(body)
    return {**body, "case_sha256": canonical_hash(body)}


def create_review_packet(report: dict, *, seed: int = 263, sample_size: int = 100) -> dict:
    """Amostra reprodutível de candidatos; os rótulos ficam em arquivo separado."""
    if type(seed) is not int or type(sample_size) is not int or sample_size < 1:
        raise ValueError("Seed deve ser inteiro e tamanho da amostra deve ser inteiro positivo")
    cases, seen_codes, seen_candidates = [], set(), set()
    for item in report["results"]:
        code = item["material_code"]
        if code in seen_codes:
            raise ValueError("Material repetido no relatório")
        seen_codes.add(code)
        for attribute, value in sorted(item.get("suggestions", {}).items()):
            evidence = [
                source
                for source in item.get("evidence", [])
                if source.get("attribute") == attribute and source.get("proposed_value") == value
            ]
            cases.append(
                _case(
                    code,
                    item.get("pdm_class_id"),
                    attribute,
                    value,
                    "INTERNAL_SUGGESTION",
                    evidence,
                    item.get("original", {}),
                )
            )
        for candidate in item.get("assisted_candidates", []):
            evidence = [
                {
                    "source_field": _text(candidate["source_field"], "source_field"),
                    "source_excerpt": _text(candidate["excerpt"], "excerpt"),
                }
            ]
            cases.append(
                _case(
                    code,
                    item.get("pdm_class_id"),
                    candidate["attribute"],
                    candidate["value"],
                    "ASSISTED_CANDIDATE",
                    evidence,
                    item.get("original", {}),
                )
            )
    for case in cases:
        key = (case["material_code"], case["attribute"], case["value"], case["kind"])
        if key in seen_candidates:
            raise ValueError("Candidato repetido no relatório")
        seen_candidates.add(key)
    ordered = sorted(cases, key=lambda case: case["id"])
    selected = Random(seed).sample(ordered, min(sample_size, len(ordered)))
    packet = {
        "schema_version": SCHEMA,
        "report_sha256": canonical_hash(report),
        "basis": {
            key: report.get(key) for key in ("dataset_id", "pipeline_version", "pdm_version", "pdm_source_sha256")
        },
        "authorizes_apply": False,
        "independent_review": False,
        "sampling": {
            "unit": "ATTRIBUTE_CANDIDATE",
            "method": "random.Random(seed).sample sobre IDs ordenados",
            "seed": seed,
            "requested_size": sample_size,
            "population_size": len(ordered),
            "frame": [{"id": case["id"], "case_sha256": case["case_sha256"]} for case in ordered],
            "selected_ids": [case["id"] for case in selected],
        },
        "cases": selected,
        "limitations": [
            "Amostra de candidatos do relatório congelado; não mede recuperação de atributos não propostos.",
            "Revisões são de desenvolvimento; aprovação operacional não comprova precisão independente.",
            "Preserve o checksum do pacote fora do arquivo para detectar sua substituição integral.",
        ],
    }
    return {**packet, "packet_sha256": canonical_hash(packet)}


def _validate_packet(packet):
    body = {key: value for key, value in packet.items() if key != "packet_sha256"}
    if packet.get("schema_version") != SCHEMA or packet.get("packet_sha256") != canonical_hash(body):
        raise ValueError("Pacote alterado ou versão incompatível")
    sampling, cases = packet["sampling"], packet["cases"]
    frame = sampling["frame"]
    ids = [case["id"] for case in frame]
    if (
        type(sampling["seed"]) is not int
        or type(sampling["requested_size"]) is not int
        or sampling["requested_size"] < 1
        or ids != sorted(set(ids))
        or sampling["population_size"] != len(frame)
        or packet["authorizes_apply"] is not False
        or packet["independent_review"] is not False
    ):
        raise ValueError("Pacote com amostragem inválida")
    selected = Random(sampling["seed"]).sample(ids, min(sampling["requested_size"], len(ids)))
    if sampling["selected_ids"] != selected or [case["id"] for case in cases] != selected:
        raise ValueError("Pacote com seleção alterada")
    hashes = {entry["id"]: entry["case_sha256"] for entry in frame}
    for case in cases:
        body = {key: value for key, value in case.items() if key != "case_sha256"}
        original = {key: value for key, value in body.items() if key != "id"}
        if (
            case["case_sha256"] != canonical_hash(body)
            or case["case_sha256"] != hashes[case["id"]]
            or case["id"] != canonical_hash(original)
        ):
            raise ValueError("Caso alterado ou incompatível com o frame congelado")


def _metrics(cases):
    supported = sum(case["expected"] is True for case in cases)
    unsupported = sum(case["expected"] is False for case in cases)
    reviewed = sum(bool(case["reviews"]) for case in cases)
    return {
        "counts": {
            "selected": len(cases),
            "reviewed": reviewed,
            "supported": supported,
            "unsupported": unsupported,
            "inconclusive": len(cases) - supported - unsupported,
        },
        "review_coverage": ratio(reviewed, len(cases)),
        "decided_precision": ratio(supported, supported + unsupported),
        "decided_precision_interval": wilson95(supported, supported + unsupported),
    }


def evaluate_packet(packet: dict, reviews: dict) -> dict:
    """Sem revisão ou com desacordo, o candidato permanece inconclusivo."""
    _validate_packet(packet)
    if set(reviews) != {"packet_sha256", "reviews"} or reviews["packet_sha256"] != packet["packet_sha256"]:
        raise ValueError("Revisões não correspondem ao pacote congelado")
    if not isinstance(reviews["reviews"], list):
        raise ValueError("Revisões devem ser uma lista")
    known = {case["id"] for case in packet["cases"]}
    grouped = defaultdict(list)
    for review in reviews["reviews"]:
        if (
            not isinstance(review, dict)
            or set(review) != {"case_id", "author", "label", "evidence"}
            or not isinstance(review["case_id"], str)
            or review["case_id"] not in known
            or not isinstance(review["label"], str)
            or review["label"] not in LABELS
        ):
            raise ValueError("Revisão fora da amostra ou com rótulo inválido")
        grouped[review["case_id"]].append(deepcopy(review))
    cases = []
    for case in packet["cases"]:
        candidate_reviews = grouped[case["id"]]
        expected, status = resolve_reviews(
            [
                {"author": review["author"], "label": LABELS[review["label"]], "evidence": review["evidence"]}
                for review in candidate_reviews
            ]
        )
        cases.append({**deepcopy(case), "expected": expected, "status": status, "reviews": candidate_reviews})
    groups = {}
    for key, name in (("pdm_class_id", "by_class"), ("attribute", "by_attribute"), ("kind", "by_kind")):
        members = defaultdict(list)
        for case in cases:
            members[str(case[key])].append(case)
        groups[name] = {value: _metrics(rows) for value, rows in sorted(members.items())}
    return {
        "schema_version": "enrichment-evaluation-v1",
        "packet_sha256": packet["packet_sha256"],
        "reviews_sha256": canonical_hash(reviews),
        "report_sha256": packet["report_sha256"],
        "authorizes_apply": False,
        "independent_review": False,
        "population_size": packet["sampling"]["population_size"],
        "sampling_coverage": ratio(len(cases), packet["sampling"]["population_size"]),
        **_metrics(cases),
        **groups,
        "cases": cases,
        "limitations": [
            "Precisão condicional somente nos candidatos decididos desta amostra de desenvolvimento.",
            "Wilson usa hipótese binomial; atributos do mesmo material podem ser correlacionados.",
            "Rótulos ausentes, inconclusivos ou divergentes não confirmam suporte; não há recall da população.",
            "O resultado não autoriza aplicar atributos nem fazer merge.",
        ],
    }
