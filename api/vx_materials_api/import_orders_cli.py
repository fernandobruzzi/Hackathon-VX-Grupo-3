"""Comando `vx-import-orders`: grava os 520 pedidos do kit como pedidos importados (#24).

Roda com a credencial api_user, depois do bootstrap e do índice de busca (`docker compose run --rm batch`),
porque a checagem de duplicidade usa o índice. Repetir não duplica pedidos.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from domain.pdm_loader import load_pdm
from pipelines.import_orders import read_orders
from vx_materials_api import settings
from vx_materials_api.bootstrap import ORDERS_FILE, PDM_FILE, TENANT_ID
from vx_materials_api.db.session import make_engine
from vx_materials_api.services.order_service import import_orders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-import-orders", description="Importa os pedidos de cadastro do kit")
    parser.add_argument("--data-dir", default=settings.data_dir(), help="Pasta com os arquivos do kit")
    args = parser.parse_args(argv)
    directory = Path(args.data_dir)
    catalog = load_pdm(directory / PDM_FILE)
    rows = read_orders((directory / ORDERS_FILE).read_bytes())
    engine = make_engine()
    try:
        with Session(engine) as db:
            result = import_orders(db, TENANT_ID, catalog, rows)
    finally:
        engine.dispose()
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
