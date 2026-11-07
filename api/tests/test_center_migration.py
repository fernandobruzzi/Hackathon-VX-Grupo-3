"""Recuperação dos nomes usa apenas a evidência original do snapshot."""

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import insert, select, text

from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot


def test_center_backfill_preserves_stock_and_requires_matching_code(connection, tenant, add_material):
    material = add_material("001")
    dataset = connection.execute(insert(Dataset).values(tenant_id=tenant).returning(Dataset.id)).scalar_one()
    originals = ["0010 - UNIDADE  - NORTE", "1200", "9999 - OUTRO CENTRO"]
    for line, original in enumerate(originals, 1):
        connection.execute(
            insert(MaterialInventorySnapshot).values(
                tenant_id=tenant,
                dataset_id=dataset,
                material_id=material,
                center_code="0010" if line == 1 else "1200",
                quantity=5,
                total_value=10,
                source_line=line,
                raw_record={"CENTRO": original},
            )
        )
    migration = importlib.import_module("vx_materials_api.db.migrations.versions.0019_center_names")
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
        migration.upgrade()
    rows = (
        connection.execute(
            select(MaterialInventorySnapshot)
            .where(MaterialInventorySnapshot.dataset_id == dataset)
            .order_by(MaterialInventorySnapshot.source_line)
        )
        .mappings()
        .all()
    )
    assert [row["center_name"] for row in rows] == ["UNIDADE - NORTE", None, None]
    assert [row["raw_record"]["CENTRO"] for row in rows] == originals
    assert all(row["quantity"] == 5 and row["total_value"] == 10 for row in rows)
    assert connection.execute(text("SELECT center_name FROM mcp_inventory WHERE dataset_id = :d"), {"d": dataset}).all()
