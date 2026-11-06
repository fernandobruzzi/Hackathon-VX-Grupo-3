"""Comando `vx-demo`: prepara o estado da demonstração e volta a ele depois de cada ensaio.

Aprovar uma proposta altera materiais, consome a proposta e grava auditoria. O reset apaga o
estado operacional, recarrega o kit como veio, refaz índice e propostas e importa os pedidos.
Tudo é determinístico (identificadores derivados do kit e do conteúdo), então repetir o comando
sempre chega ao mesmo estado, conferido pela impressão digital no resumo.

Só roda com DEMO_MODE=true e com o nome do banco confirmado: ele apaga dados.
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from clients.storage import ObjectStore, get_object_store
from domain.pdm_loader import load_pdm
from pipelines.full_run import run_sanitize
from pipelines.import_orders import read_orders
from pipelines.search_index import run_index
from vx_materials_api import settings
from vx_materials_api.bootstrap import ORDERS_FILE, PDM_FILE, TENANT_ID, bootstrap
from vx_materials_api.db.models import (
    AuditLog,
    ChatSession,
    MaterialMaster,
    RegistrationOrder,
    SanitizationProposal,
    UserSso,
)
from vx_materials_api.errors import ApiError
from vx_materials_api.security.identity import Identity
from vx_materials_api.security.local_session import CENTERS
from vx_materials_api.security.permissions import PERSONA_ROLES, permissions_for
from vx_materials_api.services.order_service import import_orders as import_order_rows

# Estado operacional apagado a cada reset, em ordem compatível com as chaves estrangeiras.
# Lista explícita, sem CASCADE: uma tabela nova que dependa destas faz o reset falhar em vez de
# ser apagada sem revisão. Usuários e sessões de login ficam: o reset não desloga as personas.
OPERATIONAL_TABLES = (
    "audit_logs",
    "lot_reviews",
    "quality_snapshot_items",
    "quality_snapshots",
    "operation_requests",
    "inventory_consolidations",
    "chat_messages",
    "chat_sessions",
    "registration_orders",
    "enrichment_sources",
    "manual_reviews",
    "sanitization_proposals",
    "material_search_index",
    "batch_jobs",
    "material_inventory_snapshots",
    "materials_master",
    "datasets",
)
LOCAL_ISSUER = "local-test"
# Classe do roteiro do pitch (parafuso sextavado): propostas dela vêm primeiro na seleção.
PITCH_CLASS = "PDM001"
SELECTION_LIMIT = 300


class DemoGuardError(RuntimeError):
    """O ambiente não é de demonstração ou o banco não foi confirmado."""


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "false").lower() == "true"


def check_demo_environment(database_url: str, confirm: str | None) -> None:
    """Recusa rodar fora da demonstração ou contra um banco diferente do confirmado."""
    if not demo_mode():
        raise DemoGuardError("O reset da demo só roda com DEMO_MODE=true")
    database = make_url(database_url).database
    if not confirm or confirm != database:
        raise DemoGuardError(f"Confirme o banco que será apagado com --confirm {database}")


def wipe(engine: Engine) -> None:
    with engine.begin() as connection:
        # Espera a análise antiga terminar antes de reaproveitar IDs e revisões da carga inicial.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"search-index:{TENANT_ID}"}
        )
        connection.execute(text(f"TRUNCATE TABLE {', '.join(OPERATIONAL_TABLES)}"))


def persona_user_id(persona: str) -> uuid.UUID:
    """Mesmo identificador que o login local cria para a persona."""
    return uuid.uuid5(TENANT_ID, persona)


def ensure_personas(engine: Engine) -> dict[str, str]:
    """Contas locais das três personas, ativas e com o papel fixo do servidor."""
    with engine.begin() as connection:
        for persona, role in PERSONA_ROLES.items():
            values = {
                "id": persona_user_id(persona),
                "tenant_id": TENANT_ID,
                "issuer": LOCAL_ISSUER,
                "subject": persona,
                "display_name": f"{persona} (teste local)",
                "roles_snapshot": [role],
                "disabled_at": None,
            }
            statement = insert(UserSso).values(values)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["issuer", "subject"],
                    set_={"roles_snapshot": [role], "disabled_at": None, "tenant_id": TENANT_ID},
                )
            )
    return {persona: str(persona_user_id(persona)) for persona in PERSONA_ROLES}


def import_orders(engine: Engine, data_dir: Path, catalog) -> dict:
    """Pedidos do kit pela mesma importação da #24, já analisados contra o PDM e o índice."""
    rows = read_orders((data_dir / ORDERS_FILE).read_bytes())
    with Session(engine) as db:
        return import_order_rows(db, TENANT_ID, catalog, rows)


def _reviewer() -> Identity:
    """Visão de quem revisa as duas áreas, só para conferir que a proposta pode ser aprovada."""
    roles = (PERSONA_ROLES["GESTOR_CADASTRO"], PERSONA_ROLES["AUDITOR_FISCAL"])
    return Identity(
        persona_user_id("GESTOR_CADASTRO"), TENANT_ID, roles, permissions_for(roles), center_codes=frozenset(CENTERS)
    )


def _summary(proposal: SanitizationProposal, item: dict) -> dict:
    return {
        "id": str(proposal.id),
        "review_path": f"/saneamento/revisao/?id={proposal.id}",
        "title": item["title"],
        "material_codes": item["material_codes"],
        "suggested_primary_code": item["suggested_primary_code"],
        "technical_review_status": proposal.technical_review_status,
        "fiscal_review_status": proposal.fiscal_review_status,
    }


def select_demo_proposals(engine: Engine, catalog) -> dict:
    """Unificações sem conflito para o roteiro: uma só técnica e uma com revisão fiscal.

    A seleção é estável: mesma ordem de classe e código a cada reset.
    """
    from vx_materials_api.services.proposal_queries import detail

    reviewer = _reviewer()
    picks: dict[str, dict | None] = {"governance": None, "fiscal": None}
    with Session(engine) as db:
        proposals = db.scalars(
            select(SanitizationProposal).where(
                SanitizationProposal.proposal_type == "MERGE", SanitizationProposal.status == "PENDING"
            )
        ).all()

        def order(proposal):
            after = proposal.changeset.get("after", {})
            codes = sorted(member.get("material_code", "") for member in proposal.members)
            return (after.get("pdm_class_id") != PITCH_CLASS, after.get("pdm_class_id") or "", codes)

        for proposal in sorted(proposals, key=order)[:SELECTION_LIMIT]:
            slot = "fiscal" if proposal.fiscal_review_status == "PENDING" else "governance"
            if picks[slot] is not None:
                continue
            try:
                item = detail(db, proposal, reviewer, catalog)
            except ApiError:
                continue
            if not item["conflicts"]:
                picks[slot] = _summary(proposal, item)
            if all(picks.values()):
                break
    return picks


def fingerprint(engine: Engine) -> dict:
    """Contagens e hash do estado que o ensaio pode alterar, sem datas nem chaves aleatórias."""
    with Session(engine) as db:
        materials = db.execute(
            select(
                MaterialMaster.material_code,
                MaterialMaster.status,
                MaterialMaster.version,
                MaterialMaster.active_code_target,
                MaterialMaster.is_canonical,
                MaterialMaster.pdm_description,
                MaterialMaster.unit,
                MaterialMaster.ncm,
                MaterialMaster.ncm_review_status,
            ).order_by(MaterialMaster.material_code)
        ).all()
        proposals = db.execute(
            select(
                SanitizationProposal.id,
                SanitizationProposal.proposal_type,
                SanitizationProposal.status,
                SanitizationProposal.technical_review_status,
                SanitizationProposal.fiscal_review_status,
                SanitizationProposal.version,
                SanitizationProposal.changeset_hash,
            ).order_by(SanitizationProposal.id)
        ).all()
        orders = db.execute(
            # Pelo id do kit: o identificador interno do pedido é gerado pelo banco.
            select(RegistrationOrder.source_order_id, RegistrationOrder.status, RegistrationOrder.version).order_by(
                RegistrationOrder.source_order_id
            )
        ).all()
        counts = {
            "materials": len(materials),
            "proposals": len(proposals),
            "pending_proposals": sum(1 for row in proposals if row.status == "PENDING"),
            "orders": len(orders),
            "audit_events": db.scalar(select(func.count()).select_from(AuditLog)),
            "chat_sessions": db.scalar(select(func.count()).select_from(ChatSession)),
        }
        for table in (
            "operation_requests",
            "inventory_consolidations",
            "batch_jobs",
            "material_search_index",
            "quality_snapshots",
        ):
            counts[table] = db.scalar(text(f"SELECT count(*) FROM {table}"))
    state = json.dumps([[list(map(str, row)) for row in rows] for rows in (materials, proposals, orders)])
    digest = hashlib.sha256((state + json.dumps(counts, sort_keys=True)).encode()).hexdigest()
    return {"sha256": digest, "counts": counts}


def reset(
    database_url: str,
    data_dir: str | Path,
    store: ObjectStore,
    pdm_workbook: str | None = None,
) -> dict:
    """Apaga o estado operacional e recria o estado inicial da demonstração."""
    directory = Path(data_dir)
    workbook = pdm_workbook or str(directory / PDM_FILE)
    engine = create_engine(database_url)
    try:
        wipe(engine)
        personas = ensure_personas(engine)
        loaded = bootstrap(directory, engine, store)
        index = run_index(workbook, database_url=database_url)
        sanitize = run_sanitize(workbook, database_url=database_url)
        catalog = load_pdm(workbook)
        orders = import_orders(engine, directory, catalog)
        picks = select_demo_proposals(engine, catalog)
        state = fingerprint(engine)
    finally:
        engine.dispose()
    return {
        "dataset_id": loaded.dataset_id,
        "personas": personas,
        "index_version": index.get("index_version"),
        "proposals_by_type": sanitize["by_type"],
        "orders_imported": orders["inserted"],
        "orders_by_status": orders["by_status"],
        "demo_proposals": picks,
        "state": state,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vx-demo", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    reset_parser = commands.add_parser("reset", help="Volta o banco ao estado inicial da demonstração")
    reset_parser.add_argument("--data-dir", default=settings.data_dir())
    reset_parser.add_argument("--pdm-workbook", default=os.environ.get("PDM_WORKBOOK_PATH"))
    reset_parser.add_argument("--confirm", help="Nome do banco que será apagado")
    commands.add_parser("status", help="Mostra a impressão digital do estado atual, sem alterar nada")
    args = parser.parse_args(argv)

    url = settings.migration_database_url()
    if args.command == "status":
        engine = create_engine(url)
        try:
            result = fingerprint(engine)
        finally:
            engine.dispose()
    else:
        try:
            check_demo_environment(url, args.confirm)
        except DemoGuardError as error:
            print(f"vx-demo: {error}", file=sys.stderr)
            return 2
        result = reset(url, args.data_dir, get_object_store(), args.pdm_workbook)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
