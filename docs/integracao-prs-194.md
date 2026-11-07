# Integração sequencial e branches — issue #194

**Integrações concluídas; três drafts com critérios externos pendentes — 7 de novembro de 2026 (UTC).** A fila mudou durante o trabalho; os números dos PRs abaixo identificam cada decisão, independentemente da contagem inicial de 32.

O inventário inicial é histórico. Na conferência de 2026-11-07T04:56:28.097Z, somente #195, #131 e #134 permaneciam abertos, todos em draft. As tabelas abaixo distinguem merges reais, substituições e critérios externos ainda pendentes.

## Por que os PRs estavam abertos

Havia motivos diferentes: drafts com captura externa ou aceite humano pendente; branches sobre uma base anterior; conflitos de contratos/migrações; testes ou critérios ainda incompletos; e implementações substituídas por outras já integradas. Estar aberto ou mostrar zero checks não prova falha: no fluxo atual, PRs de trabalho para `homologacao` não executam CI. As três suítes locais são o gate. Os oito checks são exclusivos da promoção de `homologacao` para `main`.

Cada merge desta fila usa rebase e uma conferência nova do head/base. Branches de outros autores que precisaram de alterações foram preservadas: o conteúdo foi integrado por PR próprio, e o original só foi fechado após confirmar o merge e que o head original não mudou.

O histórico confirma a mudança no [PR202](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/202), que levou os PRs de trabalho e os testes locais para `homologacao`, e a promoção no [PR203](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/203), integrada em `main` como `0a4e007ef33be76f8d0ada9a4f8b8ace337ef265`. A sequência atual replica rebase, validação e merge usados anteriormente na `main`, usando a nova base. Nenhuma promoção adicional para produção faz parte desta fila.

## Análise individual dos PRs

| PR                                                                      | Branch original                           | Último estado registrado | Análise / encaminhamento                                                                                                                                      |
| ----------------------------------------------------------------------- | ----------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#69](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/69)   | `feat/23-real-product-enrichment`         | FECHADO SEM MERGE        | Substituído por [#210](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/210) após confirmar MERGED; branch original preservada.                    |
| [#72](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/72)   | `docs/28-roi-pitch`                       | FECHADO SEM MERGE        | Substituído por [#217](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/217) após confirmar MERGED; branch original preservada.                    |
| [#116](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/116) | `feat/68-manual-review`                   | FECHADO SEM MERGE        | Substituído por [#211](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/211) após confirmar MERGED; branch original preservada.                    |
| [#123](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/123) | `fix/121-trailing-punctuation`            | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#127](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/127) | `test/26-mvp-acceptance`                  | MERGED                   | Aceitação local integrada com PostgreSQL; AWS/Cognito/EC2 e aceite final da issue #26 continuam pendentes.                                                    |
| [#130](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/130) | `fix/107-agent-memory-measurement`        | MERGED                   | Preparação de medição local; homologação AWS da issue107 não foi inventada.                                                                                   |
| [#131](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/131) | `feat/30-official-ncm-snapshot`           | ABERTO / DRAFT           | Draft: falta captura oficial Siscomex; CONNECT403 neste ambiente.                                                                                             |
| [#132](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/132) | `feat/113-independent-review-handoff`     | MERGED                   | Pacote congelado preparado; aceite técnico humano da issue113 segue separado.                                                                                 |
| [#134](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/134) | `feat/35-mcp-resources-prompts`           | ABERTO / DRAFT           | Draft: recursos/prompts preparados localmente; captura NCM oficial Siscomex ainda não obtida.                                                                 |
| [#135](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/135) | `fix/133-explicit-technical-values`       | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#161](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/161) | `fix/149-atomic-storage`                  | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#163](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/163) | `fix/156-batch-action-error`              | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#164](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/164) | `fix/146-authorize-order-replay`          | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#165](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/165) | `fix/148-resumable-finalization`          | MERGED                   | Finalização retomável com métricas imutáveis.                                                                                                                 |
| [#166](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/166) | `ci/157-complete-smoke-flow`              | MERGED                   | Configuração da CI integrada; Refs #157. Build/flow Compose real ainda bloqueado pelo certificado RDS; issue aberta.                                          |
| [#167](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/167) | `fix/150-metric-thread-length`            | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#168](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/168) | `fix/143-mcp-tenant-scope`                | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#169](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/169) | `fix/153-reject-unsupported-status-scope` | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#170](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/170) | `fix/151-decimal-inches`                  | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#171](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/171) | `fix/137-paginate-scoped-orders`          | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#172](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/172) | `fix/145-preserve-reusable-identity`      | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#173](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/173) | `fix/154-ncm-evaluation-coverage`         | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#174](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/174) | `feat/142-complement-registration-orders` | MERGED                   | Complementos com origem, versionamento, idempotência e escopo; migração 0014. Validação final: 915 back / 586 API PostgreSQL / 169 MCP PostgreSQL.            |
| [#175](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/175) | `fix/144-preserve-item-name`              | FECHADO SEM MERGE        | Substituído por [#187](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/187) após confirmar MERGED; branch original preservada.                    |
| [#177](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/177) | `chore/176-ignore-secrets`                | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#179](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/179) | `fix/139-complete-audit-events`           | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#180](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/180) | `feat/141-resume-chat-history`            | MERGED                   | Histórico privado/paginado com validação atual e escopo de centros.                                                                                           |
| [#181](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/181) | `fix/152-current-inventory-dataset`       | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#182](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/182) | `ci/178-local-tests-homologacao`          | FECHADO SEM MERGE        | Substituído por [#196](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/196) após confirmar MERGED; branch original preservada.                    |
| [#183](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/183) | `feat/138-review-order-fiscal-ncm`        | MERGED                   | Revisão técnica/fiscal com assinatura atual, auditoria e NCM normalizado; migração 0015. Validação final: 915 back / 600 API PostgreSQL / 169 MCP PostgreSQL. |
| [#184](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/184) | `fix/147-snapshot-field-provenance`       | MERGED                   | Origem por campo, preservando o valor e sua fonte.                                                                                                            |
| [#186](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/186) | `docs/185-post-merge-cleanup`             | MERGED                   | Integrado por rebase; validação registrada no PR.                                                                                                             |
| [#187](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/187) | `fix/144-shared-material-identity`        | MERGED                   | Decisão compartilhada de identidade integrada; substitui175.                                                                                                  |
| [#195](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/195) | `fix/140-current-material-search`         | ABERTO / DRAFT           | Draft: código e testes locais preparados; reconstrução/flow Compose real bloqueado pelo domínio do certificado RDS.                                           |
| [#205](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/205) | `fix/158-no-value-specialization`         | FECHADO SEM MERGE        | Substituído por [#216](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/216) após confirmar MERGED; branch original preservada.                    |
| [#206](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/206) | `fix/204-classifier-abbreviations`        | FECHADO SEM MERGE        | Substituído por [#212](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/212) após confirmar MERGED; branch original preservada.                    |
| [#208](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/208) | `feat/207-experiment-packets`             | FECHADO SEM MERGE        | Substituído por [#218](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/218) após confirmar MERGED; branch original preservada.                    |
| [#213](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/213) | `fix/188-batch-idempotency`               | MERGED                   | Idempotency-Key obrigatório no start/resume batch, replay vinculado a ator/ação/corpo/recurso; sem migração.                                                  |
| [#215](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/215) | `fix/198-inline-label-prefix`             | MERGED                   | Prefixos anteriores a rótulos inline preservados; medição histórica própria, distinta da revisão 10 da #205.                                                  |

## Preparações locais e critérios ainda abertos

A CI da #166 está **configurada** para `local → reset da demo → flow → concorrência`,
somente na promoção `homologacao → main` do mesmo repositório, com oito checks.
A preparação é integrável com **Refs #157**, mantendo a issue #157 aberta, assim como
as preparações locais #130, #132 e #127 não encerram homologações externas. As três
suítes locais, 43 testes de scripts, 8 de workflow e a política foram verificados
no trabalho da #166; este relatório não afirma uma nova execução deles. Build de
imagens e flow completo com Compose permanecem sem execução real validada porque
o domínio do certificado RDS foi negado. Configuração não é esse aceite.

Após integrar a preparação da #166, os três critérios de draft restantes são #195 (build/flow real e RDS), #131 e #134 (captura oficial
Siscomex). Os três drafts não foram integrados. AWS, Cognito, ensaio humano e issues de
aceite continuam separados dos merges de preparação.

A base candidata já incorpora #213 sem migração e #215 com seu registro histórico
em [inline-label-prefix.md](inline-label-prefix.md). A comparação da #205 está em
[alias-evidence-158-current.json](measurements/alias-evidence-158-current.json):
extrator `rule_based_v1` da revisão `9-inline-label-prefix-198` para `10`, mantendo
classificador `aliases_v1@2`; 5 materiais e 6 referências de pedidos mudam,
preservando os valores corretos da evidência original. Os estados e as chaves de
identidade não mudam (23.554 materiais/520 pedidos). `DO` continua sendo parte do
cabeçalho composto, nunca referência fabricada. São medições de desenvolvimento
com fontes/hashes registrados; não são precisão independente nem uma nova
medição executada para este relatório.

A sequência pendente de migrações é linear: #195 acrescenta
`0016_search_content_version` após 0015; #131 não acrescenta migração; #134 prepara 0017
para recursos MCP após 0016. A validação final do grafo acompanha a base combinada,
sem criar uma bifurcação para contornar essa ordem.

Os vínculos de substituição já identificados são
[69→210](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/210),
[116→211](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/211),
[206→212](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/212),
[205→216](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/216),
[175→187](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/187) e
[182→196](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/196).
Também foram confirmados [72→217](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/217) e [208→218](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/218). O #214 foi fechado sem merge e substituído pelo #216.

## Análise individual das branches iniciais

A análise histórica original permanece em [limpeza-branches-185.md](limpeza-branches-185.md). A regra obrigatória de pós-merge foi integrada pelo PR186; um PR apenas fechado não satisfaz essa regra. A conferência abaixo compara cada branch inicial com referências remotas atualizadas. Ausência não atribui a exclusão a esta execução: o GitHub e outros colaboradores também podem remover branches após merge.

| Branch                                    | PR / evidência                                                          | Head remoto    | Decisão                                                                      |
| ----------------------------------------- | ----------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------- |
| `chore/176-ignore-secrets`                | [#177](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/177) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `ci/108-main-ci-queue`                    | [#110](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/110) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `ci/157-complete-smoke-flow`              | [#166](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/166) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `ci/178-local-tests-homologacao`          | [#182](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/182) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `docs/28-roi-pitch`                       | [#72](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/72)   | `2156da8e7325` | Preservada: original fechado sem merge; conteúdo integrado por substituição. |
| `feat/23-real-product-enrichment`         | [#69](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/69)   | `db7774342f31` | Preservada: original fechado sem merge; conteúdo integrado por substituição. |
| `feat/30-official-ncm-snapshot`           | [#131](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/131) | `c34d87adddde` | Preservada: PR aberto em draft.                                              |
| `feat/35-mcp-resources-prompts`           | [#134](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/134) | `453e1d3c4a58` | Preservada: PR aberto em draft.                                              |
| `feat/68-manual-review`                   | [#116](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/116) | `61da1da04b9c` | Preservada: original fechado sem merge; conteúdo integrado por substituição. |
| `feat/113-independent-review-handoff`     | [#132](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/132) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `feat/120-lot-approval`                   | [#126](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/126) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `feat/138-review-order-fiscal-ncm`        | [#183](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/183) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `feat/141-resume-chat-history`            | [#180](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/180) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `feat/142-complement-registration-orders` | [#174](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/174) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/107-agent-memory-measurement`        | [#130](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/130) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/121-trailing-punctuation`            | [#123](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/123) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/133-explicit-technical-values`       | [#135](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/135) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/137-paginate-scoped-orders`          | [#171](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/171) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/139-complete-audit-events`           | [#179](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/179) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/143-mcp-tenant-scope`                | [#168](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/168) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/144-preserve-item-name`              | [#175](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/175) | `f5299cbd8808` | Preservada: original fechado sem merge; conteúdo integrado por substituição. |
| `fix/145-preserve-reusable-identity`      | [#172](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/172) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/146-authorize-order-replay`          | [#164](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/164) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/147-snapshot-field-provenance`       | [#184](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/184) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/148-resumable-finalization`          | [#165](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/165) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/149-atomic-storage`                  | [#161](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/161) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/150-metric-thread-length`            | [#167](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/167) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/151-decimal-inches`                  | [#170](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/170) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/152-current-inventory-dataset`       | [#181](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/181) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/153-reject-unsupported-status-scope` | [#169](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/169) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/154-ncm-evaluation-coverage`         | [#173](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/173) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `fix/156-batch-action-error`              | [#163](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/163) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |
| `homologacao`                             | Permanente                                                              | `91730ca909db` | Preservada: branch permanente.                                               |
| `main`                                    | Permanente                                                              | `0a4e007ef33b` | Preservada: branch permanente.                                               |
| `test/26-mvp-acceptance`                  | [#127](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/127) | `ausente`      | Ausente no remoto; nenhuma exclusão adicional necessária.                    |

`main`, `homologacao` e a branch local preexistente `work` foram preservadas. Worktrees com patches de referência ainda necessários não foram descartadas. Cópias locais concluídas só são removidas após árvore limpa, prova de integração e conferência dos worktrees. As branches próprias dos PRs de substituição são verificadas separadamente após cada merge. Conferência com fetch de todas as heads remotas; branches dos merges #127, #174, #183 e #166 já ausentes após o merge. Branches fechadas sem merge foram preservadas.

## Limites da validação

Passagens locais não são aceite humano, ensaio cronometrado, homologação AWS nem captura fiscal oficial. O proxy deste ambiente negou o domínio `truststore.pki.rds.amazonaws.com` durante a reconstrução Compose e o endpoint oficial Siscomex durante a captura NCM. Não foram usados certificados alternativos, espelhos rotulados como oficiais ou resultados fictícios. Os PRs dependentes desses critérios permanecem identificados até uma execução real.

## Branches posteriores ao inventário inicial

| Branch                             | PR / evidência                                                          | Head remoto    | Decisão                                                          |
| ---------------------------------- | ----------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------- |
| `fix/140-current-material-search`  | [#195](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/195) | `41efc1717b1f` | Preservada: PR em draft.                                         |
| `fix/158-no-value-specialization`  | [#205](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/205) | `85a41ec0c9bd` | Preservada: original fechado sem merge; substituição confirmada. |
| `fix/204-classifier-abbreviations` | [#206](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/206) | `4bb8542b9a62` | Preservada: original fechado sem merge; substituição confirmada. |
| `feat/207-experiment-packets`      | [#208](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/208) | `60a32cd160dc` | Preservada: original fechado sem merge; substituição confirmada. |
| `fix/188-batch-idempotency`        | [#213](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/213) | `ausente`      | Ausente no remoto após merge confirmado.                         |
| `fix/198-inline-label-prefix`      | [#215](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/215) | `ausente`      | Ausente no remoto após merge confirmado.                         |

As branches próprias das substituições #210, #211, #212, #216, #217 e #218 foram conferidas ausentes após confirmar MERGED. Nenhuma branch permanente ou trabalho local preexistente foi descartado.
