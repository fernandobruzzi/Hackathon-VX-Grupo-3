"""Leitura do catálogo e escrita de propostas, com a credencial batch_user.

O batch não altera a base mestre: só registra propostas, aplicadas depois pelo fluxo de aprovação da API.
"""

import json
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy import Connection, Engine, text

from domain.contracts import MaterialRecord, MergeProposal
from repositories.proposal_payload import approval_payload

_READ_MATERIALS = text(
    """
    SELECT m.id::text AS id, m.material_code, m.status, m.original_description_short,
           m.original_description_long, m.manufacturer, m.manufacturer_reference, m.unit, m.ncm, m.version,
           s.center_code, s.quantity, s.unit AS stock_unit, s.total_value, s.raw_record->>'GRUPO_MERCADORIA' AS grupo
    FROM materials_master m
    LEFT JOIN material_inventory_snapshots s ON s.material_id = m.id
      AND (CAST(:dataset_id AS uuid) IS NULL OR s.dataset_id = CAST(:dataset_id AS uuid))
    WHERE m.tenant_id = :tenant_id
    ORDER BY m.material_code
    """
)

_INSERT_PROPOSAL = text(
    """
    INSERT INTO sanitization_proposals (
        id, tenant_id, job_id, proposal_type, members, primary_material_id, changeset, changeset_hash,
        technical_review_status, fiscal_review_status
    )
    VALUES (
        :id, :tenant_id, :job_id, :proposal_type, CAST(:members AS jsonb), :primary_material_id,
        CAST(:changeset AS jsonb), :changeset_hash, 'PENDING', :fiscal_review_status
    )
    ON CONFLICT (id) DO NOTHING
    RETURNING id
    """
)

# Função da migração 0008: o batch não grava auditoria direto, só pede a substituição das pendentes.
_SUPERSEDE = text("SELECT supersede_proposals(CAST(:ids AS uuid[]))")


def single_tenant(engine: Engine) -> str:
    """O MVP tem uma empresa. Mais de uma exige decidir o escopo antes de propor."""
    with engine.connect() as connection:
        tenants = connection.execute(text("SELECT DISTINCT tenant_id::text FROM materials_master")).scalars().all()
    if len(tenants) != 1:
        raise ValueError(f"Esperada uma empresa na base, encontradas {len(tenants)}")
    return tenants[0]


def read_materials(engine: Engine, tenant_id: str, *, require_single_dataset: bool = False) -> list[MaterialRecord]:
    records: dict[str, dict] = {}
    with engine.connect() as connection:
        dataset_id = single_dataset(connection, tenant_id) if require_single_dataset else None
        for row in connection.execute(_READ_MATERIALS, {"tenant_id": tenant_id, "dataset_id": dataset_id}).mappings():
            current = records.setdefault(
                row["material_code"],
                {
                    "row": row,
                    "inventory": [],
                    "total": Decimal(0),
                },
            )
            if row["center_code"] is not None:
                current["inventory"].append(
                    {"center_code": row["center_code"], "quantity": str(row["quantity"]), "unit": row["stock_unit"]}
                )
                current["total"] += row["total_value"] or Decimal(0)
    return [_record(value["row"], value["inventory"], value["total"]) for value in records.values()]


def _record(row, inventory: list[dict], total: Decimal) -> MaterialRecord:
    return MaterialRecord(
        code=row["material_code"],
        status=row["status"],
        description=row["original_description_long"] or "",
        short_description=row["original_description_short"] or "",
        group=row["grupo"] or "",
        manufacturer=row["manufacturer"] or "",
        reference=row["manufacturer_reference"] or "",
        unit=row["unit"] or "",
        ncm=row["ncm"] or "",
        version=row["version"],
        total_value=str(total),
        inventory=tuple(inventory),
        database_id=row["id"],
    )


@dataclass(frozen=True)
class SearchSource:
    record: MaterialRecord
    approved_class_id: str | None
    approved_attributes: dict
    original_description: str | None = None


def read_search_sources(
    engine: Engine, tenant_id: str, version: str, *, only_stale: bool = False
) -> list[SearchSource]:
    """A interpretação sugerida fica no índice; os valores na master são os dados atuais aprovados."""
    query = text(
        "SELECT m.id::text AS id, m.material_code, m.status, m.original_description_short, "
        "m.original_description_long, m.manufacturer, m.manufacturer_reference, m.unit, m.ncm, m.version, "
        "m.pdm_class_id, m.pdm_description, m.attributes, s.grupo "
        "FROM materials_master m LEFT JOIN (SELECT DISTINCT ON (material_id) material_id, tenant_id, "
        "raw_record->>'GRUPO_MERCADORIA' AS grupo FROM material_inventory_snapshots "
        "WHERE tenant_id = :tenant ORDER BY material_id, source_line) s "
        "ON s.material_id = m.id AND s.tenant_id = m.tenant_id "
        "LEFT JOIN material_search_index i ON i.material_id = m.id "
        "AND i.tenant_id = m.tenant_id AND i.normalization_version = :version "
        "WHERE m.tenant_id = :tenant AND (NOT :only_stale OR i.source_version IS DISTINCT FROM m.version) "
        "ORDER BY m.id"
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"tenant": tenant_id, "version": version, "only_stale": only_stale}).mappings()
        result = []
        for row in rows:
            record = _record(row, [], Decimal(0))
            if row["pdm_description"]:
                record = replace(record, description=row["pdm_description"], short_description="")
            result.append(
                SearchSource(
                    record, row["pdm_class_id"], dict(row["attributes"] or {}), row["original_description_long"]
                )
            )
        return result


_INDEX_COVERAGE = text(
    """
    SELECT
        (SELECT count(*) FROM materials_master WHERE tenant_id = :tenant_id) AS materials,
        (
            SELECT count(*) FROM material_search_index i JOIN materials_master m ON m.id = i.material_id
            WHERE i.tenant_id = :tenant_id AND m.tenant_id = :tenant_id
            AND i.normalization_version = :version AND i.source_version = m.version
        ) AS indexed
    """
)
_INSERT_INDEX = text(
    """
    INSERT INTO material_search_index (
        tenant_id, material_id, proposed_class_id, extracted_attributes, search_vector, normalization_version,
        candidate_identity_key, embedding, embedding_model, source_version
    )
    VALUES (
        :tenant_id, :material_id, :proposed_class_id, CAST(:extracted_attributes AS jsonb),
        to_tsvector('simple', :search_text), :version, :candidate_identity_key, CAST(:embedding AS vector),
        :embedding_model, :source_version
    )
    ON CONFLICT (material_id, normalization_version) DO UPDATE SET
        proposed_class_id = EXCLUDED.proposed_class_id,
        extracted_attributes = EXCLUDED.extracted_attributes,
        search_vector = EXCLUDED.search_vector,
        candidate_identity_key = EXCLUDED.candidate_identity_key,
        embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model,
        source_version = EXCLUDED.source_version
    WHERE material_search_index.source_version <= EXCLUDED.source_version
    """
)


def index_coverage(engine: Engine, tenant_id: str, version: str) -> tuple[int, int]:
    """Materiais da empresa e quantos deles têm linha no índice desta versão."""
    with engine.connect() as connection:
        row = connection.execute(_INDEX_COVERAGE, {"tenant_id": tenant_id, "version": version}).one()
    return row.materials, row.indexed


def write_search_index(engine: Engine, tenant_id: str, version: str, rows: list[dict]) -> int:
    """Confirma um lote atomicamente, sem sobrescrever uma revisão mais recente do material."""
    with engine.begin() as connection:
        payload = [
            {
                **row,
                "tenant_id": tenant_id,
                "version": version,
                "extracted_attributes": json.dumps(row["extracted_attributes"], ensure_ascii=False),
            }
            for row in rows
        ]
        if payload:
            connection.execute(_INSERT_INDEX, payload)
    return len(rows)


def _proposal_row(
    proposal: MergeProposal, ids: dict[str, str | None], tenant_id: str, job_id: str | None, dataset_id: str
) -> dict:
    members, changeset, digest = approval_payload(proposal, ids, dataset_id)
    return {
        "id": str(uuid.uuid5(uuid.UUID(proposal.id), digest)),
        "tenant_id": tenant_id,
        "job_id": job_id,
        "proposal_type": proposal.proposal_type,
        "members": json.dumps(members, ensure_ascii=False),
        "primary_material_id": ids[proposal.suggested_primary_code],
        "changeset": json.dumps(changeset, ensure_ascii=False),
        "changeset_hash": digest,
        "fiscal_review_status": "PENDING" if proposal.fiscal_review_required else "NOT_REQUIRED",
    }


def single_dataset(connection: Connection, tenant_id: str) -> str:
    """Recusa escopo ambíguo antes de ler saldos ou gravar propostas."""
    datasets = (
        connection.execute(text("SELECT id::text FROM datasets WHERE tenant_id = :tenant"), {"tenant": tenant_id})
        .scalars()
        .all()
    )
    if len(datasets) != 1:
        raise ValueError(
            "O batch exige exatamente um dataset por empresa no MVP; múltiplas importações não são suportadas"
        )
    return datasets[0]


def insert_proposals(
    connection: Connection,
    proposals: list[MergeProposal],
    records: list[MaterialRecord],
    tenant_id: str,
    job_id: str | None = None,
) -> int:
    """Insere na transação de quem chama. Os ids vêm do conteúdo, então repetir não duplica nada.

    Conteúdo novo para os mesmos tipo e membros gera id novo: a pendente anterior vira STALE, com auditoria,
    na mesma transação.
    """
    ids = {record.code: record.database_id for record in records}
    if not proposals:
        return 0
    dataset_id = single_dataset(connection, tenant_id)
    new_ids = []
    for proposal in proposals:
        result = connection.execute(_INSERT_PROPOSAL, _proposal_row(proposal, ids, tenant_id, job_id, dataset_id))
        new_ids.extend(result.scalars().all())
    if new_ids:
        connection.execute(_SUPERSEDE, {"ids": new_ids})
    return len(new_ids)


# Jobs: a API cria o registro (batch_user não insere); o batch só acompanha e conclui.
#
# Cada execução é um worker com id próprio, gravado em `checkpoint.lease`. Toda escrita do worker exige
# que o job continue RUNNING e com o lease dele: se a API marcou o job como parado por falta de
# heartbeat, ou se outro worker assumiu, a escrita não acontece e o worker para (`LeaseLost`).
_LOAD_JOB = text(
    """
    SELECT id::text, tenant_id::text, job_type, status, checkpoint,
           heartbeat_at IS NOT NULL AND heartbeat_at > now() - make_interval(secs => :stale) AS alive
    FROM batch_jobs WHERE id = :id FOR UPDATE
    """
)
_CLAIM_JOB = text(
    """
    UPDATE batch_jobs
    SET status = 'RUNNING', heartbeat_at = now(), checkpoint = CAST(:checkpoint AS jsonb), error_summary = NULL
    WHERE id = :id
    """
)
_UPDATE_JOB = text(
    """
    UPDATE batch_jobs
    SET status = :status, heartbeat_at = now(), checkpoint = CAST(:checkpoint AS jsonb),
        counts = COALESCE(CAST(:counts AS jsonb), counts), error_summary = :error
    WHERE id = :id AND status = 'RUNNING' AND checkpoint -> 'lease' ->> 'worker' = :worker
    """
)
_HEARTBEAT = text(
    """
    UPDATE batch_jobs SET heartbeat_at = now()
    WHERE id = :id AND status = 'RUNNING' AND checkpoint -> 'lease' ->> 'worker' = :worker
    """
)
# Sem heartbeat por mais que isso, o worker anterior é considerado parado e outro pode assumir.
DEFAULT_STALE_SECONDS = 120


class JobNotRunnable(ValueError):
    """O job não existe, é de outro tipo, já terminou ou tem outro worker vivo."""


class LeaseLost(RuntimeError):
    """O job deixou de pertencer a este worker: foi dado como parado ou outro worker assumiu."""


def claim_job(
    engine: Engine, job_id: str, worker_id: str, job_type: str = "SANITIZE", stale_seconds: int = DEFAULT_STALE_SECONDS
) -> dict:
    """Marca o job como RUNNING para este worker e devolve o checkpoint salvo, para continuar de onde parou."""
    with engine.begin() as connection:
        row = connection.execute(_LOAD_JOB, {"id": job_id, "stale": stale_seconds}).mappings().first()
        if row is None or row["job_type"] != job_type:
            raise JobNotRunnable(f"Job {job_id} inexistente ou de outro tipo")
        if row["status"] == "SUCCEEDED":
            raise JobNotRunnable(f"Job {job_id} já concluído")
        if row["status"] == "RUNNING" and row["alive"]:
            raise JobNotRunnable(f"Job {job_id} já está rodando em outro worker")
        checkpoint = dict(row["checkpoint"] or {})
        checkpoint["lease"] = {"worker": worker_id}
        connection.execute(_CLAIM_JOB, {"id": job_id, "checkpoint": json.dumps(checkpoint, ensure_ascii=False)})
    return {"tenant_id": row["tenant_id"], "checkpoint": checkpoint}


def _worker(checkpoint: dict) -> str:
    return checkpoint["lease"]["worker"]


def _update(connection: Connection, job_id: str, status: str, checkpoint: dict, counts=None, error=None) -> None:
    result = connection.execute(
        _UPDATE_JOB,
        {
            "id": job_id,
            "status": status,
            "checkpoint": json.dumps(checkpoint, ensure_ascii=False),
            "counts": None if counts is None else json.dumps(counts, ensure_ascii=False),
            "error": error,
            "worker": _worker(checkpoint),
        },
    )
    if result.rowcount != 1:
        raise LeaseLost(f"Job {job_id} não pertence mais a este worker")


def heartbeat(engine: Engine, job_id: str, worker_id: str) -> bool:
    """Sinal de vida entre checkpoints. Falso quando o job não é mais deste worker."""
    with engine.begin() as connection:
        return connection.execute(_HEARTBEAT, {"id": job_id, "worker": worker_id}).rowcount == 1


def update_job(connection: Connection, job_id: str, checkpoint: dict) -> None:
    """Checkpoint e heartbeat, na mesma transação do trabalho que eles registram."""
    _update(connection, job_id, "RUNNING", checkpoint)


def finish_job(engine: Engine, job_id: str, checkpoint: dict, counts: dict) -> None:
    with engine.begin() as connection:
        _update(connection, job_id, "SUCCEEDED", checkpoint, counts)


def fail_job(engine: Engine, job_id: str, checkpoint: dict, error: str) -> None:
    """Falha guarda o checkpoint: rodar de novo continua dele. Sem o lease, não sobrescreve nada."""
    try:
        with engine.begin() as connection:
            _update(connection, job_id, "FAILED", checkpoint, error=error[:500])
    except LeaseLost:
        pass
