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

Entrega de preparação local com **Refs #26**, integrável em `homologacao` independentemente do aceite AWS; a #26 permanece aberta até a homologação final.

## Registro histórico de execução da branch original

As contagens e mutações abaixo pertencem à implementação original; não são reexecuções nem contagens da `homologacao` atual. As referências a pendências descrevem o estado daquela execução.

- Revisão independente: acrescentada a verificação dos vínculos persistidos de consolidação, estado do principal e redirecionamentos dos materiais bloqueados.
- Falhas controladas: omitir chamadas do painel falha na comparação com o MCP observado; impedir a gravação de `InventoryConsolidation` falha na conferência dos vínculos. As mutações são temporárias e não fazem parte da entrega.
- A #47 foi integrada durante a execução; a branch foi atualizada por rebase sobre `f4cae75`.
- API: 407 testes com PostgreSQL. Após o rebase, repetidos os 81 testes de sessão, chat, aprovação e dashboard; todos aprovados. MCP: 92 testes com banco após o rebase. Back: 351 testes após o rebase. Ruff, formatação Python e Prettier dos documentos novos aprovados.
- Continuação: a #22 foi integrada na main `b162946`; a branch foi atualizada por rebase para revalidar o cenário com as regras fiscais atuais. A #73 e a homologação AWS continuam pendentes.
- Após essa atualização, o cenário integrado passou com PostgreSQL e a suíte MCP completa passou com 94 testes, sem skips. Ruff, formatação e Prettier dos documentos novos foram conferidos novamente.

## Integração atual

Rebase sobre `5bb5b9febc6acd70901420570e6024eef6e5ac82`, que inclui `identity-v3`, classificador revisão 2, extrator revisão 9, resolução manual e enriquecimento com fonte. A consulta da proposta batch exige tenant, schema atual e estado PENDING; a leitura da auditoria percorre todas as páginas. Não há alteração de código de produção, kit, gabaritos ou dependências. Em 2026-11-07, a execução focada atual com PostgreSQL real (`TEST_DATABASE_URL` definido, `TMPDIR` exclusivo) passou: `cd mcp && uv run --locked pytest tests/test_mvp_acceptance.py -v` → **1 passed em 76,91 s, sem skips**. A paginação da auditoria foi exercitada com limite de um evento por página. `uv sync --locked`, Ruff check/format, Prettier dos dois documentos novos e `git diff --check` passaram. As três suítes completas não foram repetidas nesta preparação; as contagens acima continuam históricas. Compose HTTP, AWS/HTTPS/Cognito, três contas reais no navegador, Plano B EC2 e aceite humano permanecem sem verificação nesta execução.
