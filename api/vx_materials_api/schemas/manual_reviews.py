"""Encaminhamento de pendência à aprovação, com origem declarada por quem revisa."""

from typing import Annotated

from pydantic import Field, StringConstraints

from vx_materials_api.schemas.proposals import Reason, StrictModel, UnitConversion

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
AttributeValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ManualReviewResolution(StrictModel):
    expected_material_version: int = Field(ge=1)
    pdm_class_id: ShortText
    item_name: ShortText
    attributes: dict[ShortText, AttributeValue] = Field(max_length=100)
    unit: ShortText
    ncm: Annotated[str, StringConstraints(max_length=32)] | None
    conversions: list[UnitConversion] = Field(default_factory=list, max_length=20)
    source: Reason
    reason: Reason
