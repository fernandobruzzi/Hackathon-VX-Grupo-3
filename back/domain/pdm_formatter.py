"""Formatação da descrição padrão do PDM (regras gerais 1 e 2)."""

from collections.abc import Mapping

from domain.contracts import PdmClass


def format_description(pdm_class: PdmClass, item_name: str, attributes: Mapping[str, str]) -> str:
    """Monta `ITEM; ATRIBUTO: VALOR; ...` na ordem do PDM, com os atributos informados."""
    parts = [item_name]
    parts += [f"{a.name}: {attributes[a.name]}" for a in pdm_class.attributes if a.name in attributes]
    return "; ".join(parts)
