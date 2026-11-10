# VX · Cadastro e saneamento de materiais

Solução do Grupo 3 para o **Desafio 01 — "Do Fundo do Poço"** do Hackathon VX
(Visagio), de 5 a 8 de novembro de 2026: sanear uma base mestre de materiais
industriais, padronizar novos cadastros e completar informações faltantes com
fonte registrada.

> **Status:** o hackathon terminou. O repositório fica como registro do MVP
> entregue e como projeto de portfólio do time. Não há manutenção ativa.

## O problema

Uma peça pode estar no almoxarifado e continuar invisível para quem precisa
dela. Descrições diferentes criam códigos diferentes para o mesmo item, e um
pedido incompleto — um parafuso sem classe de resistência, por exemplo — não
permite saber se o material atende à manutenção. O resultado é estoque
duplicado, compras desnecessárias e NCM fiscal inconsistente.

## O que construímos

Uma plataforma em que **a mesma regra de domínio** valida o saneamento em lote
e o cadastro conversacional, e em que **nada altera a base mestre sem aprovação
humana auditada**.

- **Saneamento em lote:** classifica cada material no padrão PDM, extrai
  atributos, encontra duplicidades por identidade verificada e propõe
  unificações, correções de descrição, unidade, grupo de mercadoria e NCM.
- **Cadastro por chat:** um agente (MCP + Bedrock Claude Sonnet 5, com
  fallback por regras) entrevista o solicitante, pergunta só o que o PDM exige,
  busca itens semelhantes antes de permitir um novo código e valida NCM.
- **Fila de aprovação:** Governança, Técnico e Fiscal decidem propostas em
  transações com auditoria, idempotência e checagem otimista de versão. NCM só
  muda com aprovação fiscal.
- **Enriquecimento com fonte:** os 15 produtos reais do kit são enriquecidos a
  partir de fontes públicas revisadas; cada valor guarda sua evidência.
- **Solicitação de material:** reserva, entrega, reversão e encaminhamento para
  Compras, com invariantes de quantidade e estoque original imutável.
- **Dashboard:** funil de propostas e snapshot antes/depois, sem confundir
  proposta com economia realizada.

### Princípios

- Unir itens diferentes custa mais que perder uma duplicidade: na dúvida, vai
  para revisão humana. `ranking_score` só ordena; nunca autoriza merge.
- Propostas, nunca edição direta. Só a API aplica mudanças, em uma transação
  com auditoria.
- Todo valor transformado guarda o original e a regra aplicada; todo valor
  enriquecido guarda a fonte.
- Algoritmos que podem decepcionar (classificação, extração, matching,
  embeddings, LLM) ficam atrás de repositórios trocáveis e medidos.

## Resultados

Rodada integral local sobre o kit do desafio, em 8/11/2026
([evidência](front/pitch/evidence/batch-final.json)):

| Métrica | Valor |
|---|---|
| Materiais analisados | 23.554 (sem erros de análise) |
| Materiais com proposta | 13.348 |
| Propostas geradas | 16.721 |
| Unificações propostas | 1.124 grupos, 2.536 materiais |
| Correções de NCM propostas | 6.083 (680 preenchimentos, 884 trocas, 4.519 de formato) |
| Correções de descrição PDM / unidade | 8.277 / 887 |
| Tempo total do lote | ~12,7 min, sem chamadas de modelo |

As medições de qualidade são de **coortes de desenvolvimento**, não de revisão
independente; os limites estão em [`front/pitch/evaluation.md`](front/pitch/evaluation.md)
e [`docs/avaliacao-saneamento.md`](docs/avaliacao-saneamento.md).

## Arquitetura

```
Navegador → API (FastAPI, serve o build do front) → PostgreSQL + pgvector
                ├─ HTTP interno → Agent (chatbot) ─ MCP stdio → servidor MCP → Bedrock
                └─ ECS RunTask / subprocesso → Batch → S3, propostas
```

| Pasta | Conteúdo |
|---|---|
| `back/` | Regras de domínio compartilhadas (PDM, identidade, NCM), pipelines do lote, enriquecimento |
| `mcp/` | Servidor MCP, ferramentas e chatbot (`vx-agent`) |
| `api/` | API FastAPI, sessões BFF, RBAC, aprovações, auditoria, banco e migrações |
| `front/` | Next.js (export estático), identidade visual "Ascensão" |
| `deployment/`, `scripts/` | AWS (ECS Fargate, RDS, S3, Cognito, Bedrock) e Plano B em EC2 + Compose |
| `data/` | Kit de dados do desafio (somente leitura) |
| `docs/` | Arquitetura, regras de domínio, medições e runbooks |

**Stack:** Python 3.12 (uv workspace), FastAPI, SQLAlchemy/Alembic,
PostgreSQL 16 + pgvector, MCP, Amazon Bedrock (Claude Sonnet 5), Next.js +
TypeScript + Tailwind, Docker Compose, AWS ECS/RDS/S3/Cognito, GitHub Actions.

## Rodar localmente

Requer Docker. Sem conta AWS: o login usa contas locais de teste e o chat
planeja por regras quando `BEDROCK_CHAT_MODEL_ID` está vazio.

```bash
docker compose up --build
```

A aplicação sobe em http://localhost:8000, com o kit carregado e o índice de
busca construído. Para o roteiro completo da demo:

```bash
DEMO_MODE=true scripts/load_demo_data.sh
```

```bash
scripts/smoke_test.sh http://localhost:8000 --mode flow
```

Desenvolvimento por módulo (Python 3.12, [uv](https://docs.astral.sh/uv/),
Node 20.9+):

```bash
uv sync --all-packages --locked
(cd back && uv run --locked pytest)
(cd mcp && uv run --locked pytest)
(cd api && uv run --locked pytest)
(cd front && npm ci && npm run dev)
```

Comandos, regras e fluxo de trabalho do time estão em [`AGENTS.md`](AGENTS.md).

## Como trabalhamos

Em quatro dias, cinco pessoas integraram 170+ PRs e 160+ issues planejadas em
milestones por checkpoint. Fluxo `branch → homologacao → main`, commits
atômicos em Conventional Commits, rebase-merge e histórico linear, contratos
OpenAPI como fonte dos tipos do front, CI completa só na promoção para
produção e deploy por OIDC.

## Time

- [Miguel Cerne](https://github.com/Cerne17)
- [Hugo Antunes](https://github.com/hugo-antunes19)
- [Fernando Bruzzi](https://github.com/fernandobruzzi)
- [bepo7](https://github.com/bepo7)
- [EnzoSamp](https://github.com/EnzoSamp)

## Documentação

- [Guia do time e dos agentes](AGENTS.md)
- [Arquitetura e contratos](docs/arquitetura.md)
- [Identidade de materiais](docs/identidade-materiais.md)
- [Classificação PDM](docs/classificacao.md)
- [NCM](docs/ncm.md)
- [Aceitação do MVP](docs/aceitacao-mvp.md)
- [Demo](docs/demo.md)
- [Pitch: roteiro, mercado e ROI](front/pitch/)
- [Deploy AWS](deployment/README.md)
- [Front](front/README.md) · [Dados](data/README.md) · [Brainstorm](docs/brainstorm.md)
