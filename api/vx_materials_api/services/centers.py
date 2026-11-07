"""Nomes dos centros autorizados na observação vigente do tenant."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot
from vx_materials_api.security.identity import Identity


def authorized_center_names(db: Session, identity: Identity) -> dict[str, str]:
    if not identity.center_codes:
        return {}
    dataset = (
        select(Dataset.id)
        .where(Dataset.tenant_id == identity.tenant_id)
        .order_by(Dataset.imported_at.desc(), Dataset.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(MaterialInventorySnapshot.center_code, MaterialInventorySnapshot.center_name)
        .where(
            MaterialInventorySnapshot.tenant_id == identity.tenant_id,
            MaterialInventorySnapshot.dataset_id == dataset,
            MaterialInventorySnapshot.center_code.in_(identity.center_codes),
            MaterialInventorySnapshot.center_name.is_not(None),
        )
        .distinct()
    )
    names: dict[str, set[str]] = defaultdict(set)
    for code, name in rows:
        if name:
            names[code].add(name)
    # Nomes contraditórios não permitem escolher um rótulo com segurança.
    return {code: next(iter(values)) for code, values in names.items() if len(values) == 1}
