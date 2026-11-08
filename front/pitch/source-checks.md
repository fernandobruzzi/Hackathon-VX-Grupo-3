# Fontes autorizadas para o roteiro

Conferência externa histórica da #28 em 5/11/2026. Os registros de legislação,
IBGE e fornecedores abaixo preservam aquela data; não foram consultados novamente
nesta integração documental. Atualização de escopo local em 7/11/2026. A análise da #27 foi entregue no
[PR #65](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/65).
Este registro decide o que pode entrar na fala; não transforma hipóteses de
[market.md](market.md) em resultados ou reescreve a entrega da #27.

## Tratamento dos cinco pontos levantados pela análise de mercado

| Ponto                                       | Resultado da conferência                                                                                 | Decisão para os cinco minutos                                                                       |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| “Multa de 1% por NCM”                       | O texto oficial confirma revogação e regras com escopo específico; não comprova essa frase genérica      | Não citar percentual de multa nem contabilizar economia fiscal                                      |
| R$ 400 milhões/ano de mercado               | A conta `2.000 × R$ 200 mil` é aritmética de hipóteses                                                   | Usar recorte oficial de empresas; receita potencial fica como sensibilidade, fora da fala principal |
| US$ 26 milhões Verdantis, caso IBM e 5%–15% | São alegações atribuídas a fornecedores/consultoria na #27; não constituem avaliação independente do MVP | Omitir da fala principal e do cálculo do ROI                                                        |
| R$ 100 milhões de estoque MRO               | Não existe cliente ou medição que sustente essa entrada aqui                                             | Manter somente como hipótese explícita no cenário ilustrativo                                       |
| Cobertura e propostas da #317 | Lote integral de 8/11 com 23.554 registros e 16.721 propostas | Mostrar propostas e aplicações da amostra separadamente |

## Legislação: o que o texto oficial sustenta

A [LC 227/2026, art. 181, II e III](https://www2.camara.leg.br/legin/fed/leicom/2026/leicomplementar-227-13-janeiro-2026-798657-normaatualizada-pl.html)
revoga o art. 84 da MP 2.158-35/2001 e o art. 69 da Lei 10.833/2003. O art. 182
disciplina efeitos. O texto também acrescenta à LC 214/2025 o art. 341-G, que
trata de obrigações acessórias de IBS/CBS. Seu inciso XIX e § 7º preveem 100 UPF
por informação e limites específicos, com piso de 50 UPF e referência a 1% da operação.

Isso não autoriza descrever toda incorreção de NCM como uma multa fixa nova ou
aplicar a mesma conta a qualquer cadastro. O roteiro fica em “conferência fiscal
e revisão humana”, sem valor de multa, ganho tributário ou afirmação de que o
produto garante conformidade. Qualquer alegação adicional exige conferência de
hipótese, período e enquadramento pelo Fiscal. O ROI ilustrativo exclui multas.

## IBGE: recorte reproduzível

Fonte primária: [PIA-Empresa, SIDRA 10452](https://sidra.ibge.gov.br/tabela/10452).
A página do SIDRA retornou 403 nesta sessão; a API oficial respondeu com os dados.

- [Metadados](https://servicodados.ibge.gov.br/api/v3/agregados/10452/metadados):
  variável `630`, número de empresas; série nova com referência 2024.
- [Consulta executada](https://servicodados.ibge.gov.br/api/v3/agregados/10452/periodos/2024/variaveis/630?localidades=N1%5Ball%5D&classificacao=9117%5B99735%2C99736%2C99737%5D%7C319%5B7830%5D):
  Brasil `N1`, classificação `319`, categoria `7830` = 500 ou mais pessoas;
  tipo de indústria `9117`: total `99735`, extrativas `99736`, transformação `99737`.
- Resultado: **2.036 = 67 + 1.969 empresas**, respectivamente.
- [Resposta preservada](evidence/ibge-pia-2024-500-plus.json), com data e URL.

Não adicionar o total às suas duas parcelas. Não misturar empresas com unidades
locais. Não inferir quantidade de compradores a partir de participação na receita.
Energia e saneamento precisam de recortes próprios; este dado não valida o universo
comercial multissetorial da #27, o percentual elegível ou o preço anual.

## Casos de fornecedores

As referências herdadas são [Verdantis, caso em mineração](https://www.verdantis.com/?p=44844),
[IBM, caso de mineradora](https://www.ibm.com/downloads/cas/RKGJ762Y) e
[I.M.A., artigo sobre estoque MRO](https://reliableplant.com/Articles/Print/3220?id=3220).
Esses endereços não puderam ser relidos nesta sessão. Os valores da #27 não foram
reconfirmados aqui e não são usados como evidência do nosso ROI.

Se forem retomados após acesso ao original, a redação precisa começar por
“segundo o fornecedor...” ou “segundo a consultoria...”, preservando unidade,
período, ações incluídas e população. Não transportar resultados de um projeto
completo de estoques para o efeito isolado do nosso cadastro. Para os cinco
minutos atuais, a decisão é omitir os casos em vez de repetir números sem contexto.

## Produto demonstrável e limites

Esta matriz descreve o código local integrado em `homologacao`, sem afirmar
execução remota ou ensaio humano. A rodada do batch de 8/11 está identificada
por commit, job e hashes na evidência da #317.

| Afirmação                                                     | Evidência local integrada                                                                             | Limite para a fala                                                                                                            |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| O batch propõe unificações e correções | [Rodada local de 8/11](evidence/batch-final.json) | Usar as contagens por tipo e separar a amostra aplicada da economia |
| O Agent pede campos, formata o PDM e busca similares          | `mcp/tests/test_conversation_flow.py` confronta chamadas MCP reais                                    | Busca depende de índice/caso; sem banco falha explicitamente; não prova Bedrock                                               |
| Há sessões reais da aplicação, pedidos, aprovação e auditoria | `api/tests/test_demo_switch.py`, `test_authenticated_approvals.py`, `test_orders.py` e `test_chat.py` | Código local integrado (#200/#171/#180); Cognito/HTTPS e ensaio de navegador na AWS permanecem pendentes                      |
| O dashboard lê dados persistidos                              | `api/tests/test_dashboard.py`; `docs/dashboard.md`                                                    | API distingue proposta/aplicação; economia realizada e precisão independente ficam indisponíveis sem evidência                |
| Há resolução manual de pendências                             | `api/tests/test_manual_reviews.py` (#211)                                                             | Produz proposta sujeita à aprovação, não aplicação direta                                                                     |
| Há consistência NCM e enriquecimento com fonte                | `docs/ncm.md`, `api/tests/test_enrichment_flow.py` (#210)                                             | Integração local; fonte NCM oficial atualizada #131 e refresh externo MCP #134 permanecem pendentes; não garante conformidade |

O smoke possui modos `health`, `local`, `flow` e `authenticated`, documentados
em [devops.md](../../docs/devops.md). `health` só verifica saúde; `local` inclui
chat/MCP; `flow` exercita o fluxo local com personas, batch, aprovação e auditoria;
`authenticated` usa HTTPS e um cookie jar de sessão real. A existência desses
modos não comprova sua execução no ambiente da apresentação. O reset da #34
existe em [demo.md](../../docs/demo.md), com proteção `DEMO_MODE=true`; o ensaio
remoto e a conferência do estado escolhido continuam pendentes.
