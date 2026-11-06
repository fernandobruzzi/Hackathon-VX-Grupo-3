# Autorização por ação e recurso

A API recebe a identidade do provedor de sessão da #7. O papel não vem em
cabeçalho, query ou payload. A matriz de permissões fica em
`security/permissions.py`; `security/rbac.py` aplica os guards nas rotas e serviços.
O front usa as permissões de `/auth/me` para exibir controles, sem conceder acesso.

Uma permissão só vale se estiver tanto na identidade autenticada quanto na matriz
do grupo. Um grupo desconhecido ou uma lista de permissões sem grupo autorizado
não concede acesso. O guard devolve o papel efetivo, para registrar a ação correta
na auditoria de aprovação.

| Ação | Solicitante | Governança | Fiscal |
|---|---|---|---|
| Chat e pedido próprio | Sim | Sim | Sim |
| Unificação técnica | Não | Sim | Não |
| Revisão de NCM | Não | Não | Sim |
| Enriquecimento técnico | Não | Sim | Não |
| Iniciar batch | Não | Sim | Não |
| Métricas de qualidade | Não | Sim | Sim |
| Métricas financeiras | Não | Não | Sim |
| Auditoria | Própria | Técnica | Fiscal |

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
