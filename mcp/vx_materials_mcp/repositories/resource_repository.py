"""Recursos consultam só views MCP e derivam tenant da identidade autenticada."""

from uuid import UUID

from sqlalchemy import Engine, bindparam, text

from vx_materials_mcp.security import FINANCIAL_PERMISSION, INVENTORY_PERMISSION, Caller, inventory_view


class ResourceRepository:
    def __init__(self, engine: Engine | None, caller: Caller | None):
        self._engine = engine
        self._caller = caller

    def _tenant(self) -> str:
        caller = self._caller
        if caller is None or "materials:read" not in caller.permissions:
            raise ValueError("Consulta de material nao autorizada")
        try:
            signed_tenant = str(UUID(caller.tenant_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Consulta de material nao autorizada") from None
        if self._engine is None:
            raise ValueError("Catalogo indisponivel")
        with self._engine.connect() as connection:
            tenant = connection.execute(
                text("SELECT tenant_id::text FROM mcp_callers WHERE id::text = :user_id AND tenant_id::text = :tenant"),
                {"user_id": caller.user_id, "tenant": signed_tenant},
            ).scalar_one_or_none()
        if tenant is None:
            raise ValueError("Consulta de material nao autorizada")
        return signed_tenant

    def material(self, code: str) -> dict:
        tenant = self._tenant()
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT id::text, material_code, status, original_description_short, "
                        "original_description_long, "
                        "pdm_description, pdm_class_id, pdm_version, attributes, manufacturer, manufacturer_reference, "
                        "unit, ncm, ncm_review_status, is_canonical FROM mcp_catalog "
                        "WHERE material_code = :code AND tenant_id::text = :tenant"
                    ),
                    {"code": code, "tenant": tenant},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("Material nao encontrado no seu escopo")
        result = dict(row)
        material_id = result.pop("id")
        result["inventory"] = self._inventory(material_id, tenant)
        return result

    def _inventory(self, material_id: str, tenant: str) -> list[dict]:
        caller = self._caller
        if INVENTORY_PERMISSION not in caller.permissions or not caller.center_codes:
            return []
        financial = FINANCIAL_PERMISSION in caller.permissions
        columns = "center_code, quantity, unit" + (", unit_price, total_value" if financial else "")
        query = text(
            f"SELECT {columns} FROM {inventory_view(caller)} WHERE material_id::text = :id "
            "AND tenant_id::text = :tenant AND center_code IN :centers "
            "AND dataset_id = (SELECT id FROM mcp_datasets WHERE tenant_id::text = :tenant "
            "ORDER BY imported_at DESC, id DESC LIMIT 1) ORDER BY center_code"
        ).bindparams(bindparam("centers", expanding=True))
        with self._engine.connect() as connection:
            rows = connection.execute(
                query, {"id": material_id, "tenant": tenant, "centers": sorted(caller.center_codes)}
            ).mappings()
            return [{key: str(value) if value is not None else None for key, value in row.items()} for row in rows]

    def require_real_material(self, code: str) -> None:
        tenant = self._tenant()
        with self._engine.connect() as connection:
            eligible = connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM (SELECT tenant_id, real_material_codes FROM mcp_datasets "
                    "WHERE tenant_id::text = :tenant ORDER BY imported_at DESC, id DESC LIMIT 1) d "
                    "JOIN mcp_catalog c ON c.tenant_id = d.tenant_id WHERE d.tenant_id::text = :tenant "
                    "AND c.material_code = :code AND jsonb_array_length(d.real_material_codes) = 15 "
                    "AND d.real_material_codes ? :code)"
                ),
                {"tenant": tenant, "code": code},
            ).scalar_one()
        if not eligible:
            raise ValueError("Codigo fora dos 15 produtos reais do manifesto autorizado")

    def evidence_for_material(self, code: str, attributes: list[str]) -> list[dict]:
        tenant = self._tenant()
        query = text(
            "SELECT e.* FROM mcp_evidence e JOIN mcp_catalog c ON c.id = e.material_id AND c.tenant_id = e.tenant_id "
            "WHERE c.material_code = :code AND e.tenant_id::text = :tenant "
            "AND e.attribute_name IN :attributes AND e.status IN ('PENDING', 'APPROVED') "
            "ORDER BY e.retrieved_at DESC, e.id"
        ).bindparams(bindparam("attributes", expanding=True))
        with self._engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    query, {"code": code, "tenant": tenant, "attributes": attributes}
                ).mappings()
            ]

    def evidence(self, source_id: str) -> dict:
        tenant = self._tenant()
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT e.id::text, c.material_code, e.attribute_name, e.proposed_value, e.source_url, "
                        "e.source_title, e.source_excerpt, e.source_page, e.retrieved_at, e.confidence_level, "
                        "e.confidence_basis, e.status FROM mcp_evidence e JOIN mcp_catalog c "
                        "ON c.id = e.material_id AND c.tenant_id = e.tenant_id "
                        "WHERE e.id::text = :id AND e.tenant_id::text = :tenant"
                    ),
                    {"id": source_id, "tenant": tenant},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("Evidencia nao encontrada no seu escopo")
        return dict(row)
