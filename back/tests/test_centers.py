import pytest

from domain.centers import split_center


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1200 - USINA DE BENEFICIAMENTO", ("1200", "USINA DE BENEFICIAMENTO")),
        (" 0010- UNIDADE  - NORTE ", ("0010", "UNIDADE - NORTE")),
        ("1200", ("1200", None)),
        ("1200 - ", ("1200", None)),
        (None, ("", None)),
    ],
)
def test_split_center(value, expected):
    assert split_center(value) == expected
