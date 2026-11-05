# Contratos de integração

`openapi.json` é a fonte dos tipos públicos do front. Define o alvo das issues de
implementação; publicar o contrato não implementa as rotas. A especificação gerada
pelo FastAPI em `/api/openapi.json` ainda lista somente as rotas implementadas.

O contrato cobre autenticação BFF, chat, fila e detalhe de propostas, decisões
técnicas/fiscais, enriquecimento, batch, pedidos e dashboard. As listagens de
materiais, pedidos, evidências e auditoria completam as telas já existentes.
Inclui também o contrato interno API → Agent (servidor interno e JWT exclusivo)
e o schema `BatchManifest`, com exemplo sem token do usuário.
Listagens usam `items` e `next_cursor`; `limit` fica entre 1 e 100 (padrão 20).
Identificadores de entidades são UUID; códigos ERP e IDs de chamadas MCP são texto.
Datas são UTC com `Z`; quantidades e dinheiro são strings decimais.

## Atualizar e verificar

Na raiz, `uv sync --all-packages` instala as dependências. Em `api/`, execute:

```bash
uv run pytest tests/test_contracts.py
```

Em `front/`:

```bash
npm ci
npm run api:generate
npm run api:check
npm test
npm run typecheck
npm run build
```

Inclua o OpenAPI, exemplos e tipos gerados no mesmo commit. O CI valida a
especificação, todos os exemplos e a geração reproduzível dos tipos. Não edite
`api.generated.ts` manualmente. `api.ts` mantém apenas aliases para os componentes.

`fixtures/examples.json` associa cada exemplo a método, rota e status. Cobre todas
as operações, escrita e leitura, os sete erros padronizados, decisão fiscal ainda
pendente da técnica, batch em execução/com erro e dashboard sem snapshot posterior.
`params` e `query` exemplificam os parâmetros; cabeçalhos de segurança vêm do
transporte, nunca de credenciais gravadas em fixtures. Dados são ilustrativos.

## Cliente HTTP do front

```ts
import { createApiClient, ApiError } from "@/lib/api";

// O getter deve ler a sessão atual; não capturar CSRF de uma sessão antiga.
const api = createApiClient({ getCsrfToken: () => currentSession?.csrf_token ?? null });
const me = await api.request("get", "/api/v1/auth/me");

const key = crypto.randomUUID();
try {
  await api.request("post", "/api/v1/sanitization/{id}/decide", {
    params: { id: proposal.id },
    body: {
      expected_version: proposal.version,
      review_area: "TECHNICAL",
      decision: "APPROVE",
      reason: "Identidade confirmada nas evidências.",
    },
    idempotencyKey: key,
  });
} catch (error) {
  if (error instanceof ApiError) {
    // Tratar error.status e error.error.{code,message,request_id,details} na tela.
  }
}
```

O cliente envia `credentials: include`, CSRF atual e uma chave UUID nas escritas.
É possível fornecer a chave para repetir a mesma operação após falha de rede;
reutilize também o mesmo payload. Não há repetição automática. `AbortSignal` é
aceito. Os tipos verificam método, rota, parâmetros, filtros, corpo e retorno.
O início do login é navegação para `/api/v1/auth/sso-start`, que responde 302;
o callback público usa a transação de login e não exige CSRF de sessão.

O backend deve conferir identidade, origem, ação e recurso. Sessões e grupos não
podem vir no corpo de decisões. Campos extras em escritas são recusados. O cookie
de sessão é opaco, Secure, HttpOnly e SameSite=Lax; tokens Cognito ficam no BFF.
As alternativas cookie e bearer estão declaradas no OpenAPI; CSRF aplica-se ao
cliente por cookie e não aos clientes bearer descritos na arquitetura.

Campos financeiros (`financial` e `members[].value_brl`) só são enviados com
`metrics:financial`. A resposta de qualidade os omite; omissão não significa zero.
`allowed_actions` descreve as ações autorizadas naquele recurso. O score apenas
ordena. A decisão aprova valores persistidos, nunca um novo valor no payload.
Chat incompleto retorna 200 com pendências e nunca publica um material.

Fila, revisão e auditoria podem usar a API com `NEXT_PUBLIC_DATA_SOURCE=api` no
build; sessão local e contrato privado do produtor estão descritos em
[`docs/aprovacoes.md`](../../docs/aprovacoes.md). As demais telas usam mocks.
Os mocks têm IDs amigáveis para o export estático; as fixtures de integração usam
UUIDs. A troca do provedor de sessão está em #7 e a ligação das telas ocorre nas
issues de cada fluxo.
