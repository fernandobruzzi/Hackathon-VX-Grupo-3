"""Leitura do catálogo pelas views autorizadas, com a credencial mcp_reader."""

from sqlalchemy import Engine, bindparam, text

from vx_materials_mcp.security import INVENTORY_FINANCIAL_VIEW, INVENTORY_VIEW

_MATERIAL_COLUMNS = """
    c.id::text AS id, c.material_code, c.status, c.original_description_long, c.pdm_description,
    c.manufacturer, c.manufacturer_reference,
    t.material_code AS target_code, t.status AS target_status, t.id::text AS target_id,
    i.proposed_class_id, i.extracted_attributes, i.candidate_identity_key
"""
_FROM = """
    FROM mcp_search_index i
    JOIN mcp_catalog c ON c.id = i.material_id
    LEFT JOIN mcp_catalog t ON t.id = c.active_code_target
"""


class CatalogRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def indexed(self, version: str) -> int:
        query = text("SELECT count(*) FROM mcp_search_index WHERE normalization_version = :version")
        with self._engine.connect() as connection:
            return connection.execute(query, {"version": version}).scalar_one()

    def by_identity(self, key: str, version: str) -> list[dict]:
        query = text(
            f"SELECT {_MATERIAL_COLUMNS}, 1.0 AS rank {_FROM} "
            "WHERE i.normalization_version = :version AND i.candidate_identity_key = :key"
        )
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(query, {"version": version, "key": key}).mappings()]

    def full_text(self, words: list[str], version: str, class_id: str | None, limit: int) -> list[dict]:
        """Full-text do PostgreSQL com qualquer um dos termos, ordenado por ts_rank_cd."""
        if not words:
            return []
        query = text(
            f"SELECT {_MATERIAL_COLUMNS}, ts_rank_cd(i.search_vector, q) AS rank {_FROM}, "
            "to_tsquery('simple', :terms) q "
            "WHERE i.normalization_version = :version AND i.search_vector @@ q "
            "AND (CAST(:class_id AS text) IS NULL OR i.proposed_class_id = :class_id) "
            "ORDER BY rank DESC, c.material_code LIMIT :limit"
        )
        terms = " | ".join(f"'{word}'" for word in dict.fromkeys(words) if "'" not in word)
        params = {"terms": terms, "version": version, "class_id": class_id, "limit": limit}
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(query, params).mappings()]

    def nearest(self, vector: list[float], version: str, class_id: str | None, limit: int) -> list[dict]:
        """Vizinhos por similaridade de cosseno no pgvector."""
        literal = "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
        query = text(
            f"SELECT {_MATERIAL_COLUMNS}, 1 - (i.embedding <=> CAST(:vector AS vector)) AS rank {_FROM} "
            "WHERE i.normalization_version = :version AND i.embedding IS NOT NULL "
            "AND (CAST(:class_id AS text) IS NULL OR i.proposed_class_id = :class_id) "
            "ORDER BY i.embedding <=> CAST(:vector AS vector), c.material_code LIMIT :limit"
        )
        params = {"vector": literal, "version": version, "class_id": class_id, "limit": limit}
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(query, params).mappings()]

    def inventory(self, material_ids: list[str], view: str, center_codes: frozenset[str]) -> dict[str, list[dict]]:
        if view not in (INVENTORY_VIEW, INVENTORY_FINANCIAL_VIEW):
            raise ValueError(f"View de estoque nao autorizada: {view}")
        if not material_ids or not center_codes:
            return {}
        extra = ", unit_price, total_value" if view == INVENTORY_FINANCIAL_VIEW else ""
        query = text(
            f"SELECT material_id::text AS material_id, center_code, quantity, unit{extra} FROM {view} "
            "WHERE material_id::text IN :ids AND center_code IN :centers ORDER BY center_code"
        ).bindparams(bindparam("ids", expanding=True), bindparam("centers", expanding=True))
        result: dict[str, list[dict]] = {}
        with self._engine.connect() as connection:
            params = {"ids": material_ids, "centers": sorted(center_codes)}
            for row in connection.execute(query, params).mappings():
                item = {"center_code": row["center_code"], "quantity": str(row["quantity"]), "unit": row["unit"]}
                if extra:
                    item |= {"unit_price": str(row["unit_price"]), "total_value": str(row["total_value"])}
                result.setdefault(row["material_id"], []).append(item)
        return result
