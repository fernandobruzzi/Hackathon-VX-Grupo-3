# Autorização por ação e recurso

A API recebe a identidade do provedor de sessão da #7. O papel não vem em
cabeçalho, query ou payload. A matriz de permissões fica em
`security/permissions.py`; `security/rbac.py` aplica os guards nas rotas e serviços.
O front usa as permissões de `/auth/me` para exibir controles, sem conceder acesso.

Uma permissão só vale se estiver tanto na identidade autenticada quanto na matriz
do grupo. Um grupo desconhecido ou uma lista de permissões sem grupo autorizado
não concede acesso. O guard devolve o papel efetivo, para registrar a ação correta
na auditoria de aprovação.

| Ação | Solicitante | Governança | Fiscal | Dev/TI | Almoxarifado | Compras |
|---|---|---|---|---|---|---|
| Chat e pedido próprio | Sim | Sim | Sim | Sim | Sim | Sim |
| Chamadas MCP do chat (`chat:diagnostics`) | Não | Não | Não | Sim | Não | Não |
| Unificação técnica | Não | Sim | Não | Não | Não | Não |
| Revisão de NCM | Não | Não | Sim | Não | Não | Não |
| Enriquecimento técnico | Não | Sim | Não | Não | Não | Não |
| Iniciar batch | Não | Sim | Não | Não | Não | Não |
| Reservar, entregar, reverter entrega (`stock:*`) | Não | Não | Não | Não | Sim | Não |
| Ler e tratar encaminhamentos (`purchasing:*`) | Não | Não | Não | Não | Não | Sim |
| Métricas de qualidade | Não | Sim | Sim | Não | Não | Não |
| Métricas financeiras | Não | Não | Sim | Não | Não | Não |
| Auditoria | Própria | Técnica | Fiscal | Não | Não | Não |

## Diagnóstico Dev/TI

As chamadas MCP de cada turno são diagnóstico técnico. A API sempre as persiste,
mas só as devolve, em `tool_calls` do turno e em `calls` da conversa salva, para
quem tem `chat:diagnostics`, concedida apenas pela role `ROLE_DEV_TI`. Para os
demais perfis os dois campos vêm vazios, inclusive em requisição direta: esconder a
aba no front não é a proteção. A role Dev/TI soma só essa permissão ao básico de
Solicitante e não aprova, publica, roda batch, vê métricas ou auditoria. Ela vê
apenas as chamadas das próprias conversas, no próprio tenant e centros, e as
chamadas não carregam tokens nem credenciais.

Para atribuir a role:

- **Cognito:** criar o grupo `ROLE_DEV_TI` no User Pool e adicionar a conta a ele.
  Na troca de persona da demo, listar a conta em `DEMO_ACCOUNTS` como `DEV_TI=<email>`.
- **Sessão local:** entrar com a conta `DEV_TI` na tela de login local.

## Almoxarifado e Compras

Os papéis operacionais da solicitação de material
([solicitacao-material.md](solicitacao-material.md#9-papéis-e-permissões)) somam ao
básico de Dev/TI, sem o diagnóstico, só as ações da própria fila:

- **`ROLE_ALMOXARIFADO`:** `stock:reserve`, `stock:deliver` e `stock:reverse`.
- **`ROLE_COMPRAS`:** `purchasing:read` e `purchasing:handle`.

Nenhum dos dois aprova cadastro, decide NCM, unifica, enriquece, roda batch, lê a fila
de saneamento, vê métricas ou auditoria. As rotas de reserva, entrega e encaminhamento
(#239, #240 e #241) usam `require_stock_action` e `require_purchasing_action` de
`security/rbac.py`. Os guards exigem a ação do papel e o centro dentro do escopo, então
cada papel só age na própria fila e nos centros autorizados. Os pedidos e as filas
nascem nessas issues. As permissões `requests:*` de criar e acompanhar a própria
solicitação entram com as rotas da #237.

Para atribuir os papéis:

- **Cognito:** criar os grupos `ROLE_ALMOXARIFADO` e `ROLE_COMPRAS` no User Pool e
  adicionar as contas. Na troca de persona da demo, listar as contas em
  `DEMO_ACCOUNTS` como `ALMOXARIFADO=<email>` e `COMPRAS=<email>`.
- **Sessão local:** entrar com as contas `ALMOXARIFADO` ou `COMPRAS` na tela de login local.

O papel certo não dispensa o escopo: o tenant precisa corresponder e todos os
centros envolvidos precisam estar autorizados. Um centro solicitado fora do
escopo recebe 403; um recurso de outro tenant, centro ou dono recebe 404 para não
revelar sua existência. O score e o UUID de uma entidade não concedem autorização.

O chat valida `chat:use`, centro, Origin e CSRF antes de reservar o turno ou
chamar o Agent. A conversa é conferida pelo tenant e dono na reserva e na
conclusão. Governança e Fiscal também não têm acesso geral às conversas alheias.
A exceção de leitura vinculada a uma revisão precisará de vínculo e autorização
específicos quando esse fluxo for entregue; não há atalho por papel administrativo.

A #20 consome os mesmos guards para leitura da fila, decisão técnica/fiscal,
centros e dados financeiros. A autorização é repetida nas tentativas idempotentes.
As decisões não aceitam ator, papel ou valores novos no payload.

Os testes cobrem a matriz completa, grupos desconhecidos, tenant/centros e
requisições com cookies locais reais: conversa de outro usuário, origem hostil,
CSRF inválido e tentativa de usar cabeçalho de papel. A integração da #20 verifica
os 403 de aprovação e os atores de auditoria com as contas locais persistidas.
