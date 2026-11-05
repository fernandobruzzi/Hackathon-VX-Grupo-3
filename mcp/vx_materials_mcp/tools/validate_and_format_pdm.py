"""Tool validate_and_format_pdm. A regra fica no domínio, a mesma usada pelo batch."""

from dataclasses import asdict

from domain.contracts import PdmCatalog
from domain.pdm_validator import validate_pdm
from vx_materials_mcp.schemas.tools import PdmValidation
from vx_materials_mcp.tools._catalog import require_version


def run(
    catalog: PdmCatalog,
    pdm_class_id: str,
    pdm_version: str,
    attributes: dict[str, str | None],
    item_name: str | None = None,
    unit: str | None = None,
) -> PdmValidation:
    require_version(catalog, pdm_version)
    result = validate_pdm(catalog, pdm_class_id, attributes, item_name=item_name, unit=unit)
    return PdmValidation.model_validate(asdict(result))
