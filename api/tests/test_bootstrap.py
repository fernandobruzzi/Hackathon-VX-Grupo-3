import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from clients.storage import LocalObjectStore
from vx_materials_api.bootstrap import (
    REDIRECT_INCONSISTENT,
    REDIRECT_LINKED,
    BootstrapError,
    bootstrap,
    read_materials,
    resolve_redirect,
)
from vx_materials_api.db.temporary_login import temporary_login

KIT = Path(__file__).parents[2] / "data" / "desafio01"


def blocked(description, code="1"):
    return {"STATUS": "BLOQUEADO", "CODIGO_MATERIAL": code, "DESCRICAO_LONGA": description}


@pytest.mark.parametrize(
    ("row", "statuses", "expected"),
    [
        (blocked("NAO UTILIZAR - USAR COD 2 - X"), {"2": "ATIVO"}, ("2", REDIRECT_LINKED)),
        (blocked("NAO UTILIZAR - USAR COD 2 - X"), {"2": "BLOQUEADO"}, (None, REDIRECT_INCONSISTENT)),
        (blocked("NAO UTILIZAR - USAR COD 2 - X"), {"2": "OBSOLETO"}, (None, REDIRECT_INCONSISTENT)),
        (blocked("NAO UTILIZAR - USAR COD 2 - X"), {}, (None, REDIRECT_INCONSISTENT)),
        (blocked("USAR COD 1", code="1"), {"1": "BLOQUEADO"}, (None, REDIRECT_INCONSISTENT)),
        (blocked("PARAFUSO M12"), {}, (None, None)),
        ({"STATUS": "ATIVO", "CODIGO_MATERIAL": "1", "DESCRICAO_LONGA": "USAR COD 2"}, {"2": "ATIVO"}, (None, None)),
    ],
)
def test_redirects_link_only_directly_to_active_items(row, statuses, expected):
    assert resolve_redirect(row, statuses) == expected


def test_missing_column_fails_loudly():
    with pytest.raises(BootstrapError, match="colunas"):
        read_materials(b"CODIGO_MATERIAL\n1\n")


def test_repeated_code_fails_loudly():
    columns = "CODIGO_MATERIAL,DESCRICAO_CURTA,DESCRICAO_LONGA,UNIDADE_MEDIDA,NCM,FABRICANTE,"
    columns += "REFERENCIA_FABRICANTE,CENTRO,STATUS,ESTOQUE_ATUAL,PRECO_MEDIO_UNITARIO\n"
    row = "1,,,PC,,,,1100 - X,ATIVO,1,1\n"
    with pytest.raises(BootstrapError, match="repetidos"):
        read_materials((columns + row + row).encode())


@pytest.fixture(scope="module")
def loaded(migrated_url, tmp_path_factory):
    """Carrega o kit real com a credencial api_user, como em produção."""
    admin = create_engine(migrated_url)
    with admin.begin() as connection:
        connection.execute(text("TRUNCATE datasets, reference_versions, materials_master CASCADE"))
    with temporary_login(migrated_url, "api_user") as api_url:
        engine = create_engine(api_url)
        store = LocalObjectStore(tmp_path_factory.mktemp("storage"))
        first = bootstrap(KIT, engine, store)
        second = bootstrap(KIT, engine, store)
        yield first, second, store, admin
        engine.dispose()
    admin.dispose()


def scalar(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).scalar_one()


def test_all_materials_are_loaded_with_their_statuses(loaded):
    first, _, _, admin = loaded
    assert first.materials_inserted == 23554
    assert first.statuses == {"ATIVO": 20014, "BLOQUEADO": 2331, "OBSOLETO": 1209}
    with admin.connect() as connection:
        rows = dict(connection.execute(text("SELECT status, count(*) FROM materials_master GROUP BY 1")).all())
    assert rows == {"ATIVO": 20014, "BLOQUEADO": 2331, "OBSOLETO": 1209}


def test_loading_twice_changes_nothing(loaded):
    first, second, _, admin = loaded
    assert second.dataset_id == first.dataset_id
    assert second.materials_inserted == 0
    assert second.snapshots_inserted == 0
    assert scalar(admin, "SELECT count(*) FROM datasets") == 1
    assert scalar(admin, "SELECT count(*) FROM reference_versions") == 1
    assert scalar(admin, "SELECT count(*) FROM material_inventory_snapshots") == 23554


def test_book_value_matches_contract(loaded):
    _, _, _, admin = loaded
    assert scalar(admin, "SELECT sum(total_value) FROM material_inventory_snapshots") == Decimal("200874691.83")


def test_values_are_kept_exactly_as_they_came(loaded):
    _, _, _, admin = loaded
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE ncm = '84749000'") > 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE unit = 'PÇ'") == 290
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE ncm IS NULL") == 1173
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE pdm_class_id IS NOT NULL") == 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE is_canonical") == 0
    # Grupo da carga fica como original; o revisado só existe depois de uma aprovação.
    mismatched = """SELECT count(*) FROM materials_master m JOIN material_inventory_snapshots s
        ON s.material_id = m.id WHERE m.original_merchandise_group IS DISTINCT FROM
        NULLIF(s.raw_record->>'GRUPO_MERCADORIA', '')"""
    assert scalar(admin, mismatched) == 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE original_merchandise_group IS NULL") == 0
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE merchandise_group IS NOT NULL") == 0


def test_stock_points_to_its_source_line(loaded):
    first, _, _, admin = loaded
    with admin.connect() as connection:
        lines = connection.execute(
            text(
                "SELECT m.material_code, s.source_line, s.center_code, s.raw_record->>'CODIGO_MATERIAL' "
                "FROM material_inventory_snapshots s JOIN materials_master m ON m.id = s.material_id "
                "WHERE s.source_line >= 23541 ORDER BY s.source_line"
            )
        ).all()
    assert [line[0] for line in lines] == first.real_material_codes
    assert [line[1] for line in lines] == list(range(23541, 23556))
    assert all(line[0] == line[3] and line[2].isdigit() for line in lines)


def test_redirects_are_linked_or_left_for_review(loaded):
    first, _, _, admin = loaded
    assert sum(first.redirects.values()) == 234
    assert scalar(admin, "SELECT count(*) FROM materials_master WHERE active_code_target IS NOT NULL") == (
        first.redirects.get(REDIRECT_LINKED, 0)
    )
    invalid = (
        "SELECT count(*) FROM materials_master m JOIN materials_master t ON t.id = m.active_code_target "
        "WHERE t.status <> 'ATIVO'"
    )
    assert scalar(admin, invalid) == 0
    pending = f"SELECT count(*) FROM materials_master WHERE block_reason = '{REDIRECT_INCONSISTENT}'"
    assert scalar(admin, pending) == first.redirects.get(REDIRECT_INCONSISTENT, 0)


def test_manifest_records_hashes_counts_and_real_products(loaded):
    first, _, store, admin = loaded
    manifest = json.loads(store.get(first.manifest_key))
    assert manifest["dataset_id"] == first.dataset_id
    assert len(manifest["real_material_codes"]) == 15
    assert manifest["real_material_codes"][-1] == "23476944"
    files = {file["name"]: file for file in manifest["files"]}
    assert files["01_base_materiais.csv"]["rows"] == 23554
    assert files["02_pedidos_cadastro.csv"]["rows"] == 520
    for name, file in files.items():
        assert len(file["sha256"]) == 64
        assert store.get(file["object_key"]) == (KIT / name).read_bytes()
    with admin.connect() as connection:
        stored = connection.execute(text("SELECT real_material_codes, files FROM datasets")).one()
    assert stored[0] == manifest["real_material_codes"]
    assert stored[1] == manifest["files"]


def test_pdm_reference_is_registered_and_stored(loaded):
    _, _, store, admin = loaded
    assert scalar(admin, "SELECT validation_status FROM reference_versions WHERE version = 'pdm-kit-v1'") == "VALIDATED"
    assert store.get("references/pdm/pdm-kit-v1/03_padrao_cadastro_PDM.xlsx")
