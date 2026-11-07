# Cliente de modelo de linguagem (#287)

O back chama modelos de linguagem por um repositório trocável, no mesmo padrão dos algoritmos
selecionáveis. Nenhum fluxo usa o cliente ainda: ele é a base do auditor LLM (#290).

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
