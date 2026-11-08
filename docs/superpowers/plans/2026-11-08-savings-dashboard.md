# Economia com premissas — plano de implementação

> **For agentic workers:** executar inline com superpowers:executing-plans.

**Goal:** entregar #316 com contagens auditadas e valores explicitamente condicionados a premissas.
**Architecture:** estender a visão executiva existente; registrar premissas imutáveis no ObjectStore, selecionadas por versão; usar eventos persistidos e movimentos reais, sem serviços externos.
**Tech Stack:** Python, SQLAlchemy/PostgreSQL, Pydantic, Next.js e OpenAPI.
**Spec:** issue #316 e recomendações aprovadas pelo usuário nesta conversa.

## Global Constraints

- Sem novas dependências nem expansão da M7.
- Não há economia realizada comprovada: manter realized_savings indisponível.
- Atendimento com estoque é valor de referência medido no kit, separado de estimativas de economia.
- Sem premissa, manter contagem e valor indisponível; premissas são hipóteses com origem e data.
- Não mostrar valores financeiros na visão de qualidade.

## Review Focus

- Não contar retries ou eventos antigos de conteúdo diferente.
- Só contar reutilização explicitamente confirmada e persistida, por conversa.
- Respeitar tenant, dataset e centros, inclusive estoque herdado por consolidação.
- Reversões reduzem atendimento; preços ausentes, heterogêneos ou unidade incompatível não viram zero.
- Premissas ausentes ou corrompidas não viram valores inventados; não somar valor do estoque a economias estimadas.

## Task 1: premissas e contagens

**Files:** api/vx_materials_api/savings_assumptions.py; schemas/metrics.py; services/savings_metrics.py; services/metrics_service.py; tests/test_savings_metrics.py.
**Interfaces:** FinancialMetrics.components e assumption_source; register_assumptions(store, raw); SAVINGS_ASSUMPTIONS_VERSION.
- [ ] Escrever e observar testes falhando para ausência de premissas, contagens sem duplicação e validação decimal.
- [ ] Implementar registro imutável, cálculos Decimal e contagens no escopo.
- [ ] Rodar testes com banco; esperado: aprovação sem skips.

## Task 2: confirmação no chat, contrato e painel

**Files:** services/chat_service.py; front/src/features/chat/MaterialCard.tsx; api/contracts/openapi.json; fixtures/examples.json; front/src/types/api.generated.ts; front/src/features/dashboard/SavingsPanel.tsx; DashboardPage.tsx; docs/dashboard.md; docs/aceitacao-mvp.md; AGENTS.md; .env.example; docker-compose.yml.
**Interfaces:** PICK_CANDIDATE validado gera CHAT_EXISTING_CONFIRMED; confirmação não cria pedido, material ou reserva.
- [ ] Testar confirmação explícita e painel sem premissas versus valor estimado.
- [ ] Atualizar contrato/exemplos/tipos e mostrar componentes, fórmulas, premissas e origem.
- [ ] Documentar operação e atualizar a matriz de aceitação da #26.
- [ ] Executar estilo, contrato, front e suites completas com banco; revisar e criar PR para homologacao.
