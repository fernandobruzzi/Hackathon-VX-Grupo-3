"""Correções só para materiais cuja classe é confiável: o nome do item do PDM abre a descrição.

Quando o nome da classe aparece no meio do texto, ele costuma ser um atributo (`REVESTIMENTO`,
`FLANGE`, `OLEO LUBRIFICANTE`) de um produto abreviado que o classificador não reconheceu, como
`PARAFUSO SEXT` ou `FILT`. Nesses casos, corrigir grupo ou descrição seria errar com confiança.
"""

import re
import unicodedata

from domain.contracts import (
    AnalyzedMaterial,
    CorrectionResult,
    FieldCorrection,
    FieldStatus,
    NormalizationRepository,
    PdmCatalog,
    ValidationStatus,
)
from domain.pdm_validator import validate_pdm

_REDIRECT_PREFIX = re.compile(r"^NAO UTILIZAR - USAR COD \d+\s*-\s*")
_CONNECTORS = frozenset({"DA", "DAS", "DE", "DO", "DOS"})


def _tokens(text: str) -> tuple[str, ...]:
    folded = unicodedata.normalize("NFKD", text.upper())
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    return tuple(word for word in re.findall(r"[A-Z0-9]+", plain) if word not in _CONNECTORS)


def opens_description(item_name: str, description: str) -> bool:
    """O nome do item é o começo da descrição, ignorando caixa, acentos e pontuação."""
    name = _tokens(item_name)
    return bool(name) and _tokens(_REDIRECT_PREFIX.sub("", description))[: len(name)] == name


class HeadNounV1CorrectionRepository:
    name = "head_noun_v1"

    def _alias_only(self, raw_unit: str, normalizer: NormalizationRepository) -> tuple[FieldCorrection, ...]:
        """Sem classe confiável, só a grafia da mesma unidade (PÇ, PCA, UN → PC) é corrigida.

        Nunca troca pela unidade padrão de uma classe, e embalagem sem fator continua sem conversão.
        A regra própria deixa claro para quem revisa que a classe não foi usada.
        """
        unit = normalizer.normalize_unit(raw_unit)
        if unit.status is not FieldStatus.NORMALIZED or not unit.value:
            return ()
        rule = f"{self.name}/unit.alias_without_class ({unit.rule})"
        return (FieldCorrection("UNIT_CORRECTION", "unit", unit.original, unit.value, rule),)

    def correct(
        self, material: AnalyzedMaterial, catalog: PdmCatalog, normalizer: NormalizationRepository
    ) -> CorrectionResult:
        record = material.record
        if record.status != "ATIVO":
            # Bloqueado e obsoleto não são reutilizados: corrigir só aumentaria a fila de revisão.
            return CorrectionResult((), (f"MATERIAL_NAO_ATIVO: {record.status}",))
        if material.pdm_class_id is None:
            return CorrectionResult(
                self._alias_only(record.unit, normalizer),
                ("SEM_CLASSE_CONFIAVEL: o classificador nao decidiu a classe",),
            )
        pdm_class = catalog.classes[material.pdm_class_id]
        if material.item_name is None or not opens_description(material.item_name, record.description):
            return CorrectionResult(
                self._alias_only(record.unit, normalizer),
                ("CLASSE_NAO_CONFIRMADA: o nome do item nao abre a descricao",),
            )

        corrections: list[FieldCorrection] = []
        pending: list[str] = []
        if record.group != pdm_class.group:
            corrections.append(
                FieldCorrection(
                    "PDM_CORRECTION",
                    "merchandise_group",
                    record.group or None,
                    pdm_class.group,
                    f"{self.name}/group.from_pdm_class",
                )
            )

        validation = validate_pdm(catalog, pdm_class.id, material.attributes, item_name=material.item_name)
        if validation.status is ValidationStatus.VALID and validation.formatted_description:
            if validation.formatted_description != record.description:
                corrections.append(
                    FieldCorrection(
                        "PDM_CORRECTION",
                        "description",
                        record.description or None,
                        validation.formatted_description,
                        f"{self.name}/description.pdm_format",
                    )
                )
        else:
            missing = [item.name for item in validation.missing_attributes]
            invalid = [item.name for item in validation.invalid_attributes]
            details = [
                f"faltam {', '.join(missing)}" if missing else "",
                f"invalidos {', '.join(invalid)}" if invalid else "",
            ]
            pending.append(f"DESCRICAO_FORA_DO_PADRAO: {'; '.join(d for d in details if d) or validation.status.value}")

        unit = normalizer.normalize_unit(record.unit)
        if unit.status is FieldStatus.NORMALIZED and unit.value:
            corrections.append(FieldCorrection("UNIT_CORRECTION", "unit", unit.original, unit.value, unit.rule))
        elif unit.status is FieldStatus.UNRESOLVED:
            # Embalagem (CX, CT, JG...) sem fator conhecido: nenhuma conversão automática.
            pending.append(f"UNIDADE_SEM_FATOR: {unit.original} exige fator de conversao para {pdm_class.default_unit}")
        elif unit.status is FieldStatus.MISSING:
            pending.append("UNIDADE_AUSENTE: sem unidade no cadastro")
        if unit.value and unit.value != pdm_class.default_unit:
            pending.append(f"UNIDADE_DIFERENTE_DA_CLASSE: {unit.value}, padrao da classe {pdm_class.default_unit}")
        return CorrectionResult(tuple(corrections), tuple(pending))
