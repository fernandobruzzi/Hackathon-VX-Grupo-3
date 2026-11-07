"""Aliases técnicos inequívocos, aplicados às palavras antes da busca dos nomes do PDM.

Cada alias troca uma sequência exata de palavras (já sem acentos, caixa e conectores) por outra.
O contexto faz parte do padrão: ESF só vira ESFERA logo depois de VALV ou VALVULA, porque em
rolamentos significa ESFERAS e em outros textos pode ser outra coisa.

Só entra aqui o que tem uma única leitura na base e no PDM. Abreviações que dependem do item, como
PARAF CAB SEXTAVADA ALLEN (cabeça cilíndrica com sextavado interno), ficam de fora: na dúvida, a
classificação continua sem classe e o pedido segue para esclarecimento.

Exemplos negativos revisados, que nenhum alias deve tocar:
- ROL RIG ESF / ROLAMENTO RIGIDO ESF: ESF fora de válvula não é expandido.
- ELEMENTO sozinho (ELEMENTO DE FIXACAO, ELEMENTO AQUECEDOR): só ELEMENTO FILTRANTE vira FILTRO.
- VALVULA SEGURANCA: VALVULA já é a palavra completa e SEGURANCA não é classe do PDM.
- VALV RET e VALVULA RET: RET depois de válvula é retenção, não retentor.
- CONT fora do começo do campo: aparece cortado em descrições curtas (... TRANSPORTADORA CONT).
- VERGALHAO TENSORA: é sinônimo, não abreviação, e VERGALHAO ROSCADO é outra peça; fica sem alias.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Alias:
    id: str
    pattern: tuple[str, ...]
    replacement: tuple[str, ...]
    # Só no começo do campo: RET abre a descrição de retentores, mas VALV RET é válvula de retenção.
    at_start: bool = False
    # Não aplica logo depois destas palavras: ANEL O RING já é o nome completo.
    not_after: tuple[str, ...] = ()
    # Não apaga um indicador de sextavado interno ao expandir a abreviação externa.
    not_before: tuple[str, ...] = ()


# Padrões mais longos primeiro: VALV ESF precisa vencer VALV.
ALIASES: tuple[Alias, ...] = (
    # PARAF. SEXT e PARAF SEXTAVADO são as formas abreviadas da peça externa; INTERNO
    # explícito ganha primeiro. ALLEN e INT incompletos ficam fora da expansão externa.
    Alias("parafuso_interno", ("PARAFUSO", "SEXT", "INTERNO"), ("PARAFUSO", "SEXTAVADO", "INTERNO"), at_start=True),
    Alias("parafuso_interno", ("PARAF", "SEXT", "INTERNO"), ("PARAFUSO", "SEXTAVADO", "INTERNO"), at_start=True),
    Alias("parafuso_interno", ("PARAF", "SEXTAVADO", "INTERNO"), ("PARAFUSO", "SEXTAVADO", "INTERNO"), at_start=True),
    Alias(
        "parafuso_sextavado",
        ("PARAF", "SEXTAVADO"),
        ("PARAFUSO", "SEXTAVADO"),
        at_start=True,
        not_before=("ALLEN", "INT", "INTERNO"),
    ),
    Alias(
        "parafuso_sextavado",
        ("PARAF", "SEXT"),
        ("PARAFUSO", "SEXTAVADO"),
        at_start=True,
        not_before=("ALLEN", "INT", "INTERNO"),
    ),
    Alias(
        "parafuso_sextavado",
        ("PARAFUSO", "SEXT"),
        ("PARAFUSO", "SEXTAVADO"),
        at_start=True,
        not_before=("ALLEN", "INT", "INTERNO"),
    ),
    # COTOV e FLG iniciam conexões no kit; no meio do texto podem ser aplicação da peça.
    Alias("cotovelo", ("COTOV",), ("COTOVELO",), at_start=True),
    Alias("flange", ("FLG",), ("FLANGE",), at_start=True),
    # Erro ortográfico e ordem dos mesmos termos, sem acrescentar tipo ou aplicação.
    Alias("placa_traseira", ("PLACA", "TRASERA"), ("PLACA", "TRASEIRA"), at_start=True),
    Alias("bucha_mancal_guia", ("BUCHA", "GUIA", "MANCAL"), ("BUCHA", "MANCAL", "GUIA"), at_start=True),
    # VALV ESF 2" AISI 316 NPT: válvula esfera. Não diz se o corpo é forjado ou fundido.
    Alias("valvula_esfera", ("VALV", "ESF"), ("VALVULA", "ESFERA")),
    Alias("valvula_esfera", ("VALVULA", "ESF"), ("VALVULA", "ESFERA")),
    # VALV GLOBO, VALV. BORBOLETA: o tipo da válvula continua decidindo a classe.
    Alias("valvula", ("VALV",), ("VALVULA",)),
    # ELEMENTO FILTRANTE AR vira FILTRO AR. Sem o tipo, FILTRO sozinho não é nome completo e a
    # classificação fica sem classe, com os filtros como candidatos.
    Alias("elemento_filtrante", ("ELEMENTO", "FILTRANTE"), ("FILTRO",)),
    # Na base, as 57 descrições que começam com RET são retentores (BASL, diâmetros de eixo e
    # alojamento); as 33 com RET depois de VALV ou VALVULA são válvulas de retenção.
    Alias("retentor", ("RET",), ("RETENTOR",), at_start=True),
    # CONT abre as 28 descrições de contatores (ELE01). No meio do texto é corte de outra palavra.
    Alias("contator", ("CONT",), ("CONTATOR",), at_start=True),
    # LAMP LED: todas as 28 ocorrências são lâmpadas LED.
    Alias("lampada_led", ("LAMP", "LED"), ("LAMPADA", "LED")),
    # FILT abre os 95 filtros abreviados. Sem o tipo completo (FILT OLEO LUBR), FILTRO sozinho não é
    # nome do PDM e o item fica com os filtros como candidatos.
    Alias("filtro", ("FILT",), ("FILTRO",)),
    # O-RING sozinho (89 descrições de vedação): o nome do PDM é ANEL O-RING.
    Alias("anel_o_ring", ("O", "RING"), ("ANEL", "O", "RING"), not_after=("ANEL",)),
    # Ball valve em linhas de catálogo em inglês, como nos anexos dos pedidos SC-202600016 e
    # SC-202600463.
    Alias("valvula_esfera", ("BALL", "VALVE"), ("VALVULA", "ESFERA")),
)
