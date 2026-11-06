"""Adapta a avaliação fiscal compartilhada ao MCP, sem escrita no cadastro."""

from dataclasses import asdict

from mcp.server.mcpserver.exceptions import ToolError

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.contracts import PdmCatalog
from domain.ncm_rules import check_ncm_consistency
from vx_materials_mcp.schemas.tools import NcmConsistency
from vx_materials_mcp.tools._catalog import require_version


def run(
    catalog: PdmCatalog,
    pdm_class_id: str,
    attributes: dict[str, str | None],
    ncm: str | None,
    pdm_version: str | None = None,
    item_name: str | None = None,
    ncm_version: str | None = None,
) -> NcmConsistency:
    require_version(catalog, pdm_version if pdm_version is not None else catalog.version)
    try:
        result = check_ncm_consistency(
            catalog,
            pdm_class_id,
            attributes,
            ncm,
            item_name=item_name,
            ncm_version=ncm_version,
            snapshot=load_configured_ncm_snapshot(ncm_version),
        )
    except ValueError as error:
        raise ToolError(str(error)) from error
    return NcmConsistency.model_validate(asdict(result))
