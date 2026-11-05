"""Contratos do dominio compartilhados por batch e MCP."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class AnalyzedMaterial:
    record: MaterialRecord
    pdm_class_id: str | None
    item_name: str | None
    attributes: dict[str, str]
    identity_key: str | None


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
