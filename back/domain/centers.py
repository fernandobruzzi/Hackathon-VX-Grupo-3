"""Separa a identificação do centro sem alterar o registro original."""


def split_center(value: str | None) -> tuple[str, str | None]:
    """Preserva zeros e hífens do nome; código isolado não permite inferir nome."""
    code, _, name = (value or "").partition("-")
    return code.strip(), " ".join(name.split()) or None
