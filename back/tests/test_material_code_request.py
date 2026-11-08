"""Somente uma seleção inequívoca por código pode dispensar a identificação por descrição."""

import pytest

from domain.material_code_request import explicit_material_code


@pytest.mark.parametrize(
    "message,expected",
    [
        ("código 16031971", "16031971"),
        ("Preciso do código: 00012345.", "00012345"),
        ("código ABC-238/01", "ABC-238/01"),
        ("16031971", "16031971"),
        ("Parafuso M12x50, 10 PC", None),
        ("Referência 16031971", None),
        ("DIN 933", None),
        ("10", None),
        ("Código 12345 válvula", None),
        ("código 123 e 456", None),
    ],
)
def test_only_explicit_single_record_selection(message, expected):
    assert explicit_material_code(message, allow_bare=True) == expected


def test_numbers_in_followups_require_a_code_label():
    assert explicit_material_code("16031971") is None
    assert explicit_material_code("código 16031971") == "16031971"
