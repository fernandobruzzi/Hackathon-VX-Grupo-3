"""Comando `vx-batch-job`: cria um job de batch para rodar localmente, sem a tela do front.

Em produção, quem cria o job é a API (`POST /api/v1/batch/jobs`, #21), com o usuário autenticado.
Este atalho só funciona com APP_ENV=local e registra um operador local como solicitante.
"""

import argparse
import sys

from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert

from domain.pdm_loader import DEFAULT_PDM_VERSION
from vx_materials_api import settings
from vx_materials_api.db.models import UserSso
from vx_materials_api.db.session import make_engine

LOCAL_OPERATOR_ISSUER = "local-cli"
LOCAL_OPERATOR_SUBJECT = "batch-operator"


def create_job(engine: Engine, job_type: str = "SANITIZE", pdm_version: str = DEFAULT_PDM_VERSION) -> str:
    with engine.begin() as connection:
        latest = text("SELECT id, tenant_id FROM datasets ORDER BY imported_at DESC LIMIT 1")
        dataset = connection.execute(latest).first()
        if dataset is None:
            raise RuntimeError("Nenhum dataset carregado: rode vx-bootstrap antes")
        connection.execute(
            insert(UserSso)
            .values(
                tenant_id=dataset.tenant_id,
                issuer=LOCAL_OPERATOR_ISSUER,
                subject=LOCAL_OPERATOR_SUBJECT,
                display_name="Operador local do batch",
            )
            .on_conflict_do_nothing(index_elements=["issuer", "subject"])
        )
        user_id = connection.execute(
            select(UserSso.id).where(UserSso.issuer == LOCAL_OPERATOR_ISSUER, UserSso.subject == LOCAL_OPERATOR_SUBJECT)
        ).scalar_one()
        return str(
            connection.execute(
                text(
                    "INSERT INTO batch_jobs (tenant_id, requested_by_user_id, dataset_id, job_type, pdm_version) "
                    "VALUES (:t, :u, :d, :type, :pdm) RETURNING id"
                ),
                {"t": dataset.tenant_id, "u": user_id, "d": dataset.id, "type": job_type, "pdm": pdm_version},
            ).scalar_one()
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-batch-job", description="Cria um job de batch local")
    parser.add_argument("--type", default="SANITIZE", choices=["SANITIZE"])
    args = parser.parse_args(argv)
    if settings.app_env() != settings.LOCAL_ENV:
        raise RuntimeError("vx-batch-job só roda com APP_ENV=local; fora dele, o job nasce pela API")
    engine = make_engine()
    try:
        print(create_job(engine, args.type))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
