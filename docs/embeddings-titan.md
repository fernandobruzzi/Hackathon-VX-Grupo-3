# Embeddings Titan na busca

A configuração AWS mantém `embedding_repository` vazio por padrão. O Titan
recuperou 10 pares a mais no top 10, mas elevou a latência p95 de 177,4 ms para
787,8 ms. A ativação permanece explícita enquanto o ganho de cobertura tiver
esse custo de latência na busca interativa.

O benchmark de 8 de novembro de 2026 usou o Titan Text Embeddings V2 em
`us-east-1` na conta do workshop, com o índice em PostgreSQL 16 e pgvector
local. As duas buscas usaram o classificador `aliases_v1@3-pilot-families-263`,
a mesma carga de 23.554 materiais e os mesmos 202 pares declarados por
redirecionamentos `USAR COD`. A avaliação mede a recuperação do código ativo
indicado pela base. O ganho de cobertura para `aliases_v2` ainda precisa de
medição própria.

| Busca | Pares no top 1 | Pares no top 5 | Pares no top 10 | Latência p50 | Latência p95 |
|---|---:|---:|---:|---:|---:|
| Identidade e full-text | 92/202 | 127/202 | 135/202 | 93,9 ms | 177,4 ms |
| Identidade, full-text e Titan | 94/202 | 138/202 | 145/202 | 668,2 ms | 787,8 ms |

O hash da coorte é
`5bccde52f862f0dd74e1b67f9dc7e750d7020547a00ed0ffc5590da449a37f81`.
O índice Titan registrou 512 dimensões e cobertura de 23.554 de 23.554
materiais. A construção levou 1.416,173 segundos com até 10 chamadas
concorrentes. As 202 consultas levaram 138,439 segundos com Titan e 19,902
segundos sem embeddings. Houve quatro timeouts de leitura recuperados por
nova tentativa, em 23.760 tentativas de inferência.

O Titan reportou 1.849.331 tokens de entrada na indexação e 12.102 nas
consultas. Ao preço de US$ 0,02 por milhão de tokens, a inferência das chamadas
com resposta custou cerca de US$ 0,0372. [Preços do Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/)

## Como reproduzir

Use um banco descartável com o kit carregado. Para reproduzir a comparação
publicada, exporte `CLASSIFICATION_REPOSITORY=aliases_v1` nas duas etapas e
confira a revisão na assinatura do índice. Gere os dois índices sobre a mesma
carga, mantendo os materiais e as revisões de PDM, classificação e extração
entre as rodadas. Rode as buscas na mesma máquina e compare os relatórios
quando os dois indicarem 23.554 materiais, 202 pares e o mesmo `cohort_sha256`.

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
