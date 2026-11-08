"""Auditor LLM no fim do saneamento (#290): só os casos de NCM que as regras não resolvem.

O modelo lê a descrição e um trecho do PDM e devolve evidências: classe, atributos com trechos
citados e o NCM que entende correto, ou se abstém. Ele nunca decide sozinho. O motor de domínio
confere cada trecho no texto original, aceita só valores admitidos pelo PDM, recalcula o código com
as mesmas regras do batch e descarta, com o motivo, o que não fecha. O que sobra vira uma proposta
`NCM_CORRECTION` com origem `LLM_AUDITOR`, sempre com revisão técnica e fiscal.

O auditor não recebe o NCM atual nem gabarito, não aplica nada e não entra em lote nem em correção
automática. Sem resposta, com erro ou com o orçamento esgotado, o caso continua pendente.
"""

import hashlib
import json
import re
import unicodedata
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field, replace

from domain.contracts import AnalyzedMaterial, FieldCorrection, LlmCall, LlmRepository, MergeProposal, PdmCatalog
from domain.llm import LlmError
from domain.ncm_rules import RULES_VERSION, check_ncm_consistency, ncm_proposal_blockers
from domain.ncm_scoring import NcmScorer, NcmScorerError, confidence
from domain.ncm_snapshot import NcmSnapshot
from domain.proposals import canonical_hash
from pipelines.corrections import build_correction_proposal
from repositories.corrections.head_noun_v2 import head_confirmed

ORIGIN = "LLM_AUDITOR"
PROMPT_VERSION = "llm-audit-v1"
POLICY_VERSION = "llm-audit-policy-v1"
TOOL_NAME = "registrar_auditoria_ncm"
MAX_CANDIDATE_CLASSES = 6
MAX_ALLOWED_VALUES = 60
MAX_ITEM_NAMES = 40

# Motivos de seleção: por que as regras não propuseram um NCM.
NO_CLASS = "NO_CLASS"
HEAD_UNCONFIRMED = "HEAD_UNCONFIRMED"
NCM_CODE_UNRESOLVED = "NCM_CODE_UNRESOLVED"

# Resultado de cada caso.
PROPOSED, CONFIRMED, ABSTAINED, DISCARDED, FAILED, SKIPPED = (
    "PROPOSED",
    "CONFIRMED",
    "ABSTAINED",
    "DISCARDED",
    "FAILED",
    "SKIPPED",
)

_NAMESPACE = uuid.UUID("5b0f8d0e-4a8f-4a4c-9a7e-2f3c1d290290")
_WORD = re.compile(r"[A-Z0-9]+")

SYSTEM_PROMPT = """Você é um auditor técnico-fiscal de cadastro de materiais industriais no Brasil.
Recebe a descrição de um material e trechos do padrão de cadastro (PDM): classes candidatas, atributos
com valores admitidos e as referências de NCM de cada classe com a regra de uso.

Regras:
- Use só o que está escrito na descrição e no PDM recebido. Não invente fabricante, medida ou material.
- Cada atributo informado precisa de um trecho copiado literalmente da descrição (`trecho`).
  Use `base` = "LITERAL" quando o valor está escrito no trecho e "INFERIDO" quando é dedução técnica
  a partir do trecho (por exemplo, a matéria de uma peça). Valores precisam estar entre os admitidos.
- O NCM precisa ser um dos códigos listados nas referências da classe escolhida, seguindo a regra.
- Na dúvida, responda `decisao` = "ABSTER" e explique o que falta. Abster-se é melhor que errar:
  o resultado sempre passa por revisão humana técnica e fiscal.
- `justificativa` é curta, em português, e cita os trechos usados."""

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    # ABSTER primeiro: o modelo simulado devolve a menor resposta válida, que é abster-se.
    "required": ["decisao", "justificativa"],
    "properties": {
        "decisao": {"enum": ["ABSTER", "RESOLVER"]},
        "classe_pdm": {"type": ["string", "null"]},
        "nome_item": {"type": ["string", "null"]},
        "atributos": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nome", "valor", "trecho", "base"],
                "properties": {
                    "nome": {"type": "string"},
                    "valor": {"type": "string"},
                    "trecho": {"type": "string", "minLength": 1},
                    "base": {"enum": ["LITERAL", "INFERIDO"]},
                },
            },
        },
        "ncm": {"type": ["string", "null"]},
        "evidencias": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1}},
        "justificativa": {"type": "string", "maxLength": 800},
    },
}


@dataclass(frozen=True)
class AuditCase:
    material: AnalyzedMaterial
    reasons: tuple[str, ...]
    candidate_classes: tuple[str, ...]


@dataclass(frozen=True)
class AuditOutcome:
    material_code: str
    reasons: tuple[str, ...]
    status: str
    detail: tuple[str, ...] = ()
    proposal: MergeProposal | None = None
    call: LlmCall | None = None
    suggested_ncm: str | None = field(default=None, compare=False)


def fold(text: str | None) -> str:
    """Caixa alta, sem acentos e com espaços simples: a mesma grafia para conferir trechos."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).upper().split())


def _digits(code: str | None) -> str:
    return "".join(ch for ch in code or "" if ch.isdigit())


def _first_word(text: str) -> str:
    words = _WORD.findall(fold(text))
    return words[0] if words else ""


def candidate_classes(material: AnalyzedMaterial, catalog: PdmCatalog) -> tuple[str, ...]:
    """Classes cujo nome começa como a descrição: a palavra inicial, inteira ou abreviada.

    Sem classe candidata não há o que auditar, e o caso não gasta chamada.
    """
    word = _first_word(material.record.description) or _first_word(material.record.short_description)
    found = [material.pdm_class_id] if material.pdm_class_id else []
    if len(word) >= 3:
        for cls in sorted(catalog.classes.values(), key=lambda c: c.id):
            heads = {_first_word(name) for name in cls.item_names}
            if any(head.startswith(word) or (len(head) >= 4 and word.startswith(head)) for head in heads):
                found.append(cls.id)
    return tuple(dict.fromkeys(found))[:MAX_CANDIDATE_CLASSES]


def _rule_reasons(material: AnalyzedMaterial, catalog: PdmCatalog) -> tuple[str, ...]:
    if material.pdm_class_id is None:
        return (NO_CLASS,)
    if not head_confirmed(material):
        return (HEAD_UNCONFIRMED,)
    cls = catalog.classes[material.pdm_class_id]
    blockers = ncm_proposal_blockers(cls, material.attributes, material.item_name)
    if blockers:
        codes = {_digits(code) for ref in cls.ncm_references for code in ref.codes}
        # Código único já igual ao atual: o auditor só confirmaria, sem mudança a propor.
        if len(codes) == 1 and _digits(material.record.ncm) in codes:
            return ()
        return blockers
    result = check_ncm_consistency(
        catalog, cls.id, material.attributes, material.record.ncm or None, item_name=material.item_name
    )
    if len(result.suggested_ncm_codes) != 1 or "PDM_CONDITION_UNRESOLVED" in result.pending_checks:
        return (NCM_CODE_UNRESOLVED,)
    return ()


def select_audit_cases(
    materials: list[AnalyzedMaterial], catalog: PdmCatalog, proposed_codes: set[str]
) -> list[AuditCase]:
    """Casos sem proposta de NCM das regras, com o motivo da regra que não resolveu."""
    cases = []
    for material in materials:
        if material.record.code in proposed_codes:
            continue
        reasons = _rule_reasons(material, catalog)
        if reasons:
            cases.append(AuditCase(material, reasons, candidate_classes(material, catalog)))
    return cases


def _class_excerpt(catalog: PdmCatalog, class_id: str, word: str) -> dict:
    cls = catalog.classes[class_id]
    names = list(cls.item_names)
    if len(names) > MAX_ITEM_NAMES:
        names = [n for n in names if _first_word(n).startswith(word[:4])][:MAX_ITEM_NAMES] or names[:MAX_ITEM_NAMES]
    return {
        "classe_pdm": cls.id,
        "nomes_item": names,
        "atributos": [
            {
                "nome": a.name,
                "obrigatorio": a.required,
                "valores_admitidos": list(a.allowed_values[:MAX_ALLOWED_VALUES]) if a.allowed_values else None,
            }
            for a in cls.attributes
        ],
        "referencias_ncm": [{"codigos": list(ref.codes), "regra": ref.rule} for ref in cls.ncm_references],
    }


def build_prompt(case: AuditCase, catalog: PdmCatalog) -> str:
    """Entrada do modelo: descrição, motivo e PDM. Nunca o NCM atual nem gabarito."""
    material, record = case.material, case.material.record
    word = _first_word(record.description)
    payload = {
        "material": {
            "descricao_longa": record.description,
            "descricao_curta": record.short_description or None,
            "fabricante": record.manufacturer or None,
            "referencia_fabricante": record.reference or None,
            "unidade": record.unit or None,
        },
        "motivo_pendencia": list(case.reasons),
        "leitura_das_regras": {
            "classe_pdm": material.pdm_class_id,
            "nome_item": material.item_name,
            "atributos": dict(sorted(material.attributes.items())),
        },
        "classes_candidatas": [_class_excerpt(catalog, class_id, word) for class_id in case.candidate_classes],
    }
    return "Audite o NCM deste material e registre o resultado com a ferramenta.\n\n" + json.dumps(
        payload, ensure_ascii=False, indent=1
    )


def revalidate(
    case: AuditCase, data: dict, catalog: PdmCatalog, snapshot: NcmSnapshot | None
) -> tuple[str, tuple[str, ...], AnalyzedMaterial | None, str | None, object]:
    """Confere a resposta com o domínio. Devolve status, motivos, material revisto, código e avaliação."""
    if data["decisao"] != "RESOLVER":
        return ABSTAINED, (), None, None, None
    material, record = case.material, case.material.record
    text = fold(" ".join(filter(None, (record.description, record.short_description))))
    class_id = data.get("classe_pdm") or material.pdm_class_id
    if class_id not in case.candidate_classes:
        return DISCARDED, ("LLM_CLASS_NOT_CANDIDATE",), None, None, None
    cls = catalog.classes[class_id]
    item_name = data.get("nome_item") or (material.item_name if class_id == material.pdm_class_id else None)
    if item_name is None or fold(item_name) not in {fold(n) for n in cls.item_names}:
        return DISCARDED, ("LLM_ITEM_NAME_INVALID",), None, None, None
    item_name = next(n for n in cls.item_names if fold(n) == fold(item_name))
    reasons: list[str] = []
    for quote in data.get("evidencias", []):
        if fold(quote) not in text:
            reasons.append("LLM_QUOTE_NOT_FOUND")
    # Atributos das regras valem só na mesma classe; o modelo nunca sobrescreve um valor extraído.
    attributes = dict(material.attributes) if class_id == material.pdm_class_id else {}
    known = {a.name: a for a in cls.attributes}
    for entry in data.get("atributos", []):
        name, value = fold(entry["nome"]), fold(entry["valor"])
        definition = known.get(name)
        if fold(entry["trecho"]) not in text:
            reasons.append("LLM_QUOTE_NOT_FOUND")
        elif definition is None:
            reasons.append("LLM_ATTRIBUTE_UNKNOWN")
        elif definition.allowed_values and value not in definition.allowed_values:
            reasons.append("LLM_ATTRIBUTE_NOT_ADMITTED")
        elif attributes.get(name) not in (None, value):
            reasons.append("LLM_ATTRIBUTE_CONFLICT")
        elif entry["base"] == "LITERAL" and not set(_WORD.findall(value)) <= set(_WORD.findall(fold(entry["trecho"]))):
            reasons.append("LLM_LITERAL_VALUE_NOT_IN_QUOTE")
        else:
            attributes[name] = value
    if reasons:
        return DISCARDED, tuple(dict.fromkeys(reasons)), None, None, None
    blockers = ncm_proposal_blockers(cls, attributes, item_name)
    # A função de anel/vedação de sobressalente é o que se pede ao auditor; a matéria não.
    blockers = tuple(b for b in blockers if b != "NCM_SEAL_FUNCTION_UNRESOLVED" or not data.get("evidencias"))
    if blockers:
        return DISCARDED, blockers, None, None, None
    suggested = _digits(data.get("ncm"))
    references = {_digits(code) for ref in cls.ncm_references for code in ref.codes}
    if suggested and suggested not in references:
        return DISCARDED, ("NCM_OUTSIDE_PDM_REFERENCE",), None, None, None
    before = check_ncm_consistency(
        catalog, class_id, attributes, record.ncm or None, item_name=item_name, snapshot=snapshot
    )
    if len(before.suggested_ncm_codes) != 1 or "PDM_CONDITION_UNRESOLVED" in before.pending_checks:
        return DISCARDED, ("NCM_UNRESOLVED_BY_DOMAIN",), None, None, None
    target = before.suggested_ncm_codes[0]
    if not suggested or suggested != _digits(target):
        return DISCARDED, ("NCM_DIFFERS_FROM_DOMAIN",), None, None, None
    revised = replace(material, pdm_class_id=class_id, item_name=item_name, attributes=attributes)
    if _digits(record.ncm) == _digits(target):
        return CONFIRMED, (), revised, target, before
    after = check_ncm_consistency(catalog, class_id, attributes, target, item_name=item_name, snapshot=snapshot)
    if after.technical_consistency != "CONSISTENT":
        return DISCARDED, ("NCM_INCONSISTENT_AFTER",), None, None, None
    return PROPOSED, (), revised, target, (before, after)


def _proposal(
    case: AuditCase,
    revised: AnalyzedMaterial,
    target: str,
    assessments,
    data: dict,
    call: LlmCall,
    prompt: str,
    catalog: PdmCatalog,
    confidence_record: dict,
) -> MergeProposal:
    before, after = assessments
    record = revised.record
    source = f"{ORIGIN}/{POLICY_VERSION}; {PROMPT_VERSION}; {call.model}; {RULES_VERSION}/{before.rule_id}"
    proposal = build_correction_proposal(
        revised,
        "NCM_CORRECTION",
        [FieldCorrection("NCM_CORRECTION", "ncm", record.ncm or None, target, source)],
        (),
        catalog,
        RULES_VERSION,
    )
    inferred = [a for a in data.get("atributos", []) if a["base"] == "INFERIDO"]
    changes = {
        **proposal.changeset,
        "origin": ORIGIN,
        "after": {**proposal.changeset["after"], "ncm": target},
        "ncm_before_assessment": asdict(before),
        "ncm_assessment": asdict(after),
        "llm_audit": {
            "policy_version": POLICY_VERSION,
            "prompt_version": PROMPT_VERSION,
            "call": asdict(call),
            "simulated": call.simulated,
            "selection_reasons": list(case.reasons),
            "class_source": "RULES" if revised.pdm_class_id == case.material.pdm_class_id else "LLM",
            "rules_reading": {
                "pdm_class_id": case.material.pdm_class_id,
                "item_name": case.material.item_name,
                "attributes": case.material.attributes,
            },
            "attributes": data.get("atributos", []),
            "inferred_attributes": [a["nome"] for a in inferred],
            "evidence": data.get("evidencias", []),
            "rationale": data["justificativa"],
            "context": {
                "candidate_classes": list(case.candidate_classes),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            },
            # Ordena a revisão; nunca aprova, aplica nem coloca a sugestão em lote.
            "confidence": confidence_record,
        },
    }
    return replace(
        proposal,
        # Id próprio: nunca colide com a proposta das regras para o mesmo material.
        id=str(uuid.uuid5(_NAMESPACE, f"{catalog.version}|NCM_CORRECTION|{ORIGIN}|{record.code}")),
        changeset=changes,
        changeset_hash=canonical_hash(changes),
        fiscal_review_required=True,
    )


def score_confidence(class_id: str, target: str, prompt: str, catalog: PdmCatalog, scorer: NcmScorer | None):
    """Pontua o código sugerido entre todos os códigos de referência da classe no PDM."""
    candidates = tuple(sorted({code for ref in catalog.classes[class_id].ncm_references for code in ref.codes}))
    if scorer is None:
        return confidence(target, candidates, None)
    try:
        return confidence(target, candidates, scorer.score(prompt, candidates))
    except NcmScorerError as error:
        return confidence(target, candidates, None, error.code)


def audit_cases(
    cases: list[AuditCase],
    catalog: PdmCatalog,
    llm: LlmRepository,
    *,
    snapshot: NcmSnapshot | None = None,
    scorer: NcmScorer | None = None,
) -> list[AuditOutcome]:
    outcomes = []
    for case in cases:
        code = case.material.record.code
        if not case.candidate_classes:
            outcomes.append(AuditOutcome(code, case.reasons, SKIPPED, ("NO_CANDIDATE_CLASS",)))
            continue
        prompt = build_prompt(case, catalog)
        try:
            result = llm.complete(
                system=SYSTEM_PROMPT,
                prompt=prompt,
                schema=RESPONSE_SCHEMA,
                tool_name=TOOL_NAME,
                prompt_version=PROMPT_VERSION,
            )
        except LlmError as error:
            outcomes.append(AuditOutcome(code, case.reasons, FAILED, (error.code,)))
            continue
        status, detail, revised, target, assessments = revalidate(case, result.data, catalog, snapshot)
        proposal = None
        if status == PROPOSED:
            # Só a sugestão que passou pela validação do domínio é pontuada.
            record = score_confidence(revised.pdm_class_id, target, prompt, catalog, scorer)
            proposal = _proposal(case, revised, target, assessments, result.data, result.call, prompt, catalog, record)
        outcomes.append(
            AuditOutcome(code, case.reasons, status, detail, proposal, result.call, _digits(result.data.get("ncm")))
        )
    return outcomes


def _count(values) -> dict:
    return dict(sorted(Counter(values).items()))


def summarize_audit(outcomes: list[AuditOutcome]) -> dict:
    calls = [o.call for o in outcomes if o.call is not None]
    return {
        "policy_version": POLICY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "cases": len(outcomes),
        "by_status": _count(o.status for o in outcomes),
        "by_selection_reason": _count(r for o in outcomes for r in o.reasons),
        "discard_reasons": _count(d for o in outcomes if o.status == DISCARDED for d in o.detail),
        "failures": _count(d for o in outcomes if o.status == FAILED for d in o.detail),
        "usage": {
            "calls": len(calls),
            "attempts": sum(c.attempts for c in calls),
            "input_tokens": sum(c.input_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "models": sorted({c.model for c in calls}),
            "simulated": any(c.simulated for c in calls),
        },
    }


def audit_pending_ncm(
    materials: list[AnalyzedMaterial],
    catalog: PdmCatalog,
    ncm_proposals: list[MergeProposal],
    llm: LlmRepository | None,
    *,
    snapshot: NcmSnapshot | None = None,
    scorer: NcmScorer | None = None,
) -> tuple[list[MergeProposal], dict | None]:
    """Etapa opcional do batch: sem modelo configurado, não faz nada e não chama ninguém."""
    if llm is None:
        return [], None
    proposed = {p.suggested_primary_code for p in ncm_proposals}
    outcomes = audit_cases(
        select_audit_cases(materials, catalog, proposed), catalog, llm, snapshot=snapshot, scorer=scorer
    )
    return [o.proposal for o in outcomes if o.proposal is not None], summarize_audit(outcomes)
