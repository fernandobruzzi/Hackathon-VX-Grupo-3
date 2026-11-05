# VX · Cadastro de Materiais — front (wireframe navegável)

Protótipo do web app do Desafio 01 (cadastro e saneamento de materiais), na identidade
**Ascensão** do Do Fundo do Poço. É o ponto de partida do `/front` da arquitetura:
Next.js (App Router) + Tailwind CSS v4 + componentes, com **dados mock** que seguem
os contratos da seção 6 da Arquitetura.

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # gera out/ (static export)
npm run typecheck  # checagem de tipos
```

Node 20.9 ou mais novo. O build sai em `out/`: é essa pasta que o target `api`
do Dockerfile deve copiar e servir (no lugar do `dist/` de um build Vite).

Entre pela tela de login e troque de persona no canto superior direito
(Solicitante, Governança PDM, Auditor fiscal). A navegação, os botões de
decisão e as telas mudam com o papel.

## Por que static export

A arquitetura serve o front pela API (FastAPI) na mesma origem HTTPS, com cookie
`__Host-vx_session` HttpOnly e modelo BFF. `output: "export"` gera HTML/JS
estáticos em `out/`, que o target `api` do Dockerfile copia e serve — nada muda
no deploy nem no fluxo de sessão. Consequências:

- Sem SSR, route handlers nem middleware: tudo que fala com a API é client component.
- Rotas dinâmicas (`/saneamento/[id]`) usam `generateStaticParams` com os mocks.
  Na integração, trocar por uma rota estática com query string
  (`/saneamento/revisao?id=…`) ou um catch-all servido pelo FastAPI.

## Telas e papéis

| Rota | Tela | Quem usa | Contrato |
|---|---|---|---|
| `/login`, `/auth/callback` | SSO Cognito + seletor demo | todos | 6.1 |
| `/chat` | Novo pedido por conversa: ficha PDM, faltantes, duplicidade, NCM, painel das chamadas MCP | todos | 6.2 |
| `/pedidos` | Meus pedidos · aba "Para publicar" (Governança) | todos | 6.5 |
| `/materiais` | Busca + estoque por centro, bloqueados apontam para o ativo | todos | catálogo |
| `/saneamento` | Fila técnica / fiscal / decididas | Governança, Fiscal | 6.3 |
| `/saneamento/[id]` | Revisão: antes, depois, estoque consolidado, mudanças com fonte, decisão com justificativa | Governança (técnica), Fiscal (NCM) | 6.3 |
| `/enriquecimento`, `/enriquecimento/[id]` | Evidências por atributo: fonte, trecho, confiança, divergência | Governança (decide), Fiscal (lê) | 6.5 |
| `/batch` | Iniciar job e acompanhar progresso/heartbeat | Governança | 6.5 |
| `/dashboard` | Qualidade da base; bloco financeiro só para o Fiscal | Governança, Fiscal | 6.4 |
| `/auditoria` | Trilha por escopo do papel | todos | — |

Quem não tem permissão vê a tela de 403 (o backend continua sendo a autoridade).

## Estrutura

```
src/
├── app/                      rotas (App Router); (app)/layout.tsx aplica o AppShell
├── components/
│   ├── ui/                   Button, Badge, Card, Eyebrow, PageHeader, Field, Input,
│   │                         Select, Textarea, Tabs, Table/Th/Td, Kpi, Code, EmptyState, Seta
│   │   └── status.tsx        badges de status (material, pedido, proposta, revisão)
│   └── shell/                AppShell (sidebar por permissão, PersonaSwitcher, tema), Guard (403)
├── features/                 uma pasta por área — mesma divisão do /front da arquitetura
│   ├── chat/                 ChatPage, MaterialCard, ToolCallsPanel
│   ├── sanitization/         QueuePage, ProposalReview
│   ├── enrichment/           EvidenceList, EvidenceReview
│   ├── dashboard/            DashboardPage  ← Pessoa 5 (exporta a página; a rota é da Pessoa 4)
│   ├── materials/ orders/ batch/ audit/
├── lib/                      auth (sessão simulada), permissions (matriz RBAC), format
├── mocks/                    dados de demonstração (fictícios, baseados no briefing VX/D01)
└── types/api.ts              tipos dos contratos — substituir pelos gerados do OpenAPI
```

## Design system

Tokens em `src/app/globals.css` (claro e escuro via `data-theme`), expostos ao
Tailwind com `@theme inline`: `bg-ink`, `bg-surface`, `text-verde`, `bg-esmeralda`,
`text-on-esmeralda`, `bg-profundo`, `text-alerta`, `rounded-md`… Regras que valem
no código:

- `esmeralda` é forma (seta, barras, CTA). Texto verde é `text-verde`.
- CTA: `bg-esmeralda text-on-esmeralda` nos dois temas — nunca texto branco.
- Um bloco `bg-profundo` por tela para o que importa; cards sem borda e sem sombra.
- Eyebrow `01 / RÓTULO` com a barrinha esmeralda (`<Eyebrow n="01">`).
- Fontes Montserrat e IBM Plex Mono locais via `next/font/local` (`src/fonts/`).

## Integração (próximos passos)

1. `src/lib/api.ts` com fetch `credentials: "include"`, `X-CSRF-Token` (de `/auth/me`)
   e `Idempotency-Key` em toda escrita; tratar 401/403/404/409/422/429/503 do formato
   de erro padronizado.
2. Trocar `AuthProvider` por `GET /api/v1/auth/me` e o seletor por
   `POST /api/v1/auth/demo/switch` (descartar caches e refazer `/auth/me`).
3. Gerar `types/api.ts` do `api/contracts/openapi.json` (ex.: `openapi-typescript`).
4. Substituir cada `mocks/*` pela chamada indicada no comentário do componente.
5. Chat: enviar `expected_session_version` e tratar 409 de turno concorrente.
