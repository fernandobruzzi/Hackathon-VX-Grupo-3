"""Busca de materiais com estoque dos centros autorizados. Somente leitura."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from vx_materials_api.dependencies import current_identity, db_session
from vx_materials_api.routes.sanitization import catalog
from vx_materials_api.schemas.materials import MaterialList
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.materials_service import search_materials

router = APIRouter(prefix="/api/v1", tags=["materials"])


@router.get("/materials")
def list_materials(
    request: Request,
    identity: Annotated[Identity, Depends(current_identity)],
    db: Annotated[Session, Depends(db_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: Literal["ATIVO", "BLOQUEADO", "OBSOLETO"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> MaterialList:
    """Busca por código ou descrição. Estoque só dos centros do usuário e nunca com preço ou valor."""
    require_permission(identity, "materials:read")
    return search_materials(
        db,
        identity,
        query=q,
        status=status,
        limit=limit,
        cursor=cursor,
        catalog=lambda: catalog(request),
    )
