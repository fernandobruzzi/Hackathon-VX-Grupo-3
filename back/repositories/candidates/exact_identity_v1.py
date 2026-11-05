"""Candidatos com a mesma chave de identidade: a regra geral 10 do PDM, sem aproximação."""

from collections import defaultdict

from domain.contracts import AnalyzedMaterial, CandidateGroup, MatchType, PdmCatalog

# Só ativos entram: obsoleto não é reutilizado, e bloqueado já tem seu destino ou está em revisão.
ELIGIBLE_STATUS = "ATIVO"
EXACT_SCORE = 1.0


class ExactIdentityV1CandidateRepository:
    name = "exact_identity_v1"

    def find(self, materials: list[AnalyzedMaterial], catalog: PdmCatalog) -> list[CandidateGroup]:
        groups: dict[str, list[str]] = defaultdict(list)
        for material in materials:
            if material.identity_key and material.record.status == ELIGIBLE_STATUS:
                groups[material.identity_key].append(material.record.code)
        return [
            CandidateGroup(tuple(sorted(codes)), MatchType.EXACT_IDENTITY, True, EXACT_SCORE)
            for _, codes in sorted(groups.items())
            if len(codes) > 1
        ]
