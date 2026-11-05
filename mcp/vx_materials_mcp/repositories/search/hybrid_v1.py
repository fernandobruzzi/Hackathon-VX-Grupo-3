"""Busca híbrida: identidade exata e full-text, reordenados pela comparação de atributos.

`ranking_score` só ordena. O que diz se é o mesmo item é `identity_verified`, que segue a regra
geral 10 do PDM; e mesmo assim a unificação de cadastro existentes só acontece por aprovação.
"""

from dataclasses import dataclass, field

from domain.contracts import ClassificationInput, PdmCatalog
from domain.identity import compare_attributes, partial_identity_key
from domain.pdm_validator import validate_pdm
from repositories.candidates.tokens_v1 import tokens
from vx_materials_mcp.security import INVENTORY_PERMISSION, Caller, inventory_view

_TEXT_CANDIDATES = 50
_TEXT_SCORE_CEILING = 0.9
_CONFLICT_PENALTY = 0.5


@dataclass(frozen=True)
class SearchQuery:
    query: str
    pdm_class_id: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    limit: int = 5


class HybridV1SearchRepository:
    name = "hybrid_v1"

    def __init__(
        self, catalog, pdm_catalog: PdmCatalog, classifier, extractor, index_version: str, caller, embedder=None
    ):
        self._catalog = catalog
        self._pdm = pdm_catalog
        self._classifier = classifier
        self._extractor = extractor
        self._version = index_version
        self._caller: Caller | None = caller
        self._embedder = embedder

    def search(self, query: SearchQuery) -> dict:
        classification = None if query.pdm_class_id else self._classifier.classify(ClassificationInput(query.query))
        class_id = query.pdm_class_id or classification.pdm_class_id
        if class_id is None:
            # "filtro X" pode ser filtro de óleo, ar ou combustível. Em classes de referência isso não
            # importa: fabricante e referência bastam para identificar o item.
            class_id = self._reference_class(classification.candidate_class_ids, query)
        pdm_class = self._pdm.classes.get(class_id) if class_id else None
        attributes = dict(query.attributes)
        key = None
        missing: list[str] = []
        if pdm_class is not None:
            extracted = self._extractor.extract(pdm_class, query.query)
            attributes = {**{n: a.value for n, a in extracted.attributes.items()}, **attributes}
            validation = validate_pdm(self._pdm, class_id, attributes, item_name=self._item(pdm_class))
            key = validation.identity_key or partial_identity_key(pdm_class, attributes)
            missing = [m.name for m in validation.missing_attributes]

        rows = {row["id"]: row for row in self._catalog.by_identity(key, self._version)} if key else {}
        for row in self._similar_rows(query, attributes, class_id):
            rows.setdefault(row["id"], row)

        candidates = [self._candidate(row, pdm_class, attributes, key, missing) for row in rows.values()]
        candidates.sort(key=lambda c: (-c["ranking_score"], c["material_code"]))
        candidates = candidates[: max(1, min(query.limit, 20))]
        self._attach_inventory(candidates)
        for candidate in candidates:
            candidate.pop("_inventory_id")
        return {
            "match_status": self._status(candidates),
            "pdm_class_id": class_id,
            "query_attributes": attributes,
            "index_version": self._version,
            "candidates": candidates,
        }

    def _similar_rows(self, query: SearchQuery, attributes: dict, class_id: str | None) -> list[dict]:
        """Candidatos por texto, com nota normalizada abaixo da identidade exata."""
        text_rows = self._catalog.full_text(
            tokens(" ".join([query.query, *attributes.values()])), self._version, class_id, _TEXT_CANDIDATES
        )
        best = max((row["rank"] for row in text_rows), default=0) or 1
        return [{**row, "rank": row["rank"] / best * _TEXT_SCORE_CEILING} for row in text_rows]

    def _reference_class(self, candidate_ids: tuple[str, ...], query: SearchQuery) -> str | None:
        """A única classe candidata de referência em que o texto traz fabricante e referência."""
        found = []
        for class_id in candidate_ids:
            pdm_class = self._pdm.classes[class_id]
            extracted = self._extractor.extract(pdm_class, query.query).attributes
            values = {name: value.value for name, value in extracted.items()} | query.attributes
            if partial_identity_key(pdm_class, values):
                found.append(class_id)
        return found[0] if len(found) == 1 else None

    @staticmethod
    def _item(pdm_class) -> str | None:
        return pdm_class.item_names[0] if len(pdm_class.item_names) == 1 else None

    def _candidate(self, row: dict, pdm_class, attributes: dict, key: str | None, missing: list[str]) -> dict:
        verified = bool(key) and row["candidate_identity_key"] == key
        same_class = pdm_class is not None and row["proposed_class_id"] == pdm_class.id
        their = row["extracted_attributes"] or {}
        conflicts, matching = compare_attributes(pdm_class, attributes, their) if same_class else ([], 0)
        matching_names = [n for n in attributes if n in their and n not in conflicts] if same_class else []
        pending = [] if verified else [f"ATRIBUTO_AUSENTE: {name}" for name in missing]
        target = None
        inventory_id = row["id"]
        if row["status"] == "BLOQUEADO":
            if row["target_code"] and row["target_status"] == "ATIVO":
                target, inventory_id = row["target_code"], row["target_id"]
            else:
                pending.append("BLOQUEADO_SEM_DESTINO_VALIDO")
        elif row["status"] == "OBSOLETO":
            pending.append("OBSOLETO_NAO_REUTILIZAR")
        score = 1.0 if verified else float(row["rank"])
        if conflicts:
            score *= _CONFLICT_PENALTY
        if verified and pdm_class is not None:
            match_type = (
                "EXACT_MANUFACTURER_REFERENCE"
                if pdm_class.identity_mode.value == "MANUFACTURER_REFERENCE"
                else "EXACT_IDENTITY"
            )
        else:
            match_type = "TEXT_SIMILARITY"
        return {
            "material_code": row["material_code"],
            "status": row["status"],
            "active_code_target": target,
            "description": row["pdm_description"] or row["original_description_long"],
            "match_type": match_type,
            "identity_verified": verified,
            "ranking_score": round(score, 4),
            "matching_attributes": matching_names,
            "conflicts": conflicts,
            "pending_checks": pending,
            "inventory": [],
            "_inventory_id": inventory_id,
        }

    def _attach_inventory(self, candidates: list[dict]) -> None:
        """Estoque só dos centros do usuário. Preço e valor só com a permissão financeira."""
        caller = self._caller
        if caller is None or INVENTORY_PERMISSION not in caller.permissions:
            for candidate in candidates:
                candidate["pending_checks"].append("ESTOQUE_NAO_AUTORIZADO")
            return
        ids = [candidate["_inventory_id"] for candidate in candidates]
        stock = self._catalog.inventory(ids, inventory_view(caller), caller.center_codes)
        for candidate in candidates:
            candidate["inventory"] = stock.get(candidate["_inventory_id"], [])

    @staticmethod
    def _status(candidates: list[dict]) -> str:
        reusable = [
            c for c in candidates if c["identity_verified"] and (c["status"] == "ATIVO" or c["active_code_target"])
        ]
        if reusable:
            return "EXISTING_FOUND"
        return "REVIEW_REQUIRED" if candidates else "NO_MATCH"
