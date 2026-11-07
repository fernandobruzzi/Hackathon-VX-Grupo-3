"""Worker da API para aplicar políticas autorizadas e recuperar a indexação pendente."""

import argparse
import logging
import os
import signal
import threading
from pathlib import Path

from domain.pdm_loader import load_pdm
from vx_materials_api import settings
from vx_materials_api.db.session import make_engine, make_session_factory
from vx_materials_api.services.automatic_corrections import process_ready_jobs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vx-auto-correct")
    parser.add_argument("--once", action="store_true", help="Processa a fila disponível e termina")
    args = parser.parse_args(argv)
    settings.automatic_correction_mode()
    stopped = threading.Event()
    for event in (signal.SIGTERM, signal.SIGINT):
        signal.signal(event, lambda *_: stopped.set())
    engine = make_engine()
    factory = make_session_factory(engine)
    try:
        catalog = load_pdm(
            os.environ.get("PDM_WORKBOOK_PATH", str(Path(settings.data_dir()) / "03_padrao_cadastro_PDM.xlsx"))
        )
        while not stopped.is_set():
            try:
                process_ready_jobs(factory, catalog)
            except Exception as error:
                # Não registra SQL, URLs de conexão nem conteúdo de credenciais.
                logging.getLogger(__name__).error("AUTOMATION_WORKER_ERROR:%s", type(error).__name__)
                if args.once:
                    return 1
            if args.once:
                return 0
            stopped.wait(float(os.environ.get("AUTOMATIC_CORRECTION_POLL_SECONDS", "5")))
    finally:
        engine.dispose()
    return 0
