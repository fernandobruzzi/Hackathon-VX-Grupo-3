"""Tabelas da seção 5 da arquitetura. Mudanças de schema sempre passam por uma migração."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIMENSIONS = 512

MATERIAL_STATUSES = ("ATIVO", "BLOQUEADO", "OBSOLETO")
PROPOSAL_TYPES = ("MERGE", "PDM_CORRECTION", "UNIT_CORRECTION", "NCM_CORRECTION", "ENRICHMENT", "COMPOSITE")
PROPOSAL_STATUSES = ("PENDING", "APPLIED", "REJECTED", "STALE")
REVIEW_STATUSES = ("PENDING", "APPROVED", "REJECTED", "NOT_REQUIRED")
ORDER_STATUSES = (
    "DRAFT",
    "INCOMPLETE",
    "READY_FOR_REVIEW",
    "EXISTING",
    "OUT_OF_SCOPE",
    "PENDING_FISCAL",
    "REGISTERED",
    "REJECTED",
)
ORDER_ORIGINS = ("CHAT", "IMPORT")
JOB_TYPES = ("SANITIZE", "IMPORT_ORDERS", "ENRICH_REAL_PRODUCTS")
JOB_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
REFERENCE_KINDS = ("PDM", "NCM")
LOT_REVIEW_STATUSES = ("OPEN", "APPROVED", "RETURNED")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({allowed})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), nullable=False)


def _user_fk(*, nullable: bool = True) -> Mapped[Any]:
    return mapped_column(ForeignKey("users_sso.id"), nullable=nullable)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


def _version() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text("1"))


def _jsonb(default: str = "{}") -> Mapped[Any]:
    return mapped_column(JSONB, nullable=False, server_default=text(f"'{default}'::jsonb"))


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class UserSso(Base):
    __tablename__ = "users_sso"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    roles_snapshot: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    browser_context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    tokens_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    demo_label: Mapped[str | None] = mapped_column(Text)


class LoginTransaction(Base):
    __tablename__ = "login_transactions"

    state_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    browser_context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    roles_snapshot: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    effective_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[Any | None] = mapped_column(JSONB)
    after_json: Mapped[Any | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    files: Mapped[Any] = _jsonb()  # hash, versão S3 e contagem de linhas de cada arquivo
    real_material_codes: Mapped[Any] = _jsonb("[]")
    imported_at: Mapped[datetime] = _created_at()


class ReferenceVersion(Base):
    __tablename__ = "reference_versions"
    __table_args__ = (
        UniqueConstraint("kind", "version"),
        CheckConstraint(_one_of("kind", REFERENCE_KINDS), name="kind"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    s3_path: Mapped[str | None] = mapped_column(Text)
    reference_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))


class MaterialMaster(Base):
    __tablename__ = "materials_master"
    __table_args__ = (
        UniqueConstraint("tenant_id", "material_code"),
        CheckConstraint(_one_of("status", MATERIAL_STATUSES), name="status"),
        # Ativo não redireciona, e nenhum material aponta para si mesmo.
        CheckConstraint("status <> 'ATIVO' OR active_code_target IS NULL", name="active_has_no_target"),
        CheckConstraint("active_code_target IS NULL OR active_code_target <> id", name="no_self_target"),
        # A base importada tem duplicidades: a unicidade vale só para principais aprovados.
        Index(
            "uq_materials_master_canonical_identity",
            "tenant_id",
            "identity_key",
            unique=True,
            postgresql_where=text("is_canonical AND status = 'ATIVO'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    material_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    block_reason: Mapped[str | None] = mapped_column(Text)
    active_code_target: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials_master.id"))
    original_description_short: Mapped[str | None] = mapped_column(Text)
    original_description_long: Mapped[str | None] = mapped_column(Text)
    pdm_description: Mapped[str | None] = mapped_column(Text)
    pdm_class_id: Mapped[str | None] = mapped_column(Text)
    pdm_version: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[Any] = _jsonb()
    manufacturer: Mapped[str | None] = mapped_column(Text)
    manufacturer_reference: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    ncm: Mapped[str | None] = mapped_column(Text)
    ncm_review_status: Mapped[str | None] = mapped_column(Text)
    # Grupo da carga, imutável, e grupo revisado, gravado só por proposta aprovada.
    original_merchandise_group: Mapped[str | None] = mapped_column(Text)
    merchandise_group: Mapped[str | None] = mapped_column(Text)
    identity_key: Mapped[str | None] = mapped_column(Text)
    is_canonical: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    version: Mapped[int] = _version()


class MaterialInventorySnapshot(Base):
    __tablename__ = "material_inventory_snapshots"
    __table_args__ = (UniqueConstraint("dataset_id", "source_line"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    center_code: Mapped[str] = mapped_column(Text, nullable=False)
    center_name: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric)
    source_line: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_record: Mapped[Any] = _jsonb()


class BatchJob(Base):
    __tablename__ = "batch_jobs"
    __table_args__ = (
        CheckConstraint(_one_of("job_type", JOB_TYPES), name="job_type"),
        CheckConstraint(_one_of("status", JOB_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    requested_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    pdm_version: Mapped[str] = mapped_column(Text, nullable=False)
    ncm_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'QUEUED'"))
    task_arn: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    counts: Mapped[Any] = _jsonb()
    automatic_corrections: Mapped[Any] = _jsonb()
    checkpoint: Mapped[Any] = _jsonb()
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class MaterialSearchIndex(Base):
    __tablename__ = "material_search_index"
    __table_args__ = (
        # Um índice por versão: consulta e indexação precisam usar a mesma versão.
        UniqueConstraint("material_id", "normalization_version"),
        Index("ix_material_search_index_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_material_search_index_candidate_identity_key", "candidate_identity_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batch_jobs.id"))
    proposed_class_id: Mapped[str | None] = mapped_column(Text)
    extracted_attributes: Mapped[Any] = _jsonb()
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    normalization_version: Mapped[str | None] = mapped_column(Text)
    candidate_identity_key: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class SanitizationProposal(Base):
    __tablename__ = "sanitization_proposals"
    __table_args__ = (
        CheckConstraint(_one_of("proposal_type", PROPOSAL_TYPES), name="proposal_type"),
        CheckConstraint(_one_of("status", PROPOSAL_STATUSES), name="status"),
        CheckConstraint(_one_of("technical_review_status", REVIEW_STATUSES), name="technical_review_status"),
        CheckConstraint(_one_of("fiscal_review_status", REVIEW_STATUSES), name="fiscal_review_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batch_jobs.id"))
    proposal_type: Mapped[str] = mapped_column(Text, nullable=False)
    members: Mapped[Any] = _jsonb("[]")
    primary_material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials_master.id"))
    changeset: Mapped[Any] = _jsonb()
    changeset_hash: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[Any] = _jsonb("[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    technical_review_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    application_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'HUMAN'"))
    technical_reviewer_id: Mapped[uuid.UUID | None] = _user_fk()
    fiscal_review_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NOT_REQUIRED'"))
    fiscal_reviewer_id: Mapped[uuid.UUID | None] = _user_fk()
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class RegistrationOrder(Base):
    __tablename__ = "registration_orders"
    __table_args__ = (
        CheckConstraint(_one_of("origin", ORDER_ORIGINS), name="origin"),
        CheckConstraint(_one_of("status", ORDER_STATUSES), name="status"),
        # Pedido criado pelo chat sempre tem solicitante autenticado.
        CheckConstraint("origin <> 'CHAT' OR requester_user_id IS NOT NULL", name="chat_has_requester"),
        UniqueConstraint("tenant_id", "source_order_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    source_order_id: Mapped[str | None] = mapped_column(Text)
    requester_user_id: Mapped[uuid.UUID | None] = _user_fk()
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_text: Mapped[str | None] = mapped_column(Text)
    supplements: Mapped[Any] = _jsonb("[]")
    center_code: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str | None] = mapped_column(Text)
    pdm_class_id: Mapped[str | None] = mapped_column(Text)
    item_name: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[Any] = _jsonb()
    review_data: Mapped[Any] = _jsonb()
    missing_attributes: Mapped[Any] = _jsonb("[]")
    candidate_material_ids: Mapped[Any] = _jsonb("[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials_master.id"))
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    owner_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    registration_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("registration_orders.id"))
    context: Mapped[Any] = _jsonb()
    pdm_version: Mapped[str | None] = mapped_column(Text)
    ncm_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = _version()
    active_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence"),
        UniqueConstraint("session_id", "client_message_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    author_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Any] = _jsonb("[]")
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()


class EnrichmentSource(Base):
    __tablename__ = "enrichment_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    attribute_name: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    source_page: Mapped[str | None] = mapped_column(Text)
    s3_object_key: Mapped[str | None] = mapped_column(Text)
    source_sha256: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence_level: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_basis: Mapped[Any] = _jsonb("[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    validated_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationRequest(Base):
    __tablename__ = "operation_requests"
    __table_args__ = (UniqueConstraint("user_id", "operation", "idempotency_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(Text)
    response: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class InventoryConsolidation(Base):
    __tablename__ = "inventory_consolidations"
    __table_args__ = (CheckConstraint("factor > 0", name="positive_factor"),)

    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_inventory_snapshots.id"), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = _tenant()
    primary_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sanitization_proposals.id"), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    conversion_source: Mapped[str] = mapped_column(Text, nullable=False)


class QualitySnapshot(Base):
    """Situação da base depois das propostas aplicadas. Imutável: um novo estado gera outro snapshot."""

    __tablename__ = "quality_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    applied_proposal_ids: Mapped[Any] = _jsonb("[]")
    summary: Mapped[Any] = _jsonb()
    export_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class QualitySnapshotItem(Base):
    """Estado de cada material no snapshot, com as propostas aplicadas que explicam a mudança."""

    __tablename__ = "quality_snapshot_items"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quality_snapshots.id"), primary_key=True)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = _tenant()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    ncm: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    proposal_ids: Mapped[Any] = _jsonb("[]")


class LotReview(Base):
    """Revisão por amostra de um lote de correções de forma (#120).

    Guarda as propostas e versões do lote no momento da abertura e a amostra sorteada pelo servidor.
    Nada é aplicado antes da decisão: aprovar aplica cada proposta pelo fluxo normal de aprovação.
    """

    __tablename__ = "lot_reviews"
    __table_args__ = (
        CheckConstraint(_one_of("status", LOT_REVIEW_STATUSES), name="status"),
        CheckConstraint("tier IN (1, 2)", name="tier"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    lot_key: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_type: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_versions: Mapped[Any] = _jsonb()
    sample_ids: Mapped[Any] = _jsonb("[]")
    marks: Mapped[Any] = _jsonb()
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    result: Mapped[Any] = _jsonb()
    created_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualReview(Base):
    """Pendência observada pelo batch; encaminhar gera proposta, nunca edição do mestre."""

    __tablename__ = "manual_reviews"
    __table_args__ = (
        UniqueConstraint("run_id", "material_id"),
        Index("ix_manual_reviews_tenant_id_run_id", "tenant_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batch_jobs.id"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    expected_material_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    observation: Mapped[Any] = _jsonb()
    rules_signature: Mapped[str] = mapped_column(Text, nullable=False)
    pdm_version: Mapped[str] = mapped_column(Text, nullable=False)
    pdm_source_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sanitization_proposals.id"))
    created_at: Mapped[datetime] = _created_at()


class AutomaticCorrectionRun(Base):
    """Execução autorizada pelo servidor, congelada nas propostas novas de um job."""

    __tablename__ = "automatic_correction_runs"
    __table_args__ = (
        UniqueConstraint("job_id"),
        CheckConstraint("mode IN ('SIMULATE', 'APPLY')", name="mode"),
        Index("ix_automatic_correction_runs_tenant_id", "tenant_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batch_jobs.id"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    rules_signature: Mapped[str] = mapped_column(Text, nullable=False)
    target_ids: Mapped[Any] = _jsonb("[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'RUNNING'"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class AutomaticCorrectionResult(Base):
    """Desfecho durável por proposta; a aplicação e seu registro compartilham a transação."""

    __tablename__ = "automatic_correction_results"
    __table_args__ = (
        UniqueConstraint("run_id", "proposal_id"),
        Index("ix_automatic_correction_results_tenant_id", "tenant_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automatic_correction_runs.id"), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sanitization_proposals.id"), nullable=False)
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials_master.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    eligible: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    reasons: Mapped[Any] = _jsonb("[]")
    evidence: Mapped[Any] = _jsonb()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    index_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NOT_REQUIRED'"))
    index_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class MaterialRequest(Base):
    __tablename__ = "material_requests"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        CheckConstraint("length(btrim(original_text)) > 0", name="original_text"),
        CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint(
            "status IN ('EM_IDENTIFICACAO', 'AGUARDANDO_CADASTRO', 'EM_ATENDIMENTO', 'ENCERRADA')", name="status"
        ),
        CheckConstraint("(status = 'ENCERRADA') = (closure_reason IS NOT NULL)", name="closure_reason"),
        Index("ix_material_requests_tenant_id_requester_user_id", "tenant_id", "requester_user_id"),
        Index("ix_material_requests_tenant_id_center_code_status", "tenant_id", "center_code", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    protocol_number: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    tenant_id: Mapped[uuid.UUID] = _tenant()
    requester_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials_master.id"))
    quantity: Mapped[Any] = mapped_column(Numeric(24, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    center_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    closure_reason: Mapped[str | None] = mapped_column(Text)
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_sessions.id"))
    registration_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("registration_orders.id"))
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


RESERVATION_STATUSES = ("ATIVA", "CONSUMIDA", "CANCELADA")
MOVEMENT_TYPES = ("ENTREGA", "REVERSAO")


class StockReservation(Base):
    """Compromisso de saldo de um centro para uma solicitação; nunca altera os snapshots importados."""

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        CheckConstraint(_one_of("status", RESERVATION_STATUSES), name="status"),
        CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        CheckConstraint("version > 0", name="version"),
        Index(
            "ix_stock_reservations_tenant_id_material_id_center_code_status",
            "tenant_id",
            "material_id",
            "center_code",
            "status",
        ),
        Index("ix_stock_reservations_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_requests.id"), nullable=False)
    # Material principal: saldos consolidados por unificação aprovada aparecem nele.
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    center_code: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(24, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ATIVA'"))
    # Dataset de estoque vigente quando a reserva foi feita (seção 4.4 do modelo).
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class StockMovement(Base):
    """Entrega ou reversão de uma reserva. Somente inserção; as operações chegam na #240."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        CheckConstraint(_one_of("movement_type", MOVEMENT_TYPES), name="movement_type"),
        CheckConstraint("(movement_type = 'REVERSAO') = (reverses_movement_id IS NOT NULL)", name="reversal_reference"),
        Index("ix_stock_movements_reservation_id", "reservation_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_reservations.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(24, 6), nullable=False)
    reverses_movement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stock_movements.id"))
    # Saídas só descontam do saldo do dataset contra o qual foram registradas (D4).
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = _created_at()


PURCHASE_FORWARD_STATUSES = ("ENCAMINHADO", "ACEITO", "DEVOLVIDO", "CANCELADO")


class PurchaseForward(Base):
    """Demanda para Compras com o código já cadastrado; não comprova pedido, recebimento nem entrega."""

    __tablename__ = "purchase_forwards"
    __table_args__ = (
        # Uma parcela por versão da solicitação: repetir o encaminhamento não o duplica.
        UniqueConstraint("material_request_id", "request_version"),
        CheckConstraint("quantity > 0 AND quantity <> 'NaN'::numeric", name="positive_quantity"),
        CheckConstraint("length(btrim(unit)) > 0", name="unit"),
        CheckConstraint("length(btrim(center_code)) > 0", name="center_code"),
        CheckConstraint(_one_of("status", PURCHASE_FORWARD_STATUSES), name="status"),
        CheckConstraint("(status IN ('DEVOLVIDO', 'CANCELADO')) = (reason IS NOT NULL)", name="reason"),
        CheckConstraint("(status IN ('ACEITO', 'DEVOLVIDO')) = (handled_by_user_id IS NOT NULL)", name="handled_by"),
        CheckConstraint("version > 0", name="version"),
        CheckConstraint("request_version > 0", name="request_version"),
        Index("ix_purchase_forwards_tenant_id_center_code_status", "tenant_id", "center_code", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    material_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_requests.id"), nullable=False)
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials_master.id"), nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(24, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    center_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    forwarded_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    handled_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = _version()
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
