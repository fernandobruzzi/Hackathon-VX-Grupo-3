"""head_noun_v1 que também confia no nome abreviado sem ambiguidade no começo da descrição.

O classificador `aliases_v2` marca com a regra `*/head.name` a classe decidida pelo nome que abre
a descrição, mesmo abreviado (`PARAF CAB SEXTAVADA`, `TAMPA PRES`, `VALV GAV`): cada abreviação é
prefixo de uma única palavra dos nomes da família, sinônimos técnicos são explícitos e qualquer
outro nome de classe no trecho devolve a dúvida. Essa classe recebe as mesmas correções que o
nome por extenso. Classe encontrada no meio do texto continua sem confiança, como no v1.

O head_noun_v1 fica registrado como alternativa literal, para auditoria e retorno.
"""

from domain.contracts import AnalyzedMaterial
from repositories.corrections.head_noun_v1 import HeadNounV1CorrectionRepository, opens_description

HEAD_RULE_SUFFIX = "/head.name"


def head_confirmed(material: AnalyzedMaterial) -> bool:
    """Classe pelo nome do item no começo da descrição, por extenso ou abreviado sem ambiguidade."""
    rule = material.classification_rule or ""
    return bool(material.item_name) and (
        rule.endswith(HEAD_RULE_SUFFIX) or opens_description(material.item_name, material.record.description)
    )


class HeadNounV2CorrectionRepository(HeadNounV1CorrectionRepository):
    name = "head_noun_v2"

    def trusted_class(self, material: AnalyzedMaterial) -> bool:
        return head_confirmed(material)
