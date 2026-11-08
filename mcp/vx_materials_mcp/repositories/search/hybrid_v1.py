"""Busca híbrida: identidade exata e full-text, reordenados pela comparação de atributos.

`ranking_score` só ordena. O que diz se é o mesmo item é `identity_verified`, que segue a regra
geral 10 do PDM; e mesmo assim a unificação de cadastro existentes só acontece por aprovação.
"""

from dataclasses import dataclass, field

from domain.contracts import AnalyzedMaterial, ClassificationInput, MaterialRecord, PdmCatalog
from domain.identity import compare_attributes, item_name_review_reasons, partial_identity_key, resolve_item_name
from domain.identity_decision import decide_identity
from domain.material_code_request import explicit_material_code
from domain.pdm_validator import validate_pdm
from pipelines.search_index import analyze_search_candidate
from repositories.batch_repository import SearchSource
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
    item_name: str | None = None


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
        code = explicit_material_code(query.query, allow_bare=True)
        if code and not query.attributes and not query.pdm_class_id and not query.item_name:
            rows = self._catalog.by_code(code, self._version)
            candidates = [self._candidate(row, None, None, []) for row in rows]
            for candidate in candidates:
                # Seleção de um registro por código não é comprovação de identidade para unificação.
                candidate["match_type"] = "EXACT_MATERIAL_CODE"
            self._attach_inventory(candidates)
            for candidate in candidates:
                candidate.pop("_inventory_id")
            return {
                "match_status": self._status(candidates),
                "pdm_class_id": None,
                "query_attributes": {},
                "index_version": self._version,
                "candidates": candidates,
            }
        classification = self._classifier.classify(ClassificationInput(query.query))
        class_id = query.pdm_class_id or classification.pdm_class_id
        if class_id is None:
            # "filtro X" pode ser filtro de óleo, ar ou combustível. Em classes de referência isso não
            # importa: fabricante e referência bastam para identificar o item.
            class_id = self._reference_class(classification.candidate_class_ids, query)
        pdm_class = self._pdm.classes.get(class_id) if class_id else None
        attributes = dict(query.attributes)
        key = None
        missing: list[str] = []
        requested = None
        if pdm_class is not None:
            extracted = self._extractor.extract(pdm_class, query.query)
            attributes = {**{n: a.value for n, a in extracted.attributes.items()}, **attributes}
            item_name, name_review = self._item(pdm_class, classification)
            if query.item_name is not None:
                item_name, name_review = query.item_name, ()
            if query.item_name is not None and query.item_name not in pdm_class.item_names:
                raise ValueError("Nome do item desconhecido para a classe PDM")
            validation = validate_pdm(self._pdm, class_id, attributes, item_name=item_name)
            key = validation.identity_key or partial_identity_key(pdm_class, attributes)
            missing = [m.name for m in validation.missing_attributes]
            requested = AnalyzedMaterial(
                MaterialRecord("", "ATIVO", query.query),
                classification.pdm_class_id or class_id,
                item_name,
                attributes,
                key,
                review_reasons=name_review,
            )

        rows = {row["id"]: row for row in self._catalog.by_identity(key, self._version)} if key else {}
        for row in self._similar_rows(query, attributes, class_id):
            rows.setdefault(row["id"], row)

        candidates = [self._candidate(row, pdm_class, requested, missing) for row in rows.values()]
        match_status = self._status(candidates)
        # A apresentação nunca pode esconder a única identidade reutilizável.
        candidates.sort(key=lambda c: (not self._reusable(c), -c["ranking_score"], c["material_code"]))
        candidates = candidates[: max(1, min(query.limit, 20))]
        self._attach_inventory(candidates)
        for candidate in candidates:
            candidate.pop("_inventory_id")
        return {
            "match_status": match_status,
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
    def _item(pdm_class, classification) -> tuple[str | None, tuple[str, ...]]:
        matched = tuple(e.matched_name for e in classification.evidence if e.class_id == pdm_class.id)
        return resolve_item_name(pdm_class, matched), item_name_review_reasons(pdm_class, matched)

    def _candidate(self, row: dict, pdm_class, requested: AnalyzedMaterial | None, missing: list[str]) -> dict:
        same_class = pdm_class is not None and row["proposed_class_id"] == pdm_class.id
        attributes = requested.attributes if requested else {}
        their = row["extracted_attributes"] or {}
        review = []
        verified = False
        if same_class:
            record = MaterialRecord(
                row["material_code"],
                row["status"],
                row["original_description_long"] or "",
                manufacturer=row.get("manufacturer") or "",
                reference=row.get("manufacturer_reference") or "",
                version=row.get("material_version", 1),
            )
            approved = row.get("approved_class_id") is not None or row.get("approved_attributes")
            current = MaterialRecord(
                record.code,
                record.status,
                (row.get("pdm_description") or record.description) if approved else record.description,
                manufacturer=record.manufacturer,
                reference=record.reference,
                version=record.version,
            )
            candidate = analyze_search_candidate(
                SearchSource(
                    current, row.get("approved_class_id"), row.get("approved_attributes") or {}, record.description
                ),
                self._pdm,
                self._classifier,
                self._extractor,
                row["proposed_class_id"],
                their,
                row["candidate_identity_key"],
            )
            their = candidate.attributes
            decision = decide_identity(self._pdm, requested, candidate)
            verified = bool(requested.identity_key) and decision.status == "SAME_MATERIAL"
            if decision.status != "SAME_MATERIAL":
                review.extend(decision.reasons)
        conflicts, matching = compare_attributes(pdm_class, attributes, their) if same_class else ([], 0)
        matching_names = [n for n in attributes if n in their and n not in conflicts] if same_class else []
        pending = [] if verified else [f"ATRIBUTO_AUSENTE: {name}" for name in missing]
        pending.extend(dict.fromkeys(review))
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
    def _reusable(candidate: dict) -> bool:
        return bool(
            (candidate["identity_verified"] or candidate.get("match_type") == "EXACT_MATERIAL_CODE")
            and (candidate["status"] == "ATIVO" or candidate["active_code_target"])
        )

    @classmethod
    def _status(cls, candidates: list[dict]) -> str:
        if any(cls._reusable(candidate) for candidate in candidates):
            return "EXISTING_FOUND"
        return "REVIEW_REQUIRED" if candidates else "NO_MATCH"
