"""Resources MCP: referências versionadas e fichas limitadas ao escopo autenticado."""

import json

from mcp.server.mcpserver.exceptions import ResourceError, ToolError

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
        """Registro fiscal versionado; indisponível até integrar snapshot oficial validado (#22/#30)."""
        raise ResourceError("Referencia NCM oficial indisponivel; vigencia e classificacao exigem revisao fiscal")

    @server.resource("material://{material_code}", mime_type="application/json")
    def material(material_code: str) -> str:
        """Ficha do tenant autenticado; estoque por centro e valores apenas com permissão financeira."""
        return json.dumps(_read(repository.material, material_code), ensure_ascii=False, default=str)

    @server.resource("evidence://{source_id}", mime_type="application/json")
    def evidence(source_id: str) -> str:
        """Origem, trecho, confiança e situação de uma evidência do tenant autenticado."""
        return json.dumps(_read(repository.evidence, source_id), ensure_ascii=False, default=str)
