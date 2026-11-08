# Cliente de modelo de linguagem (#287)

O back chama modelos de linguagem por um repositório trocável, no mesmo padrão dos algoritmos
selecionáveis. O primeiro fluxo que o usa é o auditor LLM do batch (#290), descrito abaixo.

## Seleção

| Variável | Padrão | Efeito |
|---|---|---|
| `LLM_REPOSITORY` | vazio | Vazio ou `none` desliga o uso de modelo. `bedrock_v1` ou `simulated_v1`. |
| `BEDROCK_LLM_MODEL_ID` | `us.anthropic.claude-sonnet-5` | Modelo ou perfil de inferência do Bedrock. |
| `AWS_REGION` | — | Região da chamada. Com o perfil `us.`, usar `us-east-1`. |
| `LLM_TIMEOUT_SECONDS` | `30` | Timeout de leitura de cada tentativa. |
| `LLM_MAX_ATTEMPTS` | `2` | Tentativas por chamada, só para falhas transitórias. |
| `LLM_MAX_CALLS_PER_RUN` | `200` | Orçamento de tentativas por execução. |
| `LLM_MAX_TOKENS` | `4096` | Limite de tokens da resposta. |

Para trocar de modelo, basta mudar `BEDROCK_LLM_MODEL_ID` no `.env`. O padrão é o Claude Sonnet 5 pelo
perfil de inferência dos EUA, o mesmo do chat (`deployment/README.md`). O perfil encaminha a inferência
entre regiões dos EUA, e o ID simples do modelo não funciona como inferência regional em `us-east-1`.
Para usar o perfil global (`global.anthropic.claude-sonnet-5`) ou outra região, confira antes os
destinos do perfil e as SCPs da conta. Credenciais vêm da cadeia padrão do SDK da AWS (task role,
instance profile ou variáveis de ambiente) e precisam de `bedrock:InvokeModel` no perfil e nos modelos de
destino.

## Garantias

- Toda chamada pede um esquema JSON e só devolve dados que passaram nele (`jsonschema`, draft 2020-12).
- O Bedrock recebe o esquema como ferramenta, sem escolha forçada, porque modelos mais novos recusam
  `toolChoice` forçado. Resposta sem a ferramenta também é erro.
- Erros têm código estável em `LlmError.code`: `LLM_INVALID_RESPONSE`, `LLM_TRUNCATED`, `LLM_REFUSED`,
  `LLM_REQUEST_REJECTED`, `LLM_UNAVAILABLE`, `LLM_NOT_CONFIGURED` e `LLM_BUDGET_EXHAUSTED`. Quem chama
  mantém o caso pendente; nunca há sucesso fictício.
- Só limite de taxa, timeout e indisponibilidade são repetidos. Pedido recusado (acesso negado, modelo
  inválido) falha na primeira vez.
- Cada tentativa conta no orçamento. Crie um repositório por execução (job, relatório ou avaliação) com
  `get_llm_repository()`.
- O log `vx.llm` registra repositório, modelo, versão do prompt, tokens, latência e tentativas. Prompt,
  resposta e credenciais não vão para o log. O mesmo registro volta em `LlmResult.call`, para quem
  precisar guardá-lo com a sugestão.

## Simulado

`simulated_v1` não usa rede e devolve a menor resposta que o esquema aceita: nulo quando permitido,
listas vazias e só os campos obrigatórios. Testes podem fixar respostas por ferramenta, que também
passam pelo esquema. O resultado sai com `simulated=True`. API, Agent e CLI recusam iniciar com
`LLM_REPOSITORY=simulated_v1` fora de `APP_ENV=local` ou com marcadores de runtime AWS.

## Verificação

De `back/`, sem credenciais:

```bash
uv run --locked pytest tests/test_llm.py tests/test_runtime.py
```

Os testes de contrato rodam sobre todos os repositórios registrados. O Bedrock é exercitado com um stub
do `bedrock-runtime`. A chamada real depende de credenciais, região e acesso ao modelo na conta do
workshop, e ainda não foi feita.

## Auditor LLM (#290)

Com `LLM_REPOSITORY` definido, o batch (`vx-back sanitize`) roda o auditor depois das propostas de
NCM das regras. Sem a variável, nada muda e nenhum modelo é chamado. O relatório offline
`sanitize-report` nunca chama modelo.

**Seleção.** Só materiais sem proposta de NCM das regras, com o motivo da regra que não resolveu:
`NO_CLASS`, `HEAD_UNCONFIRMED` (classe sem o nome do item no começo), `NCM_MATTER_UNPROVEN`,
`NCM_SEAL_FUNCTION_UNRESOLVED` e `NCM_CODE_UNRESOLVED` (mais de um código possível). Um código único
igual ao atual não é auditado, porque não haveria mudança. Caso sem classe candidata (palavra inicial
que não abre nenhum nome do PDM) fica `SKIPPED`, sem gastar chamada.

**Entrada do modelo.** Descrições, fabricante, referência, unidade, motivo, leitura das regras e o
trecho do PDM de até seis classes candidatas: nomes, atributos com valores admitidos e referências de
NCM com a regra. O NCM atual e o gabarito nunca entram. O prompt é versionado (`llm-audit-v1`) e a
resposta segue um esquema: `ABSTER` ou `RESOLVER`, com classe, nome do item, atributos (valor, trecho
citado e base `LITERAL` ou `INFERIDO`), NCM, evidências e justificativa.

**Revalidação pelo domínio** (`llm-audit-policy-v1`). A resposta é descartada, com o motivo, quando:

| Motivo | Quando |
|---|---|
| `LLM_CLASS_NOT_CANDIDATE`, `LLM_ITEM_NAME_INVALID` | Classe fora das candidatas ou nome que a classe não tem |
| `LLM_QUOTE_NOT_FOUND` | Trecho ou evidência que não está na descrição (sem caixa nem acento) |
| `LLM_ATTRIBUTE_UNKNOWN`, `LLM_ATTRIBUTE_NOT_ADMITTED` | Atributo fora da classe ou valor fora do PDM |
| `LLM_ATTRIBUTE_CONFLICT` | Valor diferente do que a extração já leu: o modelo nunca sobrescreve |
| `LLM_LITERAL_VALUE_NOT_IN_QUOTE` | Base `LITERAL` com valor que não está escrito no trecho |
| `NCM_MATTER_UNPROVEN` | Mesmo com os atributos do modelo, a matéria segue sem prova |
| `NCM_OUTSIDE_PDM_REFERENCE` | Código fora das referências da classe |
| `NCM_UNRESOLVED_BY_DOMAIN`, `NCM_DIFFERS_FROM_DOMAIN` | As regras, com os atributos aceitos, não chegam a um código, ou chegam a outro |

O código é sempre o que o motor de domínio calcula com a classe e os atributos aceitos; o modelo só
contribui com evidência. A função de anel ou vedação de sobressalente (`PDM110`) é a única pendência
que a evidência citada do auditor libera. Se o domínio chega ao NCM atual, o caso é `CONFIRMED`, sem
proposta.

**Proposta.** `NCM_CORRECTION` com `origin = LLM_AUDITOR` e `llm_audit` no changeset: modelo, versão do
prompt e da política, tokens, motivos da seleção, leitura das regras, atributos com trechos, atributos
inferidos, evidências, justificativa, classes candidatas e o hash do prompt. O id é próprio, então nunca
colide com a proposta das regras. Exige revisão técnica e fiscal, nunca entra em lote (só correções de
tier 1 e 2 sem revisão fiscal entram) e nem na política automática (#224), que não trata NCM. A
aprovação recalcula a coerência com a classe e os atributos do changeset e grava só o NCM.

**Falhas.** Resposta inválida, recusa, erro ou orçamento esgotado (`LLM_MAX_CALLS_PER_RUN`) deixam o
caso `FAILED` com o código do erro, e ele continua pendente. O resultado do batch traz `llm_audit`
(casos por resultado, motivos de seleção e de descarte, falhas e uso) e soma o uso em `model_usage`,
com custo desconhecido enquanto não houver preço configurado. Ao retomar um job, a etapa de propostas
roda de novo e o auditor também; ids determinísticos impedem propostas duplicadas.

**Medição.** De `back/`, sem expor o gabarito ao modelo:

```bash
LLM_REPOSITORY=bedrock_v1 uv run python -m pipelines.measure_ncm_benchmark ../data/benchmark_ncm/v1 \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx --llm-audit
```

O relatório ganha `llm_audit`: resultado por caso, acertos, erros, alterações indevidas, abstenções,
descartes e falhas por família (pendentes do gabarito à parte) e o total com o auditor. Localmente,
`LLM_REPOSITORY=simulated_v1` exercita o fluxo e se abstém em tudo; o resultado sai rotulado como
simulado e não mede qualidade. A medição com o Bedrock depende de acesso ao modelo na conta.

```bash
uv run --locked pytest tests/test_llm_audit.py tests/test_measure_ncm_benchmark.py
```
