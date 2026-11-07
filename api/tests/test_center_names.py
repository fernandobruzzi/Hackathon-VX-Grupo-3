"""Rótulos da sessão respeitam empresa, centros e dataset atual."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import insert

from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot
from vx_materials_api.security.identity import Identity
from vx_materials_api.services.centers import authorized_center_names


def test_names_use_only_the_current_authorized_dataset(connection, tenant, add_material):
    material = add_material("CENTER-TEST")
    other = uuid.uuid4()
    datasets = []
    for owner, year in [(tenant, 2025), (tenant, 2026), (other, 2026)]:
        datasets.append(
            connection.execute(
                insert(Dataset)
                .values(tenant_id=owner, imported_at=datetime(year, 1, 1, tzinfo=UTC))
                .returning(Dataset.id)
            ).scalar_one()
        )
    old, current, foreign = datasets
    cases = [
        (tenant, old, "1100", "NOME ANTIGO"),
        (tenant, current, "1100", "MINA SERRA AZUL"),
        (tenant, current, "1200", "NOME A"),
        (tenant, current, "1200", "NOME B"),
        (tenant, current, "1300", None),
        (tenant, current, "9000", "CENTRO NAO AUTORIZADO"),
        (other, foreign, "1100", "CENTRO DE OUTRA EMPRESA"),
    ]
    for line, (owner, dataset, code, name) in enumerate(cases, 1):
        connection.execute(
            insert(MaterialInventorySnapshot).values(
                tenant_id=owner,
                dataset_id=dataset,
                material_id=material,
                center_code=code,
                center_name=name,
                quantity=1,
                source_line=line,
            )
        )
    identity = Identity(uuid.uuid4(), tenant, (), frozenset(), center_codes=frozenset({"1100", "1200", "1300"}))
    assert authorized_center_names(connection, identity) == {"1100": "MINA SERRA AZUL"}
