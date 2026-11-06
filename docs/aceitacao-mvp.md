# Aceitação do MVP (#26)

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

O resultado esperado dessa integração é **1 passed, sem skips**. Uma execução sem `TEST_DATABASE_URL`, que pula testes de banco, não é evidência de aceitação. No CI, o job `database` fornece a variável e executa as suítes completas de API e MCP, incluindo este cenário.

## O que o novo cenário comprova

`mcp/tests/test_mvp_acceptance.py::test_login_chat_mcp_batch_approval_audit_and_metrics` liga a sessão local opaca da API ao Agent real, usando HTTP em memória (`ASGITransport`), e deste ao servidor MCP real em subprocesso stdio. Confere as chamadas observadas, o painel retornado e a mensagem salva no PostgreSQL.

O pedido incompleto permanece sem publicação. Uma segunda persona não consegue continuar a conversa pelo UUID. Uma proposta real gerada pelo batch passa por Governança e Fiscal, com 403 nas decisões indevidas, idempotência e autoria de auditoria. O teste confere os snapshots originais, o estoque consolidado e o funil do dashboard, mantendo economia realizada e comparação posterior indisponíveis quando não há evidência para elas.

As escritas da API são desfeitas ao final, inclusive quando o teste falha. O HTTP interno em memória não cobre DNS, portas, cookies em navegador, imagens de container ou o provedor Cognito.

## Matriz dos critérios

Os caminhos e nomes abaixo são relativos ao repositório. A integração nova complementa os testes específicos; não os substitui.

| Critério                                                         | Verificação principal                                                                                                                                                   | Limite                                                                                              |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Solicitante, Governança e Fiscal recebem 403 nas ações indevidas | `api/tests/test_authenticated_approvals.py::test_wrong_session_role_receives_403_even_with_a_forged_role_header`; nova integração                                       | Sessões locais reais da aplicação                                                                   |
| Trocar persona muda sessão e ator                                | `api/tests/test_demo_switch.py::test_approval_after_switching_is_audited_with_the_real_user`; `test_switch_changes_the_authenticated_session_and_audit_actor`           | O adaptador Cognito usa provedor HTTP controlado nesses testes; homologação real é #91              |
| UUID não concede acesso à conversa                               | `api/tests/test_chat.py::test_other_users_session_is_not_found`; nova integração                                                                                        | Na integração, a recusa acontece antes de outra chamada MCP                                         |
| Pedido incompleto recebe os campos faltantes corretos            | `mcp/tests/test_conversation_flow.py::test_incomplete_request_lists_missing_fields`; nova integração                                                                    | Caso real de parafuso do roteiro                                                                    |
| Painel representa chamadas MCP executadas                        | `mcp/tests/test_conversation_flow.py::test_panel_calls_are_the_executed_mcp_calls`; nova integração                                                                     | A integração também verifica a persistência pela API                                                |
| Fabricantes diferentes permanecem distintos                      | `api/tests/test_approval_transactions.py::test_different_manufacturers_or_references_never_merge`                                                                       | Cobre classes por referência na aprovação; os erros de identidade técnica do batch continuam na #73 |
| Repetir aprovação não duplica efeitos                            | `api/tests/test_idempotency.py`; nova integração                                                                                                                        | Inclui concorrência em PostgreSQL na suíte da API                                                   |
| Proposta desatualizada é recusada                                | `api/tests/test_approval_transactions.py::test_stale_member_is_rejected_and_audited`                                                                                    | Confere 409, estado STALE e auditoria                                                               |
| Consolidação conserva quantidade, valor e centros                | `api/tests/test_approval_transactions.py::test_merge_conserves_inventory_and_records_real_actor`; `test_unit_factor_requires_source_and_keeps_value`; nova integração   | Conversão exige fator e fonte; snapshots originais são preservados                                  |
| NCM só muda com autorização fiscal                               | `api/tests/test_approval_transactions.py::test_fiscal_review_and_technical_review_are_both_required`; `test_fiscal_change_cannot_bypass_review`; nova integração        | A ferramenta de consistência e os condicionais adicionais pertencem à #22                           |
| Dashboard separa propostas, aplicações e estimativas             | `api/tests/test_dashboard.py::test_real_approval_and_idempotent_retry_count_one_application`; `test_snapshot_after_approval_compares_before_and_after`; nova integração | Aprovação não implica economia realizada nem avaliação independente                                 |

## Pendências para fechar a issue

- A consistência fiscal (#22) já foi integrada na main. Revalidar o fluxo após integrar a correção de unificações inseguras (#73); os testes atuais de referência não comprovam a resolução dos erros de identidade técnica encontrados na base.
- A #47 já foi integrada: executar também o fluxo HTTP do Compose descrito em `docs/demo.md` sobre a versão escolhida para a demo. Este teste ASGI complementa aquela verificação de containers e portas.
- Executar o fluxo implantado após o deploy (#6) e a homologação Cognito (#91), com HTTPS, três contas reais e trocas de persona no navegador. Usar os procedimentos de `deployment/README.md`, `docs/autenticacao.md` e `docs/demo.md`.
- Registrar commit, ambiente, horário, comandos/resultados e eventos de auditoria, preservando cookies, tokens e credenciais fora das evidências publicadas.
- Repetir no Plano B (#29) para o ensaio da demo. Login local e teste ASGI não contam como execução na AWS.

Até essas verificações, a #26 permanece aberta e o PR desta preparação fica em rascunho.
