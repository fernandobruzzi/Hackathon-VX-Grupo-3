"""Resources MCP: referências versionadas e fichas limitadas ao escopo autenticado."""

import json
from dataclasses import asdict

from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from clients.ncm_snapshot_store import load_configured_ncm_snapshot
from domain.ncm_snapshot import OFFICIAL_NCM_URL, NcmSourceKind, check_snapshot_ncm
from vx_materials_mcp.tools.get_pdm_template import run as pdm_template


def _read(operation, *arguments):
    try:
        return operation(*arguments)
    except (ValueError, ToolError) as error:
        raise ResourceError(str(error)) from error


def register_resources(server, catalog, repository):
    @server.resource("pdm://{pdm_version}/classes/{pdm_class_id}", mime_type="application/json")
    def pdm(pdm_version: str, pdm_class_id: str) -> str:
        """Template público da classe e versão PDM informadas; não contém dados do usuário."""
        return _read(pdm_template, catalog, pdm_class_id, pdm_version).model_dump_json()

    @server.resource("ncm://{ncm_version}/codes/{code}", mime_type="application/json")
    def ncm(ncm_version: str, code: str) -> str:
        """Registro do snapshot selecionado no servidor, com escopo ativo e procedência explícita."""
        _read(repository.require_read_access)
        snapshot = _read(load_configured_ncm_snapshot, ncm_version)
        if snapshot is None:
            raise ResourceError("Snapshot NCM indisponível; existência e vigência desconhecidas")
        check = check_snapshot_ncm(snapshot, code)
        record = snapshot.records.get(check.normalized_ncm)
        return json.dumps(
            {
                **asdict(check),
                "record": asdict(record) if record else None,
                "source_last_update": snapshot.source_last_update,
                "source_url": OFFICIAL_NCM_URL if snapshot.source_kind == NcmSourceKind.OFFICIAL_DOWNLOAD else None,
            },
            ensure_ascii=False,
            default=str,
        )

    @server.resource("material://{material_code}", mime_type="application/json")
    def material(material_code: str) -> str:
        """Ficha do tenant autenticado; estoque por centro e valores apenas com permissão financeira."""
        return json.dumps(_read(repository.material, material_code), ensure_ascii=False, default=str)

    @server.resource("evidence://{source_id}", mime_type="application/json")
    def evidence(source_id: str) -> str:
        """Origem, trecho, confiança e situação de uma evidência do tenant autenticado."""
        return json.dumps(_read(repository.evidence, source_id), ensure_ascii=False, default=str)
