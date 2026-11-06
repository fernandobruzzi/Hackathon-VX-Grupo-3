"""Busca de materiais no cadastro mestre, com estoque restrito aos centros do usuário.

Lê o cadastro como está: classe, descrição e unidade só mudam por propostas aprovadas. O estoque vem do
dataset mais recente, já com as consolidações aprovadas, e nunca traz preço ou valor.
"""

import unicodedata
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, bindparam, func, select, text
from sqlalchemy.orm import Session, aliased

from domain.contracts import PdmCatalog, PdmClass
from vx_materials_api.db.models import (
    Dataset,
    InventoryConsolidation,
    MaterialInventorySnapshot,
    MaterialMaster,
)
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.materials import InventoryRow, Material, MaterialList
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import has_permission
from vx_materials_api.services.approval_service import exact_product, exact_sum

MAX_TERMS = 8
# Propostas pendentes que viram sinais na busca. Só indicam revisão em andamento, nunca decidem nada.
PENDING_FLAGS = {"MERGE": "DUPLICIDADE_SUSPEITA", "UNIT_CORRECTION": "UNIDADE_NAO_CANONICA"}


def search_terms(query: str | None) -> list[str]:
    """Termos em maiúsculas e sem acento, como o cadastro grava; aspas e curingas viram texto comum."""
    if not query:
        return []
    plain = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode().upper()
    terms = [term for term in plain.replace('"', " ").split() if term]
    if len(terms) > MAX_TERMS:
        raise ApiProblem(422, "VALIDATION_ERROR", f"Use no máximo {MAX_TERMS} termos na busca.")
    return terms


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _class_name(pdm_class: PdmClass) -> str:
    if len(pdm_class.item_names) == 1:
        return pdm_class.item_names[0]
    return pdm_class.noun or " / ".join(pdm_class.item_names)


def _quantity(value: Decimal) -> str:
    text_value = format(value, "f")
    return text_value.rstrip("0").rstrip(".") if "." in text_value else text_value


def search_materials(
    db: Session,
    identity: Identity,
    *,
    query: str | None,
    status: str | None,
    limit: int,
    cursor: str | None,
    catalog: Callable[[], PdmCatalog],
) -> MaterialList:
    terms = search_terms(query)
    target = aliased(MaterialMaster)
    description = func.concat_ws(
        " ",
        MaterialMaster.material_code,
        MaterialMaster.pdm_description,
        MaterialMaster.original_description_short,
        MaterialMaster.original_description_long,
    )
    statement = (
        select(MaterialMaster, target.material_code)
        .outerjoin(target, and_(target.id == MaterialMaster.active_code_target, target.tenant_id == identity.tenant_id))
        .where(MaterialMaster.tenant_id == identity.tenant_id)
    )
    for term in terms:
        # Todos os termos precisam aparecer no código ou em alguma das descrições.
        statement = statement.where(func.upper(description).like(_like(term), escape="\\"))
    if status:
        statement = statement.where(MaterialMaster.status == status)
    if cursor:
        statement = statement.where(MaterialMaster.material_code > cursor)
    rows = db.execute(statement.order_by(MaterialMaster.material_code).limit(limit + 1)).all()
    page, more = rows[:limit], len(rows) > limit
    materials = [row[0] for row in page]

    ids = [material.id for material in materials]
    stock = _inventory(db, identity, ids) if has_permission(identity, "inventory:read") else {}
    flags = _pending_flags(db, identity, ids)
    classes = catalog().classes if any(material.pdm_class_id for material in materials) else {}

    items = []
    for material, target_code in page:
        pdm_class = classes.get(material.pdm_class_id) if material.pdm_class_id else None
        material_flags = sorted(flags.get(material.id, set()))
        if not material.ncm:
            material_flags = ["SEM_NCM", *material_flags]
        items.append(
            Material(
                material_code=material.material_code,
                status=material.status,
                # A descrição curta do ERP é cortada em 40 caracteres: a longa diz mais.
                description=material.pdm_description
                or material.original_description_long
                or material.original_description_short
                or "",
                pdm_class=_class_name(pdm_class) if pdm_class else None,
                unit=material.unit or "",
                ncm=material.ncm,
                active_code_target=target_code,
                inventory=stock.get(material.id, []),
                flags=material_flags,
            )
        )
    return MaterialList(items=items, next_cursor=materials[-1].material_code if more else None)


def _inventory(db: Session, identity: Identity, ids: list[UUID]) -> dict[UUID, list[InventoryRow]]:
    """Saldo por centro e unidade no dataset mais recente, só nos centros do usuário.

    Saldos consolidados por uma unificação aprovada aparecem no material principal, convertidos pelo
    fator registrado, como na view de estoque do MCP. O saldo original fica intacto no banco.
    """
    centers = sorted(identity.center_codes)
    if not ids or not centers:
        return {}
    dataset = db.scalar(
        select(Dataset.id)
        .where(Dataset.tenant_id == identity.tenant_id)
        .order_by(Dataset.imported_at.desc(), Dataset.id.desc())
        .limit(1)
    )
    if dataset is None:
        return {}
    owner = func.coalesce(InventoryConsolidation.primary_material_id, MaterialInventorySnapshot.material_id)
    rows = db.execute(
        select(
            owner.label("material_id"),
            MaterialInventorySnapshot.center_code,
            MaterialInventorySnapshot.quantity,
            MaterialInventorySnapshot.unit,
            InventoryConsolidation.factor,
            InventoryConsolidation.unit.label("consolidated_unit"),
        )
        .outerjoin(
            InventoryConsolidation,
            and_(
                InventoryConsolidation.source_snapshot_id == MaterialInventorySnapshot.id,
                InventoryConsolidation.tenant_id == MaterialInventorySnapshot.tenant_id,
            ),
        )
        .where(
            MaterialInventorySnapshot.tenant_id == identity.tenant_id,
            MaterialInventorySnapshot.dataset_id == dataset,
            MaterialInventorySnapshot.center_code.in_(centers),
            owner.in_(ids),
        )
    ).all()
    grouped: dict[tuple[UUID, str, str], Decimal] = defaultdict(lambda: Decimal(0))
    for row in rows:
        quantity = exact_product(row.quantity, row.factor) if row.factor is not None else row.quantity
        unit = row.consolidated_unit or row.unit or ""
        key = (row.material_id, row.center_code, unit)
        grouped[key] = exact_sum(grouped[key], quantity)
    result: dict[UUID, list[InventoryRow]] = defaultdict(list)
    for (material_id, center, unit), quantity in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][2])):
        result[material_id].append(InventoryRow(center_code=center, quantity=_quantity(quantity), unit=unit))
    return result


def _pending_flags(db: Session, identity: Identity, ids: list[UUID]) -> dict[UUID, set[str]]:
    if not ids:
        return {}
    statement = text(
        "SELECT DISTINCT p.proposal_type, m.value->>'material_id' AS material_id "
        "FROM sanitization_proposals p CROSS JOIN LATERAL jsonb_array_elements(p.members) AS m(value) "
        "WHERE p.tenant_id = :tenant AND p.status = 'PENDING' AND p.proposal_type IN :types "
        "AND m.value->>'material_id' IN :ids"
    ).bindparams(bindparam("types", expanding=True), bindparam("ids", expanding=True))
    params = {"tenant": identity.tenant_id, "types": list(PENDING_FLAGS), "ids": [str(value) for value in ids]}
    rows = db.execute(statement, params).all()
    flags: dict[UUID, set[str]] = defaultdict(set)
    for proposal_type, value in rows:
        flags[UUID(value)].add(PENDING_FLAGS[proposal_type])
    return flags
