# Limpeza de branches — issue #185

Análise de 6 de novembro de 2026 (BRT), após atualizar as referências remotas.
Foram examinadas individualmente as 35 branches existentes e os 88 PRs retornados pelo GitHub.

## Resultado

- Excluída do remoto: `ci/108-main-ci-queue`.
- Preservadas: 32 branches com PR aberto e as permanentes `main` e `homologacao`.
- A única branch local anterior ao trabalho, `work`, foi preservada. Não havia cópia local de `ci/108-main-ci-queue`.

## Análise individual

| Branch | Evidência | Decisão |
|---|---|---|
| `chore/176-ignore-secrets` | PR [#177](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/177) aberto; alterações ainda não integradas | Preservada |
| `ci/108-main-ci-queue` | PR [#110](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/110) mesclado; issue #108 concluída; nenhum patch exclusivo | Excluída |
| `ci/157-complete-smoke-flow` | PR [#166](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/166) aberto; alterações ainda não integradas | Preservada |
| `ci/178-local-tests-homologacao` | PR [#182](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/182) aberto; alterações ainda não integradas | Preservada |
| `docs/28-roi-pitch` | PR [#72](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/72) aberto; alterações ainda não integradas | Preservada |
| `feat/23-real-product-enrichment` | PR [#69](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/69) aberto; alterações ainda não integradas | Preservada |
| `feat/30-official-ncm-snapshot` | PR [#131](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/131) aberto; alterações ainda não integradas | Preservada |
| `feat/35-mcp-resources-prompts` | PR [#134](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/134) aberto; alterações ainda não integradas | Preservada |
| `feat/68-manual-review` | PR [#116](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/116) aberto; alterações ainda não integradas | Preservada |
| `feat/113-independent-review-handoff` | PR [#132](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/132) aberto; alterações ainda não integradas | Preservada |
| `feat/120-lot-approval` | PR [#126](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/126) aberto; alterações ainda não integradas | Preservada |
| `feat/138-review-order-fiscal-ncm` | PR [#183](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/183) aberto; alterações ainda não integradas | Preservada |
| `feat/141-resume-chat-history` | PR [#180](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/180) aberto; alterações ainda não integradas | Preservada |
| `feat/142-complement-registration-orders` | PR [#174](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/174) aberto; alterações ainda não integradas | Preservada |
| `fix/107-agent-memory-measurement` | PR [#130](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/130) aberto; alterações ainda não integradas | Preservada |
| `fix/121-trailing-punctuation` | PR [#123](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/123) aberto; alterações ainda não integradas | Preservada |
| `fix/133-explicit-technical-values` | PR [#135](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/135) aberto; alterações ainda não integradas | Preservada |
| `fix/137-paginate-scoped-orders` | PR [#171](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/171) aberto; alterações ainda não integradas | Preservada |
| `fix/139-complete-audit-events` | PR [#179](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/179) aberto; alterações ainda não integradas | Preservada |
| `fix/143-mcp-tenant-scope` | PR [#168](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/168) aberto; alterações ainda não integradas | Preservada |
| `fix/144-preserve-item-name` | PR [#175](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/175) aberto; alterações ainda não integradas | Preservada |
| `fix/145-preserve-reusable-identity` | PR [#172](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/172) aberto; alterações ainda não integradas | Preservada |
| `fix/146-authorize-order-replay` | PR [#164](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/164) aberto; alterações ainda não integradas | Preservada |
| `fix/147-snapshot-field-provenance` | PR [#184](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/184) aberto; alterações ainda não integradas | Preservada |
| `fix/148-resumable-finalization` | PR [#165](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/165) aberto; alterações ainda não integradas | Preservada |
| `fix/149-atomic-storage` | PR [#161](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/161) aberto; alterações ainda não integradas | Preservada |
| `fix/150-metric-thread-length` | PR [#167](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/167) aberto; alterações ainda não integradas | Preservada |
| `fix/151-decimal-inches` | PR [#170](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/170) aberto; alterações ainda não integradas | Preservada |
| `fix/152-current-inventory-dataset` | PR [#181](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/181) aberto; alterações ainda não integradas | Preservada |
| `fix/153-reject-unsupported-status-scope` | PR [#169](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/169) aberto; alterações ainda não integradas | Preservada |
| `fix/154-ncm-evaluation-coverage` | PR [#173](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/173) aberto; alterações ainda não integradas | Preservada |
| `fix/156-batch-action-error` | PR [#163](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/163) aberto; alterações ainda não integradas | Preservada |
| `homologacao` | Branch permanente, destino do PR [#182](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/182) aberto | Preservada |
| `main` | Branch principal protegida | Preservada |
| `test/26-mvp-acceptance` | PR [#127](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/pull/127) aberto; alterações ainda não integradas | Preservada |

## Conferência da branch excluída

- O head remoto `4b9fa196bd884717da19c592e1044c109e4d626f` coincidia com o head mesclado do PR #110, sem commits posteriores.
- O PR foi mesclado em 6 de novembro de 2026, às 07h45 BRT; a issue #108 está fechada com motivo `completed`.
- O commit resultante `c7bea6b1b2cd7fff0d886ec4dd8f5fbf9fbe2c71` é ancestral da `main` examinada (`6c8ec19afdd777af061438c7352fdb40413a2619`).
- `git cherry -v origin/main origin/ci/108-main-ci-queue` retornou apenas `- 4b9fa196…`: nenhum patch exclusivo.
- `git range-diff 4b9fa196^..4b9fa196 c7bea6b1^..c7bea6b1` confirmou patches idênticos (`=`). O rebase explica os SHAs diferentes.
- A exclusão foi condicionada ao SHA verificado com `--force-with-lease=refs/heads/ci/108-main-ci-queue:4b9fa196bd884717da19c592e1044c109e4d626f`.
- A listagem posterior do GitHub retornou 34 branches, sem a branch excluída. `git fetch origin --prune` também removeu a referência remota local.

Os PRs e branches continuam recebendo atualizações. Esta análise registra a decisão desta limpeza; uma próxima exclusão exige nova conferência.
