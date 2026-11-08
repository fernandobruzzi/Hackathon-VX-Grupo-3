# Análise de mercado

Cadastro e saneamento de materiais industriais. Fontes consultadas em 5 nov. 2026.

Este documento separa três tipos de número, e o pitch deve manter a mesma separação:

- **Medido:** saída do nosso pipeline no kit sintético do desafio. É reproduzível com os comandos indicados.
- **Fonte:** número publicado por terceiros, com link. Quando a fonte é um fornecedor, isso está dito.
- **Premissa:** estimativa nossa, com o raciocínio. Precisa ser validada antes de virar argumento de venda.

## Resumo

| Número | O que mostra | Tipo |
|---|---|---|
| **10,8% da base** | 2.536 dos 23.554 materiais do kit estão em 1.124 propostas de unificação | Medido |
| **5% a 15%** | Faixa típica de itens duplicados em um cadastro de MRO não saneado, numa mesma planta | Fonte ([I.M.A.][ima]) |
| **US$ 26 mi** | Capital de giro liberado em uma mineradora com cinco minas, eliminando estoque excedente, obsoleto e duplicado | Fonte, fornecedor ([Verdantis][verdantis-mining]) |
| **67,9%** | Fatia da receita líquida da indústria brasileira gerada por empresas com 500 ou mais pessoas, o nosso cliente-alvo | Fonte ([IBGE, PIA-Empresa 2024][ibge-pia]) |
| **US$ 18,6 bi** | Mercado global de gestão de dados mestres (MDM) em 2025, crescendo cerca de 16% ao ano | Fonte ([Fortune Business Insights][fbi-mdm]) |

Em uma frase: grandes indústrias acumulam, em décadas de ERP, cadastros de materiais com duplicidades e dados fiscais errados. Isso prende capital em estoque, gera compras repetidas e expõe a empresa a erro fiscal. As alternativas atuais são caras e lentas, ou não impedem que o erro volte a entrar.

## 1. Problema e quem sofre com ele

O cadastro de materiais é o catálogo de tudo que a empresa compra e estoca: peças de reposição, EPIs, consumíveis de manutenção (MRO). Em empresas com várias plantas e muitos anos de ERP, o mesmo item é cadastrado várias vezes, com descrições diferentes, unidades inconsistentes e NCM ausente ou errado.

**O que o kit do desafio mostra (medido)**, nos 23.554 registros da Serra Azul:

| Problema | Registros | % da base | Como medir |
|---|---|---|---|
| Materiais em grupos propostos de unificação | 2.536 (1.124 propostas) | 10,8% | [Rodada de 8/11](evidence/batch-final.json) |
| Propostas de unificação com divergência de NCM entre os itens | 265 | – | [Rodada de 8/11](evidence/batch-final.json) |
| NCM ausente | 1.173 | 5,0% | `vx-back normalization-report` |
| Unidade de embalagem sem fator de conversão | 978 | 4,2% | `vx-back normalization-report` |

O kit é sintético, mas foi construído para reproduzir os problemas de uma base real (ver `data/desafio01/LEIA-ME.md`). A taxa de duplicidade medida fica dentro da faixa que o mercado relata para bases reais, o que dá coerência ao exemplo.

**Quem sofre:**

- **Time de cadastro:** recebe pedidos em texto livre, sem padrão, e precisa decidir sozinho se o item já existe.
- **Manutenção e almoxarifado:** a peça existe no estoque com outro código, não é encontrada, e a máquina fica parada esperando uma compra nova.
- **Compras:** compra de novo o que já tem, perde poder de negociação por item espalhado em vários códigos.
- **Fiscal:** NCM errado leva a tributo errado e a risco de multa.
- **Controladoria:** capital de giro preso em estoque duplicado e obsoleto.

**Quanto custa (fontes):**

- Duplicidade típica de **5% a 15% dos itens** dentro de uma planta, e semelhança entre plantas de até 25% em empresas com várias unidades ([I.M.A.][ima]). Outros fornecedores relatam faixas parecidas: 5% a 7% das compras de MRO são duplicadas por cadastro impreciso ([Verdantis][verdantis-stats]); 10% a 20% dos materiais em operações com mais de US$ 100 mi em estoque de MRO ([Verusen][verusen-dup]). Nenhuma dessas fontes é acadêmica.
- Em mineração, uma empresa liberou **cerca de US$ 26 mi** de capital de giro em cinco minas ([Verdantis][verdantis-mining]), e uma mineradora de carvão australiana economizou **US$ 11 mi no primeiro ano** ([IBM][ibm-coal]). Os dois casos são publicados pelos próprios fornecedores.
- A Gartner estima perda média de **US$ 12,9 mi por ano** por organização com dados de baixa qualidade ([Gartner, via Verato][gartner]). É uma estimativa de 2020, feita com clientes de referência de fornecedores. Serve como ordem de grandeza, não como número preciso.

**Por que o NCM pesa mais agora:**

- Na importação, o erro de NCM na declaração gerava multa de 1% do valor aduaneiro, mínimo de R$ 500 (art. 711 do Regulamento Aduaneiro), mesmo sem prejuízo ao fisco ([ConJur][conjur-ncm]). Segundo análises de 2026, a LC 227/2026 substituiu essa regra por multa fixa com teto de 1% ([TaxRadar][taxradar-lc227]). **Conferir o texto oficial antes de citar no pitch.**
- Na reforma tributária, o NCM define se o item paga a alíquota padrão, reduzida ou zero de IBS e CBS, pelos anexos da LC 214/2025 ([Barbieri Advogados][barbieri-ncm]). De 2026 a 2033, todo cadastro de produtos precisa ser revisto. Um NCM errado deixa de ser só um risco de multa e passa a ser tributo pago a mais ou a menos.

## 2. Tamanho do mercado

| Camada | Estimativa | Como chegamos |
|---|---|---|
| **TAM** (global, MDM) | US$ 18,6 bi em 2025 | Fonte ([Fortune Business Insights][fbi-mdm]). As estimativas publicadas variam de US$ 5 bi a US$ 23 bi, conforme a definição de mercado. Inclui todos os domínios de dados mestres, não só materiais. |
| **SAM** (Brasil, materiais em grandes indústrias) | **R$ 400 mi por ano** | Premissa: 2.000 empresas-alvo × R$ 200 mil por ano. |
| **SOM** (3 anos) | **R$ 4 mi por ano**, ou 20 clientes | Premissa: 1% do SAM. |

**Premissas do SAM, a validar:**

- **2.000 empresas-alvo:** indústria, mineração, energia, papel e celulose e saneamento, com 500 ou mais pessoas, ERP e almoxarifado de manutenção próprio. É uma ordem de grandeza: a indústria tem 358,4 mil empresas, e as com 500 ou mais pessoas geram 67,9% da receita ([IBGE, PIA-Empresa 2024][ibge-pia]). Em 2006, o país tinha 3.566 empresas de todas as atividades com 1.000 ou mais pessoas ([IBGE, CEMPRE][ibge-cempre-2006]). **Próximo passo:** obter a contagem exata por porte e setor nas tabelas da PIA-Empresa e do CEMPRE no SIDRA.
- **R$ 200 mil por ano por cliente:** assinatura da plataforma somada ao saneamento inicial diluído no contrato. Fica bem abaixo de uma implantação de SAP MDG, estimada em cerca de US$ 944 mil só em serviços por um integrador ([EPAM][epam-mdg]). Precisa ser validada em conversa com compradores.

## 3. Concorrentes e alternativas

| Alternativa | Exemplos | Limitação para o nosso cliente |
|---|---|---|
| **MDM corporativo** | SAP MDG, Informatica, Stibo | Governa o fluxo, mas não saneia a base existente. Implantação de meses a mais de um ano e custo alto ([EPAM][epam-mdg], [SAP Licensing Experts][sap-mdg-lic]). |
| **Especialistas em MRO, globais** | Verdantis, PiLog, Verusen, Sparetech | Fortes em saneamento de MRO, mas não têm o PDM brasileiro nem as regras de NCM e da reforma tributária como núcleo. |
| **Especialistas no Brasil** | Klassmatt (Integra), desde 1999 | Concorrente mais direto: saneamento, plataforma SaaS e BPO de cadastro, com clientes como Petrobras e MRN ([Baguete][baguete-klassmatt], [Baguete, MRN][baguete-mrn]). O modelo depende muito de serviço; o preço não é público. |
| **Consultorias** | IMAM e consultorias de suprimentos | Projeto pontual de saneamento: a base volta a degradar quando o projeto acaba ([IMAM][imam-pdm]). |
| **Fazer em casa** | Time de cadastro, planilhas, regras no ERP | É a alternativa mais comum. Não escala, e a decisão de duplicidade depende de quem cadastra. |

## 4. Diferencial

1. **Uma regra para saneamento e entrada.** O mesmo motor de regras do PDM corrige a base existente (batch) e valida cada novo pedido no chat. O cliente não compra dois produtos, e o erro corrigido não volta a entrar.
2. **Precisão antes de volume.** Unir itens diferentes custa mais caro que deixar passar uma duplicidade. Nenhuma unificação é aplicada sem identidade verificada pelo PDM e sem aprovação humana, e cada proposta mostra antes, depois e a regra aplicada.
3. **Fiscal no fluxo.** Mudança de NCM sempre passa pela aprovação do fiscal. Na rodada de 8/11, 810 propostas de unificação exigiram revisão fiscal, e 265 propostas de unificação registraram divergência de NCM.
4. **Auditoria completa.** Cada alteração registra quem aprovou, quando e com qual evidência. O valor enriquecido de fontes externas guarda a fonte.
5. **Nativo do padrão brasileiro.** PDM, NCM e reforma tributária são o núcleo do produto, não uma customização.
6. **Funciona ao lado do ERP.** Propõe correções, sem substituir o ERP nem exigir migração.

## 5. Modelo de negócio

**Hipótese:** B2B, com venda consultiva para grandes indústrias.

| Componente | Cobrança | Premissa a validar |
|---|---|---|
| **Diagnóstico** | Projeto fixo e curto: roda o batch na base do cliente e entrega o relatório de duplicidades, NCM e unidades | Funciona como porta de entrada: mostra o valor com os dados do próprio cliente antes do contrato. |
| **Saneamento** | Por item saneado ou por lote | Referência de volume: um cliente da Klassmatt recebe cerca de 7 mil itens saneados por mês ([Baguete, Sonepar][baguete-sonepar]). |
| **Plataforma** | Assinatura anual por faixa de itens ativos e número de usuários | Mantém a base limpa com o chat e a fila de aprovação. |

**Canais:** venda direta para mineração, energia e siderurgia, e parcerias com integradores SAP e TOTVS.

**ROI para o pitch, ilustrativo:** uma empresa com R$ 100 mi em estoque de MRO (premissa) e 5% a 15% de itens duplicados ([I.M.A.][ima]) teria da ordem de R$ 5 mi a R$ 15 mi em estoque duplicado. Esse cálculo supõe que o valor duplicado seja proporcional à quantidade de itens. Mesmo liberando uma fração disso, o valor cobre várias vezes o contrato anual de R$ 200 mil (premissa). **As premissas de ROI ficam em [`roi-assumptions.md`](roi-assumptions.md) (#28), separadas de resultados realizados.**

## 6. Riscos

- **Dados reais são mais sujos que o kit.** É preciso medir a precisão na base de um cliente piloto antes de prometer números.
- **Ciclo de venda longo** em grandes empresas, com aprovação de TI e segurança.
- **Integração com ERP:** SAP e TOTVS exigem conectores certificados para escrita.
- **Concorrência estabelecida** (Klassmatt e SAP MDG) já presente nas contas grandes.
- **Mudança regulatória:** as regras de NCM e da reforma tributária ainda estão sendo regulamentadas, o que é um risco e também uma oportunidade.

## 7. Próximos passos até uma empresa real

1. **Validar o problema:** entrevistar 10 times de cadastro e fiscal em mineração e energia. Confirmar a dor, quem decide a compra e quanto se paga hoje.
2. **Piloto pago:** rodar o diagnóstico na base real de um ou dois clientes e medir precisão, cobertura e valor em estoque duplicado.
3. **Integração:** conector de leitura com SAP e TOTVS primeiro; escrita só via aprovação na API.
4. **Segurança e conformidade:** LGPD, implantação na nuvem do cliente quando exigido, trilha de auditoria pronta para auditoria externa.
5. **Precificação:** testar diagnóstico, saneamento e assinatura com os primeiros clientes.
6. **Parcerias:** integradores SAP e consultorias de suprimentos como canal de venda.

## Fontes

Todas acessadas em 5 nov. 2026.

- [I.M.A. Ltd., "Show me the money: an MRO inventory analysis"][ima]
- [Verdantis, caso em mineração][verdantis-mining]
- [Verdantis, estatísticas de dados mestres][verdantis-stats]
- [Verusen, duplicidade em MRO][verusen-dup]
- [IBM Services, caso de mineradora de carvão][ibm-coal]
- [Gartner, custo da baixa qualidade de dados (via Verato)][gartner]
- [IBGE, PIA-Empresa 2024][ibge-pia]
- [IBGE, CEMPRE 2006][ibge-cempre-2006]
- [Fortune Business Insights, mercado de MDM][fbi-mdm]
- [EPAM, implantação de SAP MDG][epam-mdg]
- [SAP Licensing Experts, licenciamento do SAP MDG][sap-mdg-lic]
- [Baguete, Klassmatt][baguete-klassmatt]
- [Baguete, MRN e Klassmatt][baguete-mrn]
- [Baguete, Sonepar e Klassmatt][baguete-sonepar]
- [IMAM, Padrão Descritivo de Materiais][imam-pdm]
- [ConJur, multa de 1% por erro de NCM][conjur-ncm]
- [TaxRadar, multas por erro de NCM e LC 227/2026][taxradar-lc227]
- [Barbieri Advogados, NCM e reforma tributária][barbieri-ncm]

[ima]: https://reliableplant.com/Articles/Print/3220?id=3220
[verdantis-mining]: https://www.verdantis.com/?p=44844
[verdantis-stats]: https://www.verdantis.com/?p=38174
[verusen-dup]: https://verusen.com/blog/how-ai-identifies-duplicate-mro-materials-across-complex-enterprises/
[ibm-coal]: https://www.ibm.com/downloads/cas/RKGJ762Y
[gartner]: https://verato.com/resources/gartner-dq
[ibge-pia]: https://www.dgabc.com.br/Noticia/4331086/ibge-industria-reuniu-358-4-mil-empresas-e-gerou-r-6-8-tri-de-receita-liquida-em-2024
[ibge-cempre-2006]: https://agenciadenoticias.ibge.gov.br/pt/agencia-sala-de-imprensa/13563-asi-em-2006-havia-57-milhoes-de-empresas-formais-no-pais.html?lang=pt-BR
[fbi-mdm]: https://www.fortunebusinessinsights.com/master-data-management-market-114277
[epam-mdg]: https://solutionshub.epam.com/solution/sap-mdg-implementation
[sap-mdg-lic]: https://saplicensingexperts.com/blog/sap-master-data-governance-licensing
[baguete-klassmatt]: https://www.baguete.com.br/noticias/klassmatt-revoluciona-a-gestao-de-dados-mestres
[baguete-mrn]: https://www.baguete.com.br/public/noticias/mrn-usa-klassmatt-para-sanear-cadastros
[baguete-sonepar]: https://www.baguete.com.br/noticias/sonepar-usa-klassmatt-para-sanear-cadastros
[imam-pdm]: https://blog.imam.com.br/pdm-importancia-padrao-descritivo-materiais
[conjur-ncm]: https://www.conjur.com.br/2022-out-10/analice-castor-mattos-ilegalidade-sumula-161-carf//?print=1
[taxradar-lc227]: https://taxradar.app/blog/ncm/multas-erro-ncm-2026-lc-227
[barbieri-ncm]: https://www.barbieriadvogados.com/?p=1035
