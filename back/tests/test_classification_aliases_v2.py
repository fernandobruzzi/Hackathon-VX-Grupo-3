"""aliases_v2: o nome que abre a descrição decide a classe, sem adivinhar na dúvida.

Cada caso positivo tem um contraexemplo encontrado na auditoria da base completa.
"""

from pathlib import Path

import pytest

from domain.contracts import ClassificationInput, ClassificationStatus
from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository

KIT = Path(__file__).parents[2] / "data/desafio01"


@pytest.fixture(scope="module")
def classifier():
    return get_classification_repository(load_pdm(KIT / "03_padrao_cadastro_PDM.xlsx"), "aliases_v2")


@pytest.mark.parametrize(
    ("description", "expected", "item"),
    [
        # Abreviação com uma única leitura na família e feminino de palavra da família.
        ("PARAF CAB SEXTAVADA, ROSCA:MA, BITOLA:M12", "PDM001", "PARAFUSO SEXTAVADO"),
        ("PARAF. SEXT. METRICA GROSSA M 16X40 A4-70", "PDM001", "PARAFUSO SEXTAVADO"),
        # Sinônimos técnicos e palavras fora de ordem; o nome mais longo vence.
        ("PARAFUSO HEXAGONAL INTERNO TIPO CABECA CILINDRICA ROSCA M6", "PDM002", "PARAFUSO SEXTAVADO INTERNO"),
        ("PARAFUSO ALLEN CAB SEXTAVADA ESCAREADA M12X50", "PDM002", "PARAFUSO SEXTAVADO INTERNO"),
        ("PARAFUSO INT SEXTAVADO, TIPO CABECA:ABAULADA", "PDM002", "PARAFUSO SEXTAVADO INTERNO"),
        ("ANEL ORING 32X3.5 NBR 70 SHORE A", "PDM031", "ANEL O-RING"),
        # RET depois de VALVULA só pode ser RETENCAO; GAV só pode ser GAVETA.
        ("VALV. RET, DIAMETRO NOMINAL:2,5POL, CL:150#", "PDM043", "VALVULA RETENCAO"),
        ("VALVULA GAV 800 SOLDA ENCAIXE", "PDM041", "VALVULA GAVETA"),
        # Nome de classe depois do trecho inicial é atributo, não ambiguidade.
        ("VALVULA ESFERA DIAMETRO DE 3POL, COM EXTREMIDADE FLANGE RF", "PDM040", "VALVULA ESFERA"),
        ("VALVULA RETENCAO 1/2POL 800# ACO CARBONO FORJADO A105 SOCKET WELD PISTAO", "PDM043", "VALVULA RETENCAO"),
        ("PARAFUSO SEXT, ROSCA: METRICA, REVESTIMENTO: ZINCADO BRANCO", "PDM001", "PARAFUSO SEXTAVADO"),
        # A barra faz parte do nome.
        ("FILTRO SEPARADOR AR/OLEO FABR DONALDSON, REF P475514", "PDM100", "FILTRO SEPARADOR AR/OLEO"),
        # Com terminais é a mangueira montada (o PDM separa os NCMs).
        ("MANGUEIRA HIDR C/TERMINAIS EN 853 1SN 1 POL", "PDM011", "MANGUEIRA HIDRAULICA MONTADA"),
        # Prefixo de duas famílias resolvido por outra palavra do nome.
        ("MANG HIDRAULICA MONTADA, PADRAO:EN 856 4SP", "PDM011", "MANGUEIRA HIDRAULICA MONTADA"),
    ],
)
def test_opening_name_decides_the_class(classifier, description, expected, item):
    result = classifier.classify(ClassificationInput(description))
    assert (result.status, result.pdm_class_id) == (ClassificationStatus.CLASSIFIED, expected)
    assert result.rule == "aliases_v2/head.name"
    assert [e.matched_name for e in result.evidence if e.rule.endswith("head.name")] == [item]


@pytest.mark.parametrize(
    "item",
    [
        # COM é preposição, nunca COMBUSTIVEL; o resultado não pode depender do nome mais longo vencer.
        ClassificationInput("FILTRO COM APLICACAO PERFURATRIZ"),
        # Dois nomes do PDM no começo: manto ou eixo.
        ClassificationInput("MANTO EIXO METSO N1234567"),
        # Palavra que distingue um item irmão sobra: SEPARADOR sem AR/OLEO não é FILTRO AR.
        ClassificationInput("FILTRO SEPARADOR AR DONALDSON"),
        # Prefixo de duas famílias sem outra palavra do nome.
        ClassificationInput("MANG 4POL"),
        ClassificationInput("MANG SUCCAO USO SUCCAO E DESCARGA"),
        # Descrição curta que começa com outra classe e anexo que cita outra classe.
        ClassificationInput("PORCA M12", short_description="ARRUELA LISA M12"),
        ClassificationInput("PORCA SEXTAVADA M12", attachment_text="Produto: Retentor"),
        # Nome curto continua exigindo o grupo.
        ClassificationInput("TE envio o pedido"),
    ],
)
def test_doubt_never_becomes_a_head_class(classifier, item):
    result = classifier.classify(item)
    assert result.rule != "aliases_v2/head.name"
    if result.status is ClassificationStatus.CLASSIFIED:
        # Só as regras conservadoras do aliases_v1 podem decidir, nunca o começo da descrição.
        assert not any(e.rule.endswith("head.name") for e in result.evidence)


def test_truncated_short_description_does_not_create_ambiguity(classifier):
    # A descrição curta é a longa cortada: REVESTIMENTO e FLANGE continuam sendo atributos.
    item = ClassificationInput(
        "VALVULA ESFERA 3 IN 150# ACO CARBONO FLANGEADA RF",
        short_description="VALV ESFERA 3 IN 150# ACO CARBONO FLANGE",
    )
    assert classifier.classify(item).pdm_class_id == "PDM040"


def test_attributes_still_come_from_the_original_text(classifier):
    # O alias decide a classe; a extração não lê o texto reescrito.
    result = classifier.classify(ClassificationInput("PARAF CAB SEXTAVADA M12"))
    assert result.original.description == "PARAF CAB SEXTAVADA M12"
