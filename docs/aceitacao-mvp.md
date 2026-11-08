# Aceitação do MVP (#26)

Preparação local: **Refs #26**. Este PR pode integrar `homologacao` independentemente da homologação AWS; não encerra a issue.

Esta matriz transforma os critérios de `docs/arquitetura.md` em verificações repetíveis. Os testes locais não encerram a homologação AWS da [#26](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/26).

## Executar localmente

Use Python 3.12, `uv sync --all-packages --locked` e um PostgreSQL com pgvector. Exporte `TEST_DATABASE_URL` com uma credencial de migração autorizada a criar bancos e roles, apontando para um banco descartável terminado em `_test`. As suítes apagam e recriam seus bancos de teste. As credenciais dos serviços vêm de roles temporárias; senhas de serviços existentes não são alteradas.

O fixture do MCP deriva outro banco, terminado em `_mcp_search_test`, do nome informado. Ele carrega o kit e constrói o índice com `batch_user`. O novo fluxo também executa o saneamento com essa role, usa `api_user` para a API e `mcp_reader` para o subprocesso MCP.

Na raiz do repositório:

```bash
: "${TEST_DATABASE_URL:?Defina um banco descartável terminado em _test}"
(cd api && uv run --locked pytest)
(cd mcp && uv run --locked pytest)
(cd back && uv run --locked pytest)
```

Para executar somente a nova integração:

```bash
: "${TEST_DATABASE_URL:?Defina um banco descartável terminado em _test}"
(cd mcp && uv run --locked pytest tests/test_mvp_acceptance.py -v)
```

O resultado esperado dessa integração é **2 passed, sem skips**. Uma execução sem `TEST_DATABASE_URL`, que pula testes de banco, não é evidência de aceitação. No CI, o job `database` fornece a variável e executa as suítes completas de API e MCP, incluindo este cenário.

## O que o novo cenário comprova

`mcp/tests/test_mvp_acceptance.py::test_login_chat_mcp_batch_approval_audit_and_metrics` liga a sessão local opaca da API ao Agent real, usando HTTP em memória (`ASGITransport`), e deste ao servidor MCP real em subprocesso stdio. Confere que o turno executou o MCP pelas mensagens salvas no PostgreSQL e que o Solicitante não recebe as chamadas técnicas.

`test_dev_ti_sees_the_real_mcp_calls_and_business_profiles_do_not` repete o turno com a persona Dev/TI (#232) e confere que o painel recebe as chamadas MCP realmente executadas, enquanto perfis de negócio recebem a lista vazia.

O pedido incompleto permanece sem publicação. Uma segunda persona não consegue continuar a conversa pelo UUID. Uma proposta real gerada pelo batch passa por Governança e Fiscal, com 403 nas decisões indevidas, idempotência e autoria de auditoria. O teste confere os snapshots originais, o estoque consolidado e o funil do dashboard, mantendo economia realizada e comparação posterior indisponíveis quando não há evidência para elas.

`mcp/tests/test_search_content.py::test_registration_revalidates_sanitized_follow_up_and_preserves_original_text` usa o PDM do kit e um catálogo pequeno em PostgreSQL para testar três respostas ao campo `ACABAMENTO`. O valor do PDM e o alias inequívoco `zinc bco` completam o campo. O termo ambíguo `zincado` mantém a pergunta e bloqueia o envio. A validação roda em MCP stdio e o histórico conserva a resposta original em cada caso.

As escritas da API são desfeitas ao final, inclusive quando o teste falha. O HTTP interno em memória não cobre DNS, portas, cookies em navegador, imagens de container ou o provedor Cognito.

## Matriz dos critérios

Os caminhos e nomes abaixo são relativos ao repositório. A integração nova complementa os testes específicos; não os substitui.

| Critério                                                         | Verificação principal                                                                                                                                                   | Limite                                                                                                        |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Solicitante, Governança e Fiscal recebem 403 nas ações indevidas | `api/tests/test_authenticated_approvals.py::test_wrong_session_role_receives_403_even_with_a_forged_role_header`; nova integração                                       | Sessões locais reais da aplicação                                                                             |
| Trocar persona muda sessão e ator                                | `api/tests/test_demo_switch.py::test_approval_after_switching_is_audited_with_the_real_user`; `test_switch_changes_the_authenticated_session_and_audit_actor`           | O adaptador Cognito usa provedor HTTP controlado nesses testes; homologação real é #91                        |
| UUID não concede acesso à conversa                               | `api/tests/test_chat.py::test_other_users_session_is_not_found`; nova integração                                                                                        | Na integração, a recusa acontece antes de outra chamada MCP                                                   |
| Pedido incompleto recebe os campos faltantes corretos            | `mcp/tests/test_conversation_flow.py::test_incomplete_request_lists_missing_fields`; nova integração                                                                    | Caso real de parafuso do roteiro                                                                              |
| Painel representa chamadas MCP executadas                        | `mcp/tests/test_conversation_flow.py::test_panel_calls_are_the_executed_mcp_calls`; `test_dev_ti_sees_the_real_mcp_calls_and_business_profiles_do_not`               | Desde a #232, só a role Dev/TI vê o painel; perfis de negócio recebem lista vazia                              |
| Fabricantes diferentes permanecem distintos                      | `api/tests/test_approval_transactions.py::test_different_manufacturers_or_references_never_merge`                                                                       | Identidade compartilhada `identity-v3` já integrada; revisão humana dos casos inconclusivos permanece na #113 |
| Repetir aprovação não duplica efeitos                            | `api/tests/test_idempotency.py`; nova integração                                                                                                                        | Inclui concorrência em PostgreSQL na suíte da API                                                             |
| Proposta desatualizada é recusada                                | `api/tests/test_approval_transactions.py::test_stale_member_is_rejected_and_audited`                                                                                    | Confere 409, estado STALE e auditoria                                                                         |
| Consolidação conserva quantidade, valor e centros                | `api/tests/test_approval_transactions.py::test_merge_conserves_inventory_and_records_real_actor`; `test_unit_factor_requires_source_and_keeps_value`; nova integração   | Conversão exige fator e fonte; snapshots originais são preservados                                            |
| NCM só muda com autorização fiscal                               | `api/tests/test_approval_transactions.py::test_fiscal_review_and_technical_review_are_both_required`; `test_fiscal_change_cannot_bypass_review`; nova integração        | Regras fiscais da #22 já integradas; não comprova homologação fiscal humana                                   |
| Dashboard separa propostas, aplicações e estimativas             | `api/tests/test_dashboard.py::test_real_approval_and_idempotent_retry_count_one_application`; `test_snapshot_after_approval_compares_before_and_after`; nova integração | Aprovação não implica economia realizada nem avaliação independente                                           |

## Cobertura complementar entregue em homologacao

Os testes referenciados nesta matriz existem na base integrada; citar um teste não afirma que sua suíte completa foi executada nesta preparação. O cenário novo usa o classificador `aliases_v1` revisão 2, o extrator `rule_based_v1` revisão 10 e `identity-v3`, sem alterar o kit ou os gabaritos históricos.

| Fluxo entregue                                                  | Evidência específica                                                                                                                                                     | Limite                                                                   |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| Estoque por tenant, dataset e centros, com paginação autorizada | `api/tests/test_materials.py::test_inventory_respects_user_centers_latest_dataset_and_consolidations`; `test_other_tenants_are_invisible`; `test_pagination_with_cursor` | A integração nova confere conservação de snapshots e consolidação        |
| Histórico e retomada de conversa                                | `api/tests/test_chat.py::test_read_saved_conversation_and_resume_without_agent_replay`; `test_history_and_resume_recheck_current_center_scope`                           | Histórico revalida o escopo atual                                        |
| Resolução manual de pendências                                  | `api/tests/test_manual_reviews.py::test_proposing_does_not_edit_material_and_normal_approval_applies`; `test_packaging_needs_explicit_factor_and_source`                 | Gera proposta sujeita à aprovação; não altera diretamente o mestre       |
| Enriquecimento com fonte                                        | `api/tests/test_enrichment_flow.py::test_frozen_evidence_flows_to_partial_approval_without_canonicalizing`; `test_changed_evidence_blocks_approval`                      | Evidência congelada de desenvolvimento; não certifica NCM nem identidade |
| Segurança da identidade batch                                   | `back/tests/test_merge_identity_safety.py::test_real_oils_from_different_manufacturers_never_merge`; `test_real_excavator_model_never_identifies_bushing_or_idler`       | Regras compartilhadas integradas; não são precisão independente          |

## Execução local registrada — 08/11/2026

Sobre `f899c99` mais os ajustes da branch das pendências (#26, #30, #157), em macOS com Docker 28.1.1 e PostgreSQL 16 com pgvector:

| Verificação | Comando | Resultado |
| --- | --- | --- |
| Integração de aceitação | `(cd mcp && TEST_DATABASE_URL=… uv run --locked pytest tests/test_mvp_acceptance.py -v)` | 2 passed, sem skips (4min38s) |
| Suítes completas | API e MCP com `TEST_DATABASE_URL`, back e `scripts/tests` | API 1019, MCP 449, back 1441 e scripts 74 passed, sem skips |
| Containers e portas | `scripts/ci_images_smoke.sh --no-cache` ([detalhes](devops.md)) | Smoke `local` 7/7, reset, smoke `flow` 9/9, Agent com `AGENT_BUSY` acima do limite e zero MCP após cancelar |

O smoke `flow` cobre, em containers com HTTP real, o chat com busca de similares, o estoque por centro autorizado, o batch pela API, os pedidos, a Governança e o Fiscal com as três decisões na auditoria e o snapshot posterior no dashboard. Isso atende ao item da #47 abaixo para a versão testada. Login Cognito, HTTPS e o ambiente AWS não foram exercitados: este ambiente não tem credenciais AWS.

## Pendências para fechar a issue

- A consistência fiscal (#22) e a correção de identidade (#73, complementada por `identity-v3`) já estão integradas. A homologação técnica humana independente dos casos inconclusivos continua pendente (#113). Esta preparação não mede precisão independente nem comprova atualização do índice após uma aprovação; a correção de freshness da #195 não faz parte desta entrega.
- A #47 já foi integrada e o fluxo HTTP do Compose passou em 08/11/2026 (acima). Repetir sobre o commit escolhido para a demo, se ele mudar.
- Executar o fluxo implantado após o deploy (#6) e a homologação Cognito (#91), com HTTPS, três contas reais e trocas de persona no navegador. Usar os procedimentos de `deployment/README.md`, `docs/autenticacao.md` e `docs/demo.md`.
- Registrar commit, ambiente, horário, comandos/resultados e eventos de auditoria, preservando cookies, tokens e credenciais fora das evidências publicadas.
- Repetir no Plano B (#29) para o ensaio da demo. Login local e teste ASGI não contam como execução na AWS.

Até essas verificações, a #26 permanece aberta. A integração desta preparação local em `homologacao` não representa aceite completo do MVP nem homologação AWS.
