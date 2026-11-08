"""Contratos do dominio compartilhados por batch e MCP."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class FieldStatus(StrEnum):
    CANONICAL = "CANONICAL"  # ja estava no padrao
    NORMALIZED = "NORMALIZED"  # corrigido por uma regra
    MISSING = "MISSING"  # campo vazio
    UNRESOLVED = "UNRESOLVED"  # exige revisao: nenhuma regra segura se aplica


@dataclass(frozen=True)
class NormalizedField:
    """Valor normalizado, sempre com o original e a regra aplicada (Arquitetura, Fluxo 1)."""

    original: str
    value: str | None
    status: FieldStatus
    rule: str


class NormalizationRepository(Protocol):
    """Um algoritmo de pre-processamento. Para testar outro, crie um novo repositorio
    em repositories/normalization e registre-o; os existentes permanecem no codigo."""

    name: str

    def normalize_ncm(self, raw: str | None) -> NormalizedField: ...

    def normalize_unit(self, raw: str | None) -> NormalizedField: ...

    def normalize_text(self, raw: str | None) -> NormalizedField: ...


class ConditionOperator(StrEnum):
    ALWAYS = "ALWAYS"
    EQUALS = "EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"


# Sujeito de condicoes que dependem do nome do item (ex.: FLANGE), nao de um atributo.
ITEM_NAME_SUBJECT = "SUBSTANTIVO"


@dataclass(frozen=True)
class Condition:
    """Condicao controlada: nunca uma expressao livre vinda do arquivo."""

    operator: ConditionOperator = ConditionOperator.ALWAYS
    subject: str | None = None
    values: tuple[str, ...] = ()


class IdentityMode(StrEnum):
    TECHNICAL_ATTRIBUTES = "TECHNICAL_ATTRIBUTES"
    MANUFACTURER_REFERENCE = "MANUFACTURER_REFERENCE"


@dataclass(frozen=True)
class PdmAttribute:
    name: str
    order: int
    required: bool
    applies_when: Condition
    format: str
    allowed_values: tuple[str, ...] | None


@dataclass(frozen=True)
class NcmReference:
    codes: tuple[str, ...]
    rule: str


@dataclass(frozen=True)
class PdmClass:
    id: str
    noun: str | None  # None quando o nome vem de uma aba de substantivos
    qualifiers: tuple[str, ...]
    item_names: tuple[str, ...]
    group: str
    default_unit: str
    identity_mode: IdentityMode
    attributes: tuple[PdmAttribute, ...]
    ncm_references: tuple[NcmReference, ...]


@dataclass(frozen=True)
class PdmCatalog:
    version: str
    source_sha256: str
    classes: dict[str, PdmClass]


class ValidationStatus(StrEnum):
    VALID = "VALID"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class MissingAttribute:
    name: str
    reason_code: str
    question: str


@dataclass(frozen=True)
class InvalidAttribute:
    name: str
    reason_code: str
    value: str | None
    expected: str | None = None


@dataclass(frozen=True)
class PdmValidationResult:
    status: ValidationStatus
    missing_attributes: tuple[MissingAttribute, ...] = ()
    invalid_attributes: tuple[InvalidAttribute, ...] = ()
    not_applicable_attributes: tuple[str, ...] = ()
    formatted_description: str | None = None
    identity_key: str | None = None
    can_submit: bool = False


class ClassificationStatus(StrEnum):
    CLASSIFIED = "CLASSIFIED"
    UNRESOLVED = "UNRESOLVED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class ClassificationInput:
    """Textos originais, tanto do cadastro legado quanto de um pedido."""

    description: str | None
    short_description: str | None = None
    merchandise_group: str | None = None
    attachment_text: str | None = None


@dataclass(frozen=True)
class ClassificationEvidence:
    class_id: str
    source_field: str
    matched_name: str
    rule: str


@dataclass(frozen=True)
class ClassificationResult:
    original: ClassificationInput
    status: ClassificationStatus
    pdm_class_id: str | None
    candidate_class_ids: tuple[str, ...]
    evidence: tuple[ClassificationEvidence, ...]
    rule: str
    pdm_version: str
    pdm_source_sha256: str


class ClassificationRepository(Protocol):
    """Classificacao substituivel; o resultado nao altera o cadastro mestre."""

    name: str
    # Mude ao alterar regras ou tabelas: a revisão entra na versão do índice de busca.
    revision: str

    def classify(self, item: ClassificationInput) -> ClassificationResult: ...


@dataclass(frozen=True)
class ExtractedAttribute:
    """Valor no padrão do PDM, sempre com o texto de origem e a regra aplicada."""

    value: str
    original: str
    rule: str


@dataclass(frozen=True)
class ExtractionResult:
    attributes: dict[str, ExtractedAttribute]
    unresolved: tuple[str, ...] = ()  # trechos que nenhuma regra segura interpretou


class ExtractionRepository(Protocol):
    """Um algoritmo de extração. Para testar outro, crie um novo repositório em
    repositories/extraction e registre-o; os existentes permanecem no código."""

    name: str
    # Mude ao alterar regras ou tabelas: a revisão entra na versão do índice de busca.
    revision: str

    def extract(
        self,
        pdm_class: PdmClass,
        description: str,
        *,
        manufacturer: str | None = None,
        manufacturer_reference: str | None = None,
    ) -> ExtractionResult: ...


@dataclass(frozen=True)
class MaterialRecord:
    """Material como está no cadastro, antes de qualquer correção."""

    code: str
    status: str
    description: str
    short_description: str = ""
    group: str = ""
    manufacturer: str = ""
    reference: str = ""
    unit: str = ""
    ncm: str = ""
    version: int = 1
    total_value: str = "0"
    inventory: tuple[dict, ...] = ()
    database_id: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyzedMaterial:
    record: MaterialRecord
    pdm_class_id: str | None
    item_name: str | None
    attributes: dict[str, str]
    identity_key: str | None
    review_reasons: tuple[str, ...] = ()
    # Regra que decidiu a classe; `*/head.name` indica o nome do PDM no começo da descrição.
    classification_rule: str | None = None


class MatchType(StrEnum):
    EXACT_IDENTITY = "EXACT_IDENTITY"
    COMPATIBLE_ATTRIBUTES = "COMPATIBLE_ATTRIBUTES"


@dataclass(frozen=True)
class CandidateGroup:
    """Materiais que podem ser o mesmo item. Só `identity_verified` satisfaz a regra do PDM."""

    codes: tuple[str, ...]
    match_type: MatchType
    identity_verified: bool
    score: float


class CandidateRepository(Protocol):
    """Um algoritmo de geração de candidatos. Para testar outro, crie um novo repositório em
    repositories/candidates e registre-o; os existentes permanecem no código."""

    name: str

    def find(self, materials: list[AnalyzedMaterial], catalog: PdmCatalog) -> list[CandidateGroup]: ...


@dataclass(frozen=True)
class MergeProposal:
    id: str
    proposal_type: str
    material_codes: tuple[str, ...]
    suggested_primary_code: str
    members: tuple[dict, ...]
    changeset: dict
    changeset_hash: str
    conflicts: tuple[str, ...]
    fiscal_review_required: bool
    ranking_score: float


@dataclass(frozen=True)
class FieldCorrection:
    """Mudança proposta em um campo do cadastro, sempre com o valor original e a regra aplicada."""

    proposal_type: str  # PDM_CORRECTION ou UNIT_CORRECTION
    field: str  # description, merchandise_group ou unit
    before: str | None
    after: str
    rule: str


@dataclass(frozen=True)
class CorrectionResult:
    corrections: tuple[FieldCorrection, ...]
    # Motivos para não corrigir automaticamente, no formato `CODIGO: detalhe`. Ficam para revisão.
    pending: tuple[str, ...] = ()


class CorrectionRepository(Protocol):
    """Decide o que corrigir em um material já analisado. Nada é aplicado: o resultado vira proposta."""

    name: str

    def correct(
        self, material: AnalyzedMaterial, catalog: PdmCatalog, normalizer: NormalizationRepository
    ) -> CorrectionResult: ...


@dataclass(frozen=True)
class ReviewLane:
    """Como uma correção é revisada: 1 e 2 podem ir em lote após amostra, 3 é sempre item a item.

    `lot_key` é tipo|regra|classe. `reasons` traz os códigos que mandaram a proposta ao nível 3.
    """

    tier: int
    lot_key: str
    reasons: tuple[str, ...] = ()


class TextLossRepository(Protocol):
    """Diz quais termos da descrição original não chegaram à descrição proposta.

    Na dúvida, aponta perda: o custo é revisar a proposta item a item, nunca aplicar texto errado.
    """

    name: str

    def lost_terms(self, material: AnalyzedMaterial, pdm_class: PdmClass, proposed: str) -> tuple[str, ...]: ...


class EmbeddingRepository(Protocol):
    """Um modelo de embeddings. `signature` identifica modelo, dimensão e versão: indexação e consulta
    só se comparam com a mesma assinatura. Para testar outro, registre um novo repositório."""

    name: str
    model: str
    dimensions: int
    simulated: bool

    @property
    def signature(self) -> str: ...

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]: ...


@dataclass(frozen=True)
class EnrichmentClaim:
    """Valor extraído, com trecho literal e página para conferir a evidência."""

    attribute: str
    value: str
    excerpt: str
    page: int | None = None


class EnrichmentRepository(Protocol):
    """Extração externa substituível; não busca URLs, aprova nem escreve no cadastro."""

    name: str

    def extract(
        self, pdm_class: PdmClass, manufacturer: str, reference: str, pages: tuple[str, ...]
    ) -> tuple[EnrichmentClaim, ...]: ...


@dataclass(frozen=True)
class LlmCall:
    """Registro de uma chamada de modelo: o que rodou e quanto custou, sem prompt nem segredos."""

    repository: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempts: int
    simulated: bool


@dataclass(frozen=True)
class LlmResult:
    """Resposta estruturada já validada pelo esquema pedido."""

    data: dict
    call: LlmCall


class LlmRepository(Protocol):
    """Modelo de linguagem substituível. Só devolve dados que passaram no esquema; resposta inválida,
    recusa, erro ou orçamento esgotado viram `LlmError`, nunca um sucesso fictício."""

    name: str
    model: str
    simulated: bool

    def complete(self, *, system: str, prompt: str, schema: dict, tool_name: str, prompt_version: str) -> LlmResult: ...


@dataclass(frozen=True)
class RagScope:
    tenant_id: str
    center_codes: frozenset[str]


@dataclass(frozen=True)
class RagMaterial:
    """Projeção sem campos financeiros; cadastro aprovado e inferência permanecem distintos."""

    tenant_id: str
    center_codes: frozenset[str]
    code: str
    version: int
    description: str
    pdm_class_id: str | None
    attributes: dict[str, str]
    ncm: str | None
    technical_source: str
    ncm_approved: bool
    score: float


class RagCandidateSource(Protocol):
    """Adaptador persistente autorizado; aplica escopo e versão antes de ranking/limite."""

    version: str

    def retrieve(
        self,
        query: str,
        class_id: str | None,
        scope: RagScope,
        limit: int,
        *,
        vector: list[float] | None,
        require_embedding: bool,
    ) -> list[RagMaterial]: ...


class RagMaterialRepository(Protocol):
    """Algoritmo de recuperação substituível; não autoriza cadastro, identidade nem NCM."""

    name: str
    version: str
    retrieval: str

    def retrieve(self, query: str, class_id: str | None, scope: RagScope, limit: int) -> list[RagMaterial]: ...
