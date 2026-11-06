"""Contagens do snapshot original e das propostas, limitadas ao tenant e aos centros da sessão."""

from collections import Counter
from decimal import Decimal

from sqlalchemy import func, select

from domain.contracts import FieldStatus
from repositories.normalization import get_normalization_repository
from vx_materials_api.db.models import Dataset, MaterialInventorySnapshot, MaterialMaster, SanitizationProposal
from vx_materials_api.errors import ApiProblem
from vx_materials_api.schemas.metrics import DashboardMetrics, FinancialMetrics, ProposalCounts, QualityCounts
from vx_materials_api.security.rbac import require_permission
from vx_materials_api.services.approval_service import exact_sum


def metrics(db, identity, *, view="quality", dataset_id=None):
    require_permission(identity, "metrics:financial" if view == "executive" else "metrics:quality")
    snapshot = MaterialInventorySnapshot
    scoped = (
        snapshot.tenant_id == identity.tenant_id,
        snapshot.center_code.in_(identity.center_codes),
    )
    visible_dataset = select(snapshot.id).where(*scoped, snapshot.dataset_id == Dataset.id).exists()
    datasets = select(Dataset.id).where(Dataset.tenant_id == identity.tenant_id, visible_dataset)
    if dataset_id is not None:
        datasets = datasets.where(Dataset.id == dataset_id)
    selected = db.scalar(datasets.order_by(Dataset.imported_at.desc(), Dataset.id.desc()).limit(1))
    if selected is None:
        raise ApiProblem(404, "NOT_FOUND", "Nenhum dataset importado disponível no seu escopo.")

    # Só os campos de qualidade do registro bruto: esta consulta não carrega preços ou valores.
    ranked = (
        select(
            snapshot.raw_record["STATUS"].astext.label("status"),
            snapshot.raw_record["NCM"].astext.label("ncm"),
            snapshot.raw_record["UNIDADE_MEDIDA"].astext.label("unit"),
            func.row_number().over(partition_by=snapshot.material_id, order_by=snapshot.source_line).label("row"),
        )
        .join(MaterialMaster, MaterialMaster.id == snapshot.material_id)
        .where(*scoped, snapshot.dataset_id == selected, MaterialMaster.tenant_id == identity.tenant_id)
        .subquery()
    )
    originals = db.execute(select(ranked.c.status, ranked.c.ncm, ranked.c.unit).where(ranked.c.row == 1)).all()
    normalizer = get_normalization_repository()
    counts = Counter(status for status, _, _ in originals)
    before = QualityCounts(
        materials_total=len(originals),
        active=counts["ATIVO"],
        blocked=counts["BLOQUEADO"],
        obsolete=counts["OBSOLETO"],
        missing_ncm=sum(not (ncm or "").strip() for _, ncm, _ in originals),
        noncanonical_unit=sum(
            normalizer.normalize_unit(unit).status != FieldStatus.CANONICAL for _, _, unit in originals
        ),
    )
    # Uma proposta com qualquer membro fora do escopo não pode contribuir nem para as contagens.
    material_centers = {}
    for material_id, center in db.execute(
        select(snapshot.material_id, snapshot.center_code)
        .join(MaterialMaster, MaterialMaster.id == snapshot.material_id)
        .where(
            snapshot.tenant_id == identity.tenant_id,
            snapshot.dataset_id == selected,
            MaterialMaster.tenant_id == identity.tenant_id,
        )
    ):
        material_centers.setdefault(str(material_id), set()).add(center)
    allowed = {key for key, centers in material_centers.items() if centers <= identity.center_codes}
    statuses = Counter()
    for status, members in db.execute(
        select(SanitizationProposal.status, SanitizationProposal.members).where(
            SanitizationProposal.tenant_id == identity.tenant_id,
            SanitizationProposal.changeset["schema_version"].astext == "proposal-v1",
            SanitizationProposal.changeset["dataset_id"].astext == str(selected),
        )
    ):
        if (
            isinstance(members, list)
            and members
            and all(
                isinstance(member, dict)
                and isinstance(member.get("material_id"), str)
                and member["material_id"] in allowed
                for member in members
            )
        ):
            statuses[status] += 1
    result = DashboardMetrics(
        dataset_id=selected,
        before=before,
        pipeline=ProposalCounts(
            proposals_total=sum(statuses.values()),
            pending=statuses["PENDING"],
            applied=statuses["APPLIED"],
            rejected=statuses["REJECTED"],
            stale=statuses["STALE"],
        ),
    )
    # Precisão/recall exigem uma amostra rotulada independente. Aprovar não prova acerto.
    # O snapshot posterior será publicado pela #33; mudanças na master não o substituem.
    if view == "executive":
        values = db.scalars(select(snapshot.total_value).where(*scoped, snapshot.dataset_id == selected)).all()
        total = Decimal(0)
        for value in values:
            if value is not None:
                total = exact_sum(total, value)
        result.financial = FinancialMetrics(
            inventory_book_value=format(total, "f") if all(value is not None for value in values) else None,
            assumptions=[
                "Valor contábil do estoque original dos centros autorizados; dados sintéticos do desafio.",
                "Unificar códigos conserva valor de estoque e não comprova economia realizada.",
                "Economia estimada indisponível sem premissas quantitativas registradas.",
            ],
        )
    return result
