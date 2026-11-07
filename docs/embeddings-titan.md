# Embeddings Titan na busca

A configuração AWS permanece com `embedding_repository` vazio até comparar o
ganho no top 10 com o custo e a latência do Titan. A linha de base abaixo foi
medida em PostgreSQL 16 com pgvector, usando o kit do desafio e as regras de
`21f0a87`. Os 202 pares foram declarados na base por redirecionamentos
`USAR COD`. A avaliação mede a recuperação do código ativo indicado pela base.
Ela não estima a precisão de fusões.

| Busca | Pares no top 1 | Pares no top 5 | Pares no top 10 | Latência p50 | Latência p95 |
|---|---:|---:|---:|---:|---:|
| Identidade e full-text | 92/202 | 127/202 | 135/202 | 88,1 ms | 215,3 ms |

O hash da coorte é
`5bccde52f862f0dd74e1b67f9dc7e750d7020547a00ed0ffc5590da449a37f81`.
Uma chamada ao Titan em `us-east-1` com o termo genérico `PARAFUSO` retornou
512 dimensões e 5 tokens de entrada. A medição com os dados do kit e o
resultado comparativo seguem pendentes.

## Como reproduzir

Use um banco descartável com o kit carregado. Gere os dois índices sobre a
mesma carga, sem editar materiais ou mudar as revisões de PDM, classificação e
extração entre as rodadas. Rode as buscas na mesma máquina e compare os
relatórios quando os dois indicarem 23.554 materiais, 202 pares e o mesmo
`cohort_sha256`.

Para a linha de base, use a credencial batch e rode em `back/`:

```bash
EMBEDDING_REPOSITORY= uv run --locked vx-back index --if-stale \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Com a credencial `mcp_reader`, rode em `mcp/`:

```bash
EMBEDDING_REPOSITORY= uv run --locked python -m vx_materials_mcp.evaluation \
  --repository hybrid_v1 --tenant-id "$BENCHMARK_TENANT_ID" \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Para o Titan real, obtenha autorização para os dados e a conta de destino antes
de executar. O índice envia a descrição longa do material, com o prefixo de
redirecionamento removido quando reconhecido, e os nomes e valores dos atributos
PDM analisados. Cada consulta envia a descrição original do bloqueado sem o
prefixo e os valores de atributos que a busca extraiu. Esses textos podem
conter fabricante e referência. O código ativo esperado, os saldos e os
valores de estoque ficam no banco durante a avaliação.

Na mesma sessão, configure credenciais autorizadas para
`bedrock:InvokeModel` em `amazon.titan-embed-text-v2:0` e use
`AWS_REGION=us-east-1`. Repita os dois comandos com
`EMBEDDING_REPOSITORY=bedrock_titan_v1` e passe
`--repository hybrid_embeddings_v1` na avaliação. Reserve capacidade para até
23.554 chamadas de indexação e 202 chamadas de busca em uma execução completa.
O cliente usa uma tentativa por chamada. O índice Titan grava lotes de 128
materiais e `--if-stale` reaproveita os lotes confirmados após uma interrupção.
Para testar todo o caminho localmente, use `APP_ENV=local` com
`EMBEDDING_REPOSITORY=simulated_v1` ou `ollama_nomic_v1`, mantendo a busca
`hybrid_embeddings_v1`.

Registre separadamente os segundos da indexação, as latências p50/p95 das
consultas e os tokens retornados pelo Titan para cada fase. Multiplique
`embedding_input_tokens` pelo preço vigente por milhão de tokens da região e
divida por um milhão para estimar o custo da inferência em USD. Os tokens
refletem as chamadas concluídas e registradas no relatório daquela execução.
[Preços do Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/)

## Comportamento no ECS

Com `embedding_repository=bedrock_titan_v1`, o ECS configura a busca híbrida
com embeddings no Agent e roda o indexador com `--if-stale`. A assinatura
`bedrock_titan_v1:amazon.titan-embed-text-v2:0:512` entra na versão do índice.
O Agent verifica a cobertura e recusa uma versão incompatível. Em caso de
falha do Titan, a tool retorna `INDEX_UPDATING` e a conversa registra a falha
da busca. A identidade continua validada pelas regras de domínio.

O primeiro índice completo pode exceder os 20 minutos que o script de deploy
aguarda pela task. Nesse caso, coordene a construção prévia do índice em uma
task batch com o mesmo PDM, imagem e configuração de embeddings. Confirme
cobertura completa antes de prosseguir com o deploy. A busca em produção pode
continuar usando o índice textual até o Agent ser atualizado.
