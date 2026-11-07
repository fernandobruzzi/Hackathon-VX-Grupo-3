# Gabarito documental de NCM — todos os grupos (v2)

Esta versão cobre **23.554 cadastros**, organizados sequencialmente pelos **15 grupos cadastrados** e pelas **80 famílias descritivas**. As 15 colunas de origem foram preservadas. O escopo do gabarito é NCM; os demais campos, inclusive o grupo cadastrado, não receberam alvo de saneamento.

| Situação documental | Cadastros |
|---|---:|
| NCM único sustentado pelas características disponíveis | 13.932 |
| NCM original equivalente ao alvo | 12.090 |
| NCM original preenchido diferente do alvo | 1.148 |
| NCM original ausente, com alvo definido | 694 |
| Características insuficientes: revisão técnica necessária | 9.622 |

A cobertura de NCM único é **59,1492%**. Incorretos e ausentes somam **1.842 cadastros**, ou **13,2214% dos pontuáveis** e **7,8203% da base completa**. Esses percentuais não estimam o erro dos 9.622 pendentes. Manter a entrada sem saneamento acerta 12.090/13.932 = **86,7786% dos pontuáveis**.

## Arquivos e uso

| Arquivo | Conteúdo |
|---|---|
| [base_sem_gabarito.csv](base_sem_gabarito.csv) | Entrada do saneamento: todos os registros, 15 campos originais e três identificadores |
| [base_com_gabarito.csv](base_com_gabarito.csv) | Mesmas linhas, ordem e IDs; acrescenta alvo, ação, evidência, regra e pendência |
| `grupos/01_FIX01.csv` a `grupos/15_SOB01.csv` | Gabaritos de consulta por grupo, com IDs e campos de decisão; os campos originais completos estão nas bases consolidadas |
| [resumo_grupos.csv](resumo_grupos.csv) | Cobertura, situação original, quantidades e valores por grupo cadastrado |
| [resumo_familias.csv](resumo_familias.csv) | Mesmas medidas para cada uma das 80 famílias, incluindo as sem NCM único |
| [sequencia_revisao.json](sequencia_revisao.json) | Ordem dos 15 grupos, famílias cobertas, contagens de alvos e pendências |
| [criterios_documentais.json](criterios_documentais.json) | Catálogo dos identificadores de regra, motivação e candidatos observados |
| [referencia_ncm.csv](referencia_ncm.csv) | Descrição da nomenclatura para todos os alvos e candidatos utilizados |
| [manifesto.json](manifesto.json) | Versão, fontes, limites, verificações e hashes |

Os CSVs usam UTF-8 com BOM, vírgula e finais de linha CRLF. Importar códigos e NCM como texto; vazio significa null. O NCM original permanece na entrada porque a tarefa é saneá-lo. **Não enviar ao saneador a base com gabarito, os arquivos de grupo ou as colunas derivadas de decisão.**

Unir resultados por `ID_BENCHMARK`. Para NCM, avaliar somente `ELEGIVEL_BENCHMARK_NCM=true`, comparando os oito dígitos de `NCM_GABARITO`. Aceitar `7318.15.00` como equivalente a `73181500`: remover apenas pontos e espaços e exigir oito dígitos, sem letras, truncamento ou preenchimento de zeros. Código preenchido inválido é incorreto quando há alvo documental; não vira ausente.

Reportar separadamente preservação dos corretos, correção dos incorretos e preenchimento dos ausentes, por família e grupo. Nos pendentes, a ação esperada é `REVISAO_MANUAL`, com a informação necessária em `PENDENCIA_TECNICA`; **NCM vazio não é resposta correta de classificação**. Não somar casos pendentes ao denominador da acurácia de oito dígitos. Também medir a capacidade de encaminhar corretamente esses casos à revisão.

## Critérios da revisão

Cada grupo foi processado em sequência: FIX01, MAN01, ROL01, VED01, TRA01, VAL01, TUB01, ELE01, INS01, EPI01, SOL01, FER01, LUB01, FIL01 e SOB01. Dentro do grupo, foram consideradas todas as famílias presentes, inclusive produtos cadastrados no grupo de outra família. O grupo ERP organiza a entrega; não determina o NCM esperado.

Os alvos documentais são derivados da descrição e de características discriminantes, antes da comparação com o NCM de entrada. Não foram adotados o NCM mais frequente, o grupo ERP ou o PDM isolado como verdade. `FAMILIA_GABARITO` é uma organização descritiva pelo substantivo do produto e abreviações equivalentes; não é alvo fiscal nem correção automática do grupo de mercadoria. Parafusos, válvulas e anéis mantêm os nomes de família da v1; as demais famílias usam substantivo normalizado em maiúsculas.

Exemplos de decisões e limites:

- **Fixadores:** tipo e material/classe técnica distinguem porcas, arruelas e parafusos; barra roscada não herda automaticamente o código do parafuso. As decisões de parafusos, válvulas e anéis preservam integralmente a v1.
- **Mangueiras:** reforço, presença de terminais, material e pressão de ruptura podem mudar o item. Pressão de trabalho baixa não determina a ruptura; reforço misto não é tratado como somente metal. PVC reforçado exige verificar também o limite de pressão de 27,6 MPa.
- **Rolamentos e conexões:** tipo de rolamento, capacidade quando exigida, material, construção moldada/forjada e ligação são características discriminantes. Diâmetro nominal não prova diâmetro interior da conexão maleável.
- **Tubos:** material, costura, dimensões e revestimento são necessários conforme o desdobramento; não usar código antigo que inexiste na referência adotada.
- **Elétricos:** tensão do circuito é distinta de tensão da bobina. Cabos exigem informação de conexão; contatores sem tensão do circuito permanecem pendentes.
- **EPI, correias e lubrificantes:** biqueira/solado não provam material do cabedal; perfil de correia não prova composição; viscosidade não demonstra proporção de óleo de petróleo.
- **Peças:** aplicação em máquina não basta quando há código próprio ou desdobramento construtivo. Braço de suspensão de caminhão e eixo de transmissão de redutor recebem análise da função própria. Componentes genéricos sem construção/material suficientes permanecem pendentes.
- **Filtros:** distinguir fluido e circuito. A aplicação em escavadeira hidráulica não transforma filtro de ar em filtro hidráulico. Elemento filtrante exige confirmar apresentação como aparelho, parte ou material.

`NCM_CANDIDATOS_REVISAO` contém hipóteses **condicionais e não exaustivas**, separadas por `|`, que não são alvos aceitos. Em 2.056 pendentes existe um `PREFIXO_NCM_SUSTENTADO` com fundamento documental. `COMPATIBILIDADE_PREFIXO` é apenas uma comparação auxiliar: `COMPATIVEL_NO_PREFIXO` não significa NCM correto. O alvo de oito dígitos continua vazio e a ação permanece revisão. Não calcular acurácia exata a partir de candidatos ou prefixos.

O catálogo de regras agrupa critérios; quando uma regra genérica cobre peças distintas, a justificativa e a pendência específicas estão em cada registro. A evidência é um trecho literal da descrição original. Este é um gabarito documental, **sem validação fiscal independente**, inspeção física ou certificados completos. Um saneador que replique as mesmas regras de rotulagem não constitui avaliação independente dessas regras.

## Comparabilidade e repetições

A [v1](../v1/README.md) fica congelada. Os **6.271 IDs, alvos, elegibilidades, situações e ações anteriores** foram preservados; os outros **17.283 registros** ampliam o universo. O identificador deriva do SHA-256 do Excel de origem, da linha original e do código do material.

`GRUPO_PARTICAO` reúne a mesma descrição longa após normalizar acento/caixa/espaços, o mesmo código de material ou o mesmo fabricante + referência preenchidos e não genéricos. O agrupamento foi recalculado sobre a base completa: **22.651 grupos**, nenhum com alvos conflitantes. Quatro registros da v1 mudaram de ID de grupo por ampliação do componente; seus IDs individuais e alvos permanecem iguais. Em eventual treino/teste, manter cada grupo inteiro em uma única partição. Nenhuma partição automática foi criada.

## Quantidades e valores

Os resumos separam número de cadastros de `ESTOQUE_ATUAL`. Para os incorretos pontuáveis, o estoque cadastrado soma 16.908; nos ausentes pontuáveis, 12.151. Essas somas misturam unidades de medida e **não representam unidades físicas equivalentes**.

O valor do estoque afetado é calculado **registro a registro**: `ESTOQUE_ATUAL × PRECO_MEDIO_UNITARIO`, somando depois. Incorretos: **R$ 20.348.498,05**; ausentes: **R$ 3.552.545,49**; total: **R$ 23.901.043,54**. É valor de estoque associado a problemas cadastrais documentais, não prejuízo tributário, valor recuperado ou saving realizado. Não há estimativa monetária de erro para os pendentes. Estes valores não medem ganho de tempo ou custo operacional.

## Referência e vigência

A origem oficial é o [Classif/Siscomex](https://portalunico.siscomex.gov.br/classif/#/sumario#secaoXV). O download direto foi bloqueado pela rede (403). A referência disponível foi a [reprodução pública fixada por commit](https://github.com/iricardofernandes/horizon/blob/d2e511ed405cffe4e9364ba831d55f34c6345135/knowledge/data/ncm-table.json.gz), declarada vigente em **29/09/2026**, Resolução Gecex nº 926/2026. A cópia auxiliar e os hashes estão no manifesto. Todos os alvos e candidatos existem nessa referência; **não foi confirmada atualização posterior até 07/11/2026**.
