"""Código ERP informado explicitamente, sem extrair números de medidas ou referências."""

import re

_LABEL = re.compile(
    r"(?:(?:preciso|quero|solicito)\s+(?:do\s+)?)?c[oó]digo\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{0,38}[A-Za-z0-9])\s*[.!]?",
    re.IGNORECASE,
)


def explicit_material_code(message: str, *, allow_bare: bool = False) -> str | None:
    found = _LABEL.fullmatch(message.strip())
    if found:
        return found.group(1)
    if allow_bare and re.fullmatch(r"[0-9]{6,18}", message.strip()):
        return message.strip()
    return None
