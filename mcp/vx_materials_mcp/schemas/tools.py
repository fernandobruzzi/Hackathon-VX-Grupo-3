"""Contratos das tools (seção 3 da arquitetura)."""

from pydantic import BaseModel, ConfigDict


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppliesWhen(_Contract):
    operator: str
    subject: str | None = None
    values: list[str] | None = None


class TemplateAttribute(_Contract):
    name: str
    order: int
    required: bool
    applies_when: AppliesWhen
    format: str
    allowed_values: list[str] | None


class NcmReferenceItem(_Contract):
    codes: list[str]
    rule: str


class PdmTemplate(_Contract):
    pdm_class_id: str
    pdm_version: str
    noun: str | None
    qualifier: str | None
    # Nomes aceitos em `item_name`. Classes como conexões e filtros têm vários.
    item_names: list[str]
    identity_mode: str
    default_unit: str
    attributes: list[TemplateAttribute]
    ncm_references: list[NcmReferenceItem]


class MissingAttributeItem(_Contract):
    name: str
    reason_code: str
    question: str


class InvalidAttributeItem(_Contract):
    name: str
    reason_code: str
    value: str | None
    expected: str | None


class PdmValidation(_Contract):
    status: str
    missing_attributes: list[MissingAttributeItem]
    invalid_attributes: list[InvalidAttributeItem]
    not_applicable_attributes: list[str]
    formatted_description: str | None
    identity_key: str | None
    can_submit: bool


class InventoryItem(BaseModel):
    center_code: str
    quantity: str
    unit: str | None
    unit_price: str | None = None
    total_value: str | None = None


class SimilarCandidate(_Contract):
    material_code: str
    status: str
    active_code_target: str | None
    description: str | None
    match_type: str
    identity_verified: bool
    ranking_score: float
    matching_attributes: list[str]
    conflicts: list[str]
    pending_checks: list[str]
    inventory: list[InventoryItem]


class SimilarMaterials(_Contract):
    match_status: str
    pdm_class_id: str | None
    query_attributes: dict[str, str]
    index_version: str
    candidates: list[SimilarCandidate]
