# MVP Acceptance Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Tornar repetíveis os critérios locais da #26 e registrar o que ainda exige homologação AWS.

**Architecture:** Reutilizar as suítes existentes e o banco descartável do MCP. Acrescentar a ligação API → Agent → MCP stdio real, com sessões locais opacas, propostas do batch, aprovação e auditoria persistidas. O transporte HTTP entre API e Agent fica em memória; suas implementações são reais.

**Tech Stack:** pytest, FastAPI TestClient, httpx ASGITransport, PostgreSQL/pgvector e os pacotes do workspace uv.

**Spec:** https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/26 e `docs/arquitetura.md`, seção “Critérios para considerar o MVP pronto”.

## Global Constraints

- Não alterar regras das issues atribuídas a outras pessoas.
- Login local não comprova Cognito nem infraestrutura AWS.
- Chat não publica material; propostas de saneamento vêm do batch.
- Não adicionar dependências.
- Manter a issue aberta enquanto faltarem integrações e homologação AWS.

## Review Focus

- Chamadas MCP devem ter sido executadas e persistidas, não apenas declaradas na resposta.
- Sessão de outra persona não deve acessar uma conversa pelo UUID.
- Repetição de aprovação não deve duplicar aplicação nem auditoria.
- Aprovação técnica pendente de Fiscal não deve modificar o mestre.
- Métricas aplicadas não devem ser apresentadas como economia realizada.

### Task 1: Integrar o fluxo local real

**Files:** Create `mcp/tests/test_mvp_acceptance.py`.

- [x] Usar o fixture `database` para kit e índice reais e executar o batch com `batch_user`.
- [x] Exercitar sessão local → API → Agent → MCP e comparar painel, chamadas observadas e mensagem persistida.
- [x] Exercitar isolamento da conversa, aprovação, repetição, auditoria, conservação de estoque e dashboard.
- [x] Executar o teste com PostgreSQL e confirmar que uma mutação no painel é detectada.

### Task 2: Registrar cobertura e limites

**Files:** Create `docs/aceitacao-mvp.md`; update `AGENTS.md` apenas com o comando e a referência da nova verificação.

- [x] Mapear todos os critérios para testes existentes e a nova integração.
- [x] Documentar os comandos, escopo local e pendências #22, #47, #73 e AWS.
- [x] Rodar suítes API/MCP com banco, back e verificações de estilo.
- [x] Revisar o diff e atualizar a branch com main.

Entrega por PR em rascunho com evidências e pendências; a #26 permanece aberta até a homologação final.

## Registro de execução

- Revisão independente: acrescentada a verificação dos vínculos persistidos de consolidação, estado do principal e redirecionamentos dos materiais bloqueados.
- Falhas controladas: omitir chamadas do painel falha na comparação com o MCP observado; impedir a gravação de `InventoryConsolidation` falha na conferência dos vínculos. As mutações são temporárias e não fazem parte da entrega.
- A #47 foi integrada durante a execução; a branch foi atualizada por rebase sobre `f4cae75`.
- API: 407 testes com PostgreSQL. Após o rebase, repetidos os 81 testes de sessão, chat, aprovação e dashboard; todos aprovados. MCP: 92 testes com banco após o rebase. Back: 351 testes após o rebase. Ruff, formatação Python e Prettier dos documentos novos aprovados.
