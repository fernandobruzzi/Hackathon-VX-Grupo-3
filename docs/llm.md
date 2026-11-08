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

## Confiança do auditor (#297)

A confiança da sugestão do auditor tem duas camadas:

1. **Validação pelo domínio:** é a revalidação descrita acima. Ela é binária e auditável: a sugestão só existe se cada trecho citado estiver na descrição e se o motor de regras chegar ao mesmo código. Toda sugestão registra `domain_validated: true`.
2. **Pontuação por log probs:** é opcional e vem de `NCM_SCORER_REPOSITORY`. O pontuador recebe o mesmo prompt, sem NCM atual nem gabarito, e todos os códigos de referência da classe no PDM. Ele não gera resposta: devolve o log prob de cada candidato. A probabilidade normalizada entre os candidatos vira uma faixa: `ALTA` a partir de 0,9, `MEDIA` a partir de 0,6, `BAIXA` abaixo disso. Os limites são provisórios até a calibração com um modelo real.

O changeset guarda `llm_audit.confidence` com:

- versão (`ncm-confidence-v1`);
- candidatos;
- probabilidades e faixa;
- pontuador (repositório, modelo e se é simulado);
- o código de erro, quando houver.

Uma falha do pontuador, ou log probs para candidatos diferentes (`SCORER_CANDIDATES_MISMATCH`), deixa a sugestão sem faixa, só com a validação pelo domínio. A confiança nunca aprova, aplica nem coloca a sugestão em lote: ela continua com revisão técnica e fiscal.

`simulated_v1` dá o mesmo log prob a todos os candidatos, ou valores fixos nos testes. É rotulado e recusado fora de `APP_ENV=local`. Sem a variável, nenhum modelo pontua.

**Calibração:** `pipelines.measure_ncm_benchmark --llm-audit` conta, por família, acertos e erros por faixa (`band_<FAIXA>_hit` e `band_<FAIXA>_wrong`, e `SEM_PONTUADOR` sem pontuador). O gabarito só é lido depois de todas as sugestões existirem.

**Modelos com log probs no Bedrock:**

- O Claude na Messages/Converse API não expõe log probs. Por isso o Sonnet 5 continua só gerando a sugestão.
- O Bedrock Custom Model Import devolve log probs com `"return_logprobs": true` no `InvokeModel`, para modelos importados a partir de 31/07/2025. O formato `OpenAIChatCompletion` traz log probs do prompt e da saída; o `BedrockCompletion` traz só os da saída. Fontes: [recursos avançados do Custom Model Import](https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-import-advanced-features.html) e [o anúncio do suporte a log probs](https://aws.amazon.com/blogs/machine-learning/unlock-model-insights-with-log-probability-support-for-amazon-bedrock-custom-model-import).
- Os modelos abertos gerenciados (como o gpt-oss) não têm suporte a log probs confirmado na documentação.

**`bedrock_import_v1`:** é o pontuador real. Ele chama `InvokeModel` no formato OpenAIChatCompletion do Custom Model Import, no modelo de `BEDROCK_SCORER_MODEL_ARN`:

- **Pedido:** os candidatos vão com letras (`A) 8481.80.95`), com `max_tokens: 1`, `temperature: 0`, `logprobs: true` e `top_logprobs` de 5 a 20.
- **Pontuação:** o log prob de cada letra entre as alternativas do primeiro token vira a pontuação do código. A letra que não aparece entre as alternativas fica 20 abaixo da pior devolvida.
- **Classe com um único código:** devolve log prob 0 sem chamar o modelo.
- **Orçamento:** cada chamada conta em `NCM_SCORER_MAX_CALLS` (padrão 200).
- **Falhas:** saem com um código estável e deixam a sugestão sem faixa: `SCORER_NOT_CONFIGURED`, `SCORER_REQUEST_REJECTED`, `SCORER_UNAVAILABLE`, `SCORER_INVALID_RESPONSE`, `SCORER_NO_CANDIDATE_TOKEN`, `SCORER_BUDGET_EXHAUSTED`.

**Na revisão:**

- A fila mostra o selo "Confiança alta/média/baixa" (`confidence_band`).
- O painel do auditor mostra:
  - a validação pelo domínio;
  - a faixa e a probabilidade de cada código do PDM;
  - o pontuador e um aviso quando a pontuação é simulada.
- Sem pontuador, o painel diz que vale só a validação pelo domínio.

A documentação da AWS diverge sobre a data mínima de importação: o blog fala em 31/07/2025, e a página de recursos avançados, em 11/11/2025. Nenhuma das duas informa regiões nem limites específicos de log probs.

**Pendente (exige acesso à conta AWS do workshop):**

- confirmar quais modelos importados existem, em que região e com que limites;
- rodar o `bedrock_import_v1` contra um deles; o formato segue a documentação, mas só foi testado com um cliente simulado;
- calibrar as faixas no benchmark com `LLM_REPOSITORY=bedrock_v1 NCM_SCORER_REPOSITORY=bedrock_import_v1 ... measure_ncm_benchmark --llm-audit`.
