"""Tool get_pdm_template."""

from mcp.server.mcpserver.exceptions import ToolError

from domain.contracts import Condition, ConditionOperator, PdmCatalog
from vx_materials_mcp.schemas.tools import AppliesWhen, NcmReferenceItem, PdmTemplate, TemplateAttribute
from vx_materials_mcp.tools._catalog import require_version


def _applies_when(condition: Condition) -> AppliesWhen:
    if condition.operator is ConditionOperator.ALWAYS:
        return AppliesWhen(operator=condition.operator.value)
    return AppliesWhen(operator=condition.operator.value, subject=condition.subject, values=list(condition.values))


def run(catalog: PdmCatalog, pdm_class_id: str, pdm_version: str) -> PdmTemplate:
    require_version(catalog, pdm_version)
    pdm_class = catalog.classes.get(pdm_class_id)
    if pdm_class is None:
        raise ToolError(f"Classe do PDM desconhecida: {pdm_class_id}")
    return PdmTemplate(
        pdm_class_id=pdm_class.id,
        pdm_version=catalog.version,
        noun=pdm_class.noun,
        qualifier=pdm_class.qualifiers[0] if len(pdm_class.qualifiers) == 1 else None,
        item_names=list(pdm_class.item_names),
        identity_mode=pdm_class.identity_mode.value,
        default_unit=pdm_class.default_unit,
        attributes=[
            TemplateAttribute(
                name=attribute.name,
                order=attribute.order,
                required=attribute.required,
                applies_when=_applies_when(attribute.applies_when),
                format=attribute.format,
                allowed_values=list(attribute.allowed_values) if attribute.allowed_values is not None else None,
            )
            for attribute in pdm_class.attributes
        ],
        ncm_references=[
            NcmReferenceItem(codes=list(reference.codes), rule=reference.rule) for reference in pdm_class.ncm_references
        ],
    )
