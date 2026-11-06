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
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Alias:
    id: str
    pattern: tuple[str, ...]
    replacement: tuple[str, ...]


# Padrões mais longos primeiro: VALV ESF precisa vencer VALV.
ALIASES: tuple[Alias, ...] = (
    # VALV ESF 2" AISI 316 NPT: válvula esfera. Não diz se o corpo é forjado ou fundido.
    Alias("valvula_esfera", ("VALV", "ESF"), ("VALVULA", "ESFERA")),
    Alias("valvula_esfera", ("VALVULA", "ESF"), ("VALVULA", "ESFERA")),
    # VALV GLOBO, VALV. BORBOLETA: o tipo da válvula continua decidindo a classe.
    Alias("valvula", ("VALV",), ("VALVULA",)),
    # ELEMENTO FILTRANTE AR vira FILTRO AR. Sem o tipo, FILTRO sozinho não é nome completo e a
    # classificação fica sem classe, com os filtros como candidatos.
    Alias("elemento_filtrante", ("ELEMENTO", "FILTRANTE"), ("FILTRO",)),
)
