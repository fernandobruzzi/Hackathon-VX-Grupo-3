"""Schemas da busca de materiais (`MaterialList` no OpenAPI). Sem preço nem valor de estoque."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

MaterialStatus = Literal["ATIVO", "BLOQUEADO", "OBSOLETO"]
MaterialFlag = Literal["SEM_NCM", "DUPLICIDADE_SUSPEITA", "UNIDADE_NAO_CANONICA", "ATRIBUTO_FALTANDO"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InventoryRow(_Contract):
    center_code: str
    quantity: str
    unit: str


class Material(_Contract):
    material_code: str
    status: MaterialStatus
    description: str
    pdm_class: str | None
    unit: str
    ncm: str | None
    active_code_target: str | None
    inventory: list[InventoryRow]
    flags: list[MaterialFlag]


class MaterialList(_Contract):
    items: list[Material]
    next_cursor: str | None
