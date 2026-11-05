"""Leitura do catálogo e escrita de propostas, com a credencial batch_user.

O batch não altera a base mestre: só registra propostas, aplicadas depois pelo fluxo de aprovação da API.
"""

import json
from decimal import Decimal

from sqlalchemy import Engine, text

from domain.contracts import MaterialRecord, MergeProposal

_READ_MATERIALS = text(
    """
    SELECT m.id::text AS id, m.material_code, m.status, m.original_description_short,
           m.original_description_long, m.manufacturer, m.manufacturer_reference, m.unit, m.ncm, m.version,
           s.center_code, s.quantity, s.unit AS stock_unit, s.total_value, s.raw_record->>'GRUPO_MERCADORIA' AS grupo
    FROM materials_master m
    LEFT JOIN material_inventory_snapshots s ON s.material_id = m.id
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


def single_tenant(engine: Engine) -> str:
    """O MVP tem uma empresa. Mais de uma exige decidir o escopo antes de propor."""
    with engine.connect() as connection:
        tenants = connection.execute(text("SELECT DISTINCT tenant_id::text FROM materials_master")).scalars().all()
    if len(tenants) != 1:
        raise ValueError(f"Esperada uma empresa na base, encontradas {len(tenants)}")
    return tenants[0]


def read_materials(engine: Engine, tenant_id: str) -> list[MaterialRecord]:
    records: dict[str, dict] = {}
    with engine.connect() as connection:
        for row in connection.execute(_READ_MATERIALS, {"tenant_id": tenant_id}).mappings():
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


def save_proposals(
    engine: Engine,
    proposals: list[MergeProposal],
    records: list[MaterialRecord],
    tenant_id: str,
    job_id: str | None = None,
) -> int:
    """Grava em uma transação. Os ids vêm do conteúdo, então repetir não duplica nada."""
    ids = {record.code: record.database_id for record in records}
    inserted = 0
    with engine.begin() as connection:
        for proposal in proposals:
            result = connection.execute(
                _INSERT_PROPOSAL,
                {
                    "id": proposal.id,
                    "tenant_id": tenant_id,
                    "job_id": job_id,
                    "proposal_type": proposal.proposal_type,
                    "members": json.dumps(proposal.members, ensure_ascii=False),
                    "primary_material_id": ids[proposal.suggested_primary_code],
                    "changeset": json.dumps(proposal.changeset, ensure_ascii=False),
                    "changeset_hash": proposal.changeset_hash,
                    "fiscal_review_status": "PENDING" if proposal.fiscal_review_required else "NOT_REQUIRED",
                },
            )
            inserted += result.rowcount if result.rowcount > 0 else 0
    return inserted
