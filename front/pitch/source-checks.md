# Fontes autorizadas para o roteiro

Conferência da #28 em 5/11/2026. A análise da #27 foi entregue no
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
| 11% e correções da #31                      | Reproduzidos na versão local atual, com 887 propostas de unidade                                         | Usar 11,2% com denominador de registros e substituir todos os números após a #32                    |

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

| Afirmação                                             | Evidência atual                                     | Limite para a fala                                                   |
| ----------------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------------- |
| O batch propõe unificações e correções                | Relatório completo local e hash dos arquivos        | Não demonstra aplicação, caixa ou execução final da #32              |
| O agente pede a classe de resistência e formata o PDM | Testes reais de integração API interna → MCP stdio  | Planejador por regras; não prova uso de Bedrock nem publicação       |
| O painel pode mostrar chamadas executadas             | Teste confronta o registro com chamadas MCP reais   | Confirmar no navegador integrado antes de falar em demo web validada |
| Há troca real de persona, aprovação e auditoria       | Ainda depende dos ensaios e integrações             | Não usar permissões simuladas do front como prova                    |
| Há dashboard financeiro realizado                     | A tela da main importa mocks                        | Não usar seus números como medição                                   |
| Há ferramenta NCM e enriquecimento integrados         | PRs #67 e #69 ainda são rascunhos nesta conferência | Fora do roteiro base da main; só acrescentar após merge e validação  |

Fontes locais dessa matriz: `mcp/tests/test_conversation_flow.py`,
`mcp/vx_materials_mcp/chatbot/agent.py`, `front/src/lib/auth.tsx` e
`front/src/features/dashboard/DashboardPage.tsx`, no commit da medição.
O smoke atual verifica apenas saúde da API; não é ensaio de ponta a ponta.
