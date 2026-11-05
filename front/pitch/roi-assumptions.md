# Premissas de ROI

Versão de trabalho da [#28](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/28), em 5/11/2026.
O MVP ainda não mediu economia financeira em uma empresa. Todos os valores comerciais
e operacionais dos cenários abaixo são **hipóteses**, em reais nominais, sem impostos
ou desconto a valor presente. Não constituem previsão de retorno nem resultado do kit.

## 1. Quatro tipos de informação

| Tipo                     | Significado                                                               | Uso na fala                                           |
| ------------------------ | ------------------------------------------------------------------------- | ----------------------------------------------------- |
| Medição local preliminar | Resultado reproduzível no kit, com versão e arquivos identificados        | Pode ser mostrado como proposta; atualizar após a #32 |
| Fonte externa            | Informação publicada por terceiro, com recorte, data e origem             | Não atribuir ao nosso produto                         |
| Hipótese                 | Entrada escolhida para explorar um cenário, ainda sem validação comercial | Dizer explicitamente que é hipotética                 |
| Estimativa calculada     | Saída de uma fórmula aplicada às hipóteses                                | Apresentar junto às hipóteses e ao que foi excluído   |

A quantidade de itens com códigos repetidos **não informa** o valor do estoque
excedente. O estoque dos códigos de um mesmo item pode atender demanda legítima
em centros diferentes. Unificar códigos não libera dinheiro por si só.

## 2. O que foi medido no kit

Rodada somente de leitura no commit `d11f13529f3436672a2145922e8d8509dede160d`,
com os algoritmos e hashes registrados em [batch-preview.json](evidence/batch-preview.json).
São números preliminares para o roteiro, não a execução final da #32.

| Indicador                                              | Resultado               | Interpretação permitida                                                                                   |
| ------------------------------------------------------ | ----------------------- | --------------------------------------------------------------------------------------------------------- |
| Registros de materiais de entrada                      | 23.554                  | Dimensão do kit                                                                                           |
| Materiais envolvidos em grupos propostos de unificação | 2.629; 11,2% da entrada | `2.629 / 23.554 × 100 = 11,1616%`; não é percentual de estoque recuperável                                |
| Propostas de unificação                                | 1.147                   | Identidade confirmada pelo algoritmo do PDM; não é precisão medida por especialistas nem aprovação humana |
| Unificações com revisão fiscal indicada                | 258                     | Divergência de NCM entre membros; não equivale a 258 infrações ou multas                                  |
| Propostas `PDM_CORRECTION`                             | 7.202                   | Descrição e/ou grupo de mercadoria propostos                                                              |
| Propostas `UNIT_CORRECTION`                            | 887                     | Valor atualizado nesta rodada; substitui a contagem inicial de 628 da #31                                 |
| Total de propostas desses três tipos                   | 9.236                   | `1.147 + 7.202 + 887`; não é número de materiais distintos                                                |
| Materiais com alguma correção proposta                 | 7.780                   | Pode haver sobreposição com os grupos de unificação                                                       |
| NCM ausente no original                                | 1.173; 5,0%             | Ausência, sem afirmar vigência ou correção dos demais NCMs                                                |
| Unidade de embalagem sem fator conhecido               | 978                     | Pendência de normalização; não converter automaticamente                                                  |

A rodada de relatório não aplicou mudanças e não mediu redução de compras,
tempo de cadastro, estoque, multas ou caixa. Os campos de correção somam 6.923
descrições, 542 grupos e 887 unidades: um material pode ter mais de um campo.
Não somar esses campos como se fossem materiais únicos.

Reprodução na raiz, depois de `uv sync --all-packages`:

```bash
uv run vx-back sanitize-report data/desafio01/01_base_materiais.csv --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx
uv run vx-back normalization-report data/desafio01/01_base_materiais.csv
```

No Windows, use `$env:PYTHONUTF8 = "1"` antes dos comandos. Na rodada final,
registrar o commit, hashes, configuração, manifesto/job, saídas e data. Se os
números mudarem, substituir a tabela, o arquivo de evidência e a fala em conjunto.

## 3. Modelo econômico ilustrativo

Horizonte: primeiro ano de um cliente hipotético. A assinatura de R$ 200 mil
é apenas uma hipótese de preço, não proposta comercial validada. O custo de
implantação está separado da assinatura para não desaparecer do cálculo.

| Entrada                                         | Símbolo | Hipótese comum aos cenários | Como validar em um piloto                                                                           |
| ----------------------------------------------- | ------- | --------------------------- | --------------------------------------------------------------------------------------------------- |
| Estoque MRO elegível, a custo                   | `S`     | R$ 100 milhões              | Conciliar inventário, centros e avaliação contábil; não usar preço de venda                         |
| Pedidos de cadastro por mês                     | `Q`     | 2.000                       | Contar eventos do fluxo real, sem duplicar reaberturas                                              |
| Tempo humano antes                              | `t0`    | 20 min/pedido               | Amostra cronometrada comparável, incluindo retrabalho                                               |
| Tempo humano depois                             | `t1`    | 12 min/pedido               | Incluir conferência, exceções e revisão humana                                                      |
| Custo econômico da hora                         | `c`     | R$ 100/h                    | Confirmar custo e uso alternativo com Controladoria                                                 |
| Custo anual evitável de manutenção do estoque   | `h`     | 15%                         | Separar espaço, seguro, obsolescência e custo de capital; excluir despesas que não caem             |
| Fração média do ano em que a redução já ocorreu | `w`     | 50%                         | Hipótese de implementação gradual; substituir por fluxo mensal observado                            |
| Assinatura anual                                | `P`     | R$ 200 mil                  | Validar disposição a pagar e escopo contratual                                                      |
| Infraestrutura, consultas e operação adicional  | `I`     | R$ 24 mil/ano               | Medir uso e suporte incremental; excluir tempos já contados em `t1` e itens incluídos na assinatura |
| Integração, treinamento e implantação           | `C0`    | R$ 50 mil no primeiro ano   | Orçamento do piloto                                                                                 |

O valor `S` é **premissa**, não estoque real de cliente nem valor do kit.
A proporção monetária elegível abaixo não vem dos 11,2% de registros nem dos
5%–15% citados por consultorias. São denominadores diferentes.

Fórmulas, com percentuais em fração e tempo em minutos:

```text
L = S × f × r                         # capital liberável uma única vez
H = 12 × Q × (t0 − t1) / 60 × a       # horas aproveitáveis por ano
B_capacidade = H × c                  # valor econômico; não é automaticamente caixa
B_estoque = L × h × w                 # despesa econômica evitável no primeiro ano
B_econômico = B_capacidade + B_estoque
C_ano1 = P + I + C0
C_recorrente = P + I
ROI_econômico_ano1 = (B_econômico − C_ano1) / C_ano1
```

`f` é a fração do **valor** do estoque comprovadamente excedente e elegível após
análise de demanda e criticidade; `r` é a fração efetivamente realizável; `a` é
a fração das horas poupadas que se consegue aproveitar. As entradas ainda
precisam ser medidas. Sem evidência de valor excedente, considerar `f = 0`.

### Sensibilidade

Todas as entradas e saídas desta tabela são hipotéticas. Custos do ano 1:
`R$ 200.000 + R$ 24.000 + R$ 50.000 = R$ 274.000`; recorrentes: R$ 224.000/ano.
Os [cenários calculados](evidence/roi-scenarios.json) preservam as entradas e as saídas decimais.

| Cenário | `f` | `r` | `a`  | Capital `L`, uma vez | Horas `H`/ano | Capacidade/ano | Estoque/ano 1 | Benefício econômico/ano 1 | ROI econômico/ano 1 |
| ------- | --- | --- | ---- | -------------------- | ------------- | -------------- | ------------- | ------------------------- | ------------------- |
| Baixo   | 1%  | 20% | 50%  | R$ 200 mil           | 1.600 h       | R$ 160 mil     | R$ 15 mil     | R$ 175 mil                | −36,1%              |
| Central | 2%  | 40% | 75%  | R$ 800 mil           | 2.400 h       | R$ 240 mil     | R$ 60 mil     | R$ 300 mil                | 9,5%                |
| Alto    | 3%  | 60% | 100% | R$ 1,8 milhão        | 3.200 h       | R$ 320 mil     | R$ 135 mil    | R$ 455 mil                | 66,1%               |

Exemplo central: `L = 100.000.000 × 0,02 × 0,40 = R$ 800.000`;
`H = 12 × 2.000 × 8 / 60 × 0,75 = 2.400 h`;
`B_estoque = 800.000 × 0,15 × 0,50 = R$ 60.000`;
`ROI = (300.000 − 274.000) / 274.000 = 9,4891%`.

### Caixa, capacidade e capital são separados

Não somar os R$ 800 mil de liberação única ao benefício recorrente de R$ 300 mil
como se ambos fossem lucro anual. Não contar a mesma compra evitada também
como estoque vendido ou como redução de despesa da mesma natureza.

As 2.400 horas representam capacidade operacional. Para virarem caixa, seria
preciso comprovar, por exemplo, redução de horas extras ou serviço terceirizado.
Mesmo o componente de estoque só entra no caixa quando a despesa deixa de ocorrer.
Se apenas os R$ 60 mil desse componente fossem caixa comprovado no ano 1,
o retorno operacional em caixa, excluindo a liberação de capital, seria
`(60.000 − 274.000) / 274.000 = −78,1%`. Portanto, o cenário central não prova
viabilidade financeira de um contrato.

Payback exige fluxos mensais reais: é o primeiro mês em que o caixa acumulado,
incluindo implantação, pagamentos e eventuais liberações únicas, se torna não
negativo. Não há payback medido nem promessa de prazo. Multas, paralisações,
tributos recuperados e ganho de negociação estão fora deste modelo por falta
de evidência; adicionar somente com atribuição e sem dupla contagem.

## 4. Mercado e verificações de fonte

O [IBGE, PIA-Empresa 2024, tabela 10452](https://sidra.ibge.gov.br/tabela/10452)
registra **2.036 empresas industriais com 500 ou mais pessoas ocupadas** no
Brasil: 67 extrativas e 1.969 de transformação. A variável é número de empresas,
não plantas/unidades locais. A [resposta oficial e os filtros](evidence/ibge-pia-2024-500-plus.json)
ficam versionados. A tabela não demonstra uso de ERP, estoque MRO, interesse
ou orçamento; tampouco cobre energia e saneamento como esse mesmo recorte industrial.

Assim, a hipótese da #27 de `2.000 × R$ 200 mil = R$ 400 milhões/ano` não virou
receita observada nem SAM comprovado. Uma sensibilidade apenas industrial seria:

```text
mercado anual hipotético = 2.036 empresas × q elegível × R$ 200.000/ano
q = 25% → R$ 101,8 milhões/ano
q = 50% → R$ 203,6 milhões/ano
q = 100% → R$ 407,2 milhões/ano
```

`q` e preço são hipóteses; 100% é um limite aritmético do recorte, não previsão.
Não somar energia ou saneamento sem outro recorte consistente e sem retirar
sobreposições. Na fala principal, usar o recorte de 2.036 e a proposta de um
piloto, sem anunciar R$ 400 milhões como mercado validado.

As ressalvas sobre legislação e casos de fornecedores estão em
[source-checks.md](source-checks.md). Esses casos não calibram o ROI do nosso MVP.

## 5. Evidência necessária antes de falar em resultado realizado

O piloto deve comparar uma amostra de pedidos equivalentes antes/depois, com
tempos de revisão incluídos, consumo real de infraestrutura e volume atendido.
Um especialista valida as propostas de identidade; rejeições, falsos positivos
e itens fora de cobertura permanecem no denominador. Controladoria confirma
despesa evitada e capital liberado; Fiscal confirma qualquer efeito tributário.

Antes do congelamento, atualizar a medição com a #32 e vincular os números ao
job e aos artefatos da execução final. Capturas ilustrativas e os mocks do
dashboard não comprovam economias nem alterações aplicadas.
