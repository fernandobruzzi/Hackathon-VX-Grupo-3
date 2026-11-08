"""Recuperação RAG pelas views MCP: filtros de tenant/centro/dataset precedem ranking e limite."""

from sqlalchemy import bindparam, text

from domain.contracts import RagMaterial, RagScope
from repositories.candidates.tokens_v1 import tokens
from vx_materials_mcp.security import INVENTORY_PERMISSION, inventory_view


class RagRepository:
    def __init__(self, connection, caller, version):
        self.connection, self.caller, self.version = connection, caller, version

    def retrieve(
        self,
        query: str,
        class_id: str | None,
        scope: RagScope,
        limit: int,
        *,
        vector: list[float] | None,
        require_embedding: bool,
    ) -> list[RagMaterial]:
        if INVENTORY_PERMISSION not in self.caller.permissions:
            raise ValueError("Consulta de estoque não autorizada")
        if scope.tenant_id != self.caller.tenant_id or not scope.center_codes <= self.caller.center_codes:
            raise ValueError("Escopo RAG não autorizado")
        params = {
            "tenant": scope.tenant_id,
            "centers": sorted(scope.center_codes),
            "class_id": class_id,
            "version": self.version,
            "limit": min(limit, 50),
            "require_embedding": require_embedding,
        }
        inventory_sql = (
            "SELECT DISTINCT s.center_code FROM " + inventory_view(self.caller) + " s "
            "WHERE s.material_id = c.id AND s.tenant_id = c.tenant_id AND s.center_code IN :centers "
            "AND s.dataset_id = (SELECT id FROM mcp_datasets WHERE tenant_id = c.tenant_id "
            "ORDER BY imported_at DESC, id DESC LIMIT 1)"
        )
        scope_sql = "c.tenant_id = CAST(:tenant AS uuid) AND c.status = 'ATIVO' AND EXISTS (" + inventory_sql + ")"
        # Índice antigo ou com fonte desatualizada não serve como contexto aprovado.
        stale = text(
            "SELECT 1 FROM mcp_catalog c LEFT JOIN mcp_search_index i ON i.material_id=c.id "
            "AND i.tenant_id=c.tenant_id AND i.normalization_version=:version AND i.source_version=c.version WHERE "
            + scope_sql
            + " AND (i.material_id IS NULL OR (CAST(:require_embedding AS boolean) AND i.embedding IS NULL)) LIMIT 1"
        ).bindparams(bindparam("centers", expanding=True))
        if self.connection.execute(stale, params).first():
            raise ValueError("INDEX_UPDATING: contexto de materiais aguarda atualização do índice")
        words = [word for word in tokens(query) if "'" not in word]
        params["terms"] = " | ".join(f"'{word}'" for word in sorted(words))
        ranking = "ts_rank_cd(i.search_vector, to_tsquery('simple', :terms))"
        predicate = "i.search_vector @@ to_tsquery('simple', :terms)" if words else "FALSE"
        if vector is not None:
            params["vector"] = "[" + ",".join(str(float(value)) for value in vector) + "]"
            ranking = "1 - (i.embedding <=> CAST(:vector AS vector))"
            predicate = "i.embedding IS NOT NULL"
        sql = text(
            "SELECT c.material_code, c.version, c.pdm_description, c.original_description_long, c.pdm_class_id, "
            "ARRAY(" + inventory_sql + ") AS center_codes, "
            "c.attributes, c.ncm, c.ncm_review_status, i.proposed_class_id, i.extracted_attributes, "
            f"{ranking} AS rank FROM mcp_catalog c JOIN mcp_search_index i ON i.material_id=c.id "
            "AND i.tenant_id=c.tenant_id WHERE " + scope_sql + " AND i.normalization_version=:version "
            "AND i.source_version=c.version AND (CAST(:class_id AS text) IS NULL "
            "OR coalesce(c.pdm_class_id,i.proposed_class_id)=:class_id) AND "
            + predicate
            + " ORDER BY (c.pdm_class_id IS NOT NULL) DESC, (c.ncm_review_status='APPROVED') DESC NULLS LAST, "
            "rank DESC, c.material_code LIMIT :limit"
        ).bindparams(bindparam("centers", expanding=True))
        result = []
        for row in self.connection.execute(sql, params).mappings():
            approved = row["pdm_class_id"] is not None
            result.append(
                RagMaterial(
                    scope.tenant_id,
                    frozenset(row["center_codes"]),
                    row["material_code"],
                    row["version"],
                    row["pdm_description"] or row["original_description_long"] or "",
                    row["pdm_class_id"] or row["proposed_class_id"],
                    dict(row["attributes"] or {}) if approved else dict(row["extracted_attributes"] or {}),
                    row["ncm"],
                    "APPROVED_MASTER" if approved else "INDEX_PROPOSAL",
                    row["ncm_review_status"] == "APPROVED",
                    float(row["rank"]),
                )
            )
        return result
