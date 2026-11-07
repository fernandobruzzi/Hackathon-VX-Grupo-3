# Autenticação local e conexão com Cognito

O fluxo local usa três contas fixas, persistidas no banco, com sessões opacas e
papéis conferidos pela API. A seleção da conta existe somente em desenvolvimento.
O navegador não decide ator, tenant, permissões ou centros. A autorização das
ações e recursos é centralizada na #9.

## Local primeiro

```bash
docker compose up --build -d --wait
scripts/smoke_test.sh http://localhost:8000 --mode local
```

O Compose habilita `APP_ENV=local` e `LOCAL_TEST_SESSION=true`. A flag equivalente
`ENABLE_LOCAL_TEST_SESSIONS=true` também é reconhecida. Fora do Compose, as flags
ficam desligadas por padrão. A origem local acompanha `API_BIND_PORT`, salvo se
`APP_ORIGIN` for informada explicitamente. A API recusa as flags fora do ambiente local, com
marcadores de runtime AWS ou origem que não seja loopback. Não há mais sessão
anônima automática no chat: primeiro é necessário entrar na tela de login.

As contas representam Solicitante, Governança PDM e Fiscal. Cada sessão dura uma
hora, guarda apenas o hash do cookie no banco e exige Origin e CSRF nas escritas
protegidas. Trocar de conta revoga a sessão local anterior e descarta o estado
privado das telas. Logout revoga a sessão no servidor. Em HTTP local, o cookie
`vx_local_session` é HttpOnly e SameSite=Lax; essa exceção não existe no Cognito.

O front consulta `/api/v1/auth/config` para descobrir o modo do servidor e
`/api/v1/auth/me` para obter identidade, permissões, centros e CSRF. Respostas 401
limpam a sessão do front e levam ao login. O modo API é o padrão do build;
`NEXT_PUBLIC_DATA_SOURCE=mock` mantém apenas o protótipo demonstrativo.

## Conectar Cognito sem mudar código

Quando a infraestrutura existir, fornecer no ambiente da mesma imagem:

```dotenv
APP_ENV=production
LOCAL_TEST_SESSION=false
ENABLE_LOCAL_TEST_SESSIONS=false
AUTH_BACKEND=cognito
APP_ORIGIN=https://<origem-publica>
AWS_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_<pool>
COGNITO_APP_CLIENT_ID=<client>
COGNITO_DOMAIN=https://<dominio-cognito>
AUTHORIZED_CENTER_CODES=1100,1200,1300,2100,2200,9000
SESSION_ENCRYPTION_KEY=<chave-fernet-fornecida-por-secret-manager>
```

Gerar a chave Fernet uma vez e guardá-la no gerenciador de segredos; ela precisa
permanecer igual entre réplicas e reinicializações. Trocar a chave invalida as
sessões existentes. `COGNITO_APP_CLIENT_SECRET` é opcional, para app client
confidencial. `COGNITO_RESOURCE_AUDIENCE` confere o audience de access tokens
quando esse recurso estiver configurado no Cognito.

No app client, habilitar Authorization Code, scopes `openid email profile` e
callback exato `<APP_ORIGIN>/auth/callback/`. Criar os grupos
`ROLE_SOLICITANTE`, `ROLE_GOVERNANCA_PDM`, `ROLE_AUDITOR_FISCAL`, `ROLE_ALMOXARIFADO`,
`ROLE_COMPRAS` e, para quem consulta as chamadas MCP do chat, `ROLE_DEV_TI`, e associar
as contas corretas (ver [autorizacao.md](autorizacao.md#diagnóstico-devti) e
[Almoxarifado e Compras](autorizacao.md#almoxarifado-e-compras)). Grupos desconhecidos não concedem acesso. Neste MVP de uma
empresa, os centros autorizados são definidos no backend para todas as contas;
uma política por usuário pode substituir essa configuração sem confiar no front.

O front passa automaticamente a redirecionar ao Cognito e oculta a seleção de
contas locais. No logout, a API revoga a sessão e devolve `provider_logout_url`.
O front segue esse endereço para encerrar também a sessão do Hosted UI, que volta
para `/login/`. Sem isso, o próximo login entraria na mesma conta sem pedir senha.
O app client precisa listar `<APP_ORIGIN>/login/` em `LogoutURLs`. Não existe troca de papel por payload. A alternância entre sessões
Cognito previamente autenticadas pertence à #8; até lá, sair e entrar novamente
é o caminho para trocar de conta no provedor.

## Garantias do protocolo

`sso-start` registra state, nonce e PKCE S256 por dez minutos, cifrando os segredos
e vinculando a transação ao navegador. `sso-callback` confere Origin, state,
cookie de vínculo e expiração e consome a transação antes da troca do código.
Falhas exigem começar outro login; callbacks repetidos não criam novas sessões.

A API valida assinatura RS256 com JWKS, emissor, expiração, emissão, `token_use`,
`client_id` do access token e audience do ID token. Também confere scopes, nonce,
identidade comum aos tokens e `at_hash` quando presente. Os grupos validados do
access token determinam permissões; o ID token só fornece o perfil.

Tokens ficam cifrados com Fernet no banco e são revalidados nas requisições.
O cookie Cognito `__Host-vx_session` é Secure, HttpOnly, SameSite=Lax, host-only
e Path=/. Expiração, revogação, usuário desabilitado ou contexto de navegador
incorreto recusam a sessão. Não há renovação silenciosa: ao expirar o token,
o usuário entra novamente. Cookies exigem CSRF; bearer validado usa a mesma
identidade e permissões, sem depender de cookies.

As respostas de autenticação não são armazenadas em cache. O callback remove
code/state da URL no front. O servidor desabilita access logs para não registrar
esses códigos; não há tokens em respostas públicas, mensagens de erro ou logs.

## O que foi verificado

Testes locais usam assinaturas RSA reais, endpoint OAuth controlado, PostgreSQL
e cookies do cliente HTTP. Cobrem claims inválidos, assinatura, state/nonce,
vínculo com navegador, replay, criptografia, expiração, CSRF, logout e três contas
locais. Isso não comprova funcionamento no serviço AWS.

Na conta do workshop ([#91](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/91)),
o login foi conferido com Cognito real e três contas nos grupos reais, em HTTPS
pelo domínio próprio:
- cookie `__Host-vx_session` Secure, HttpOnly, SameSite=Lax, host-only e `Path=/`;
- `/auth/me` com papéis e permissões corretos e sem tokens;
- logout recusando a sessão;
- sessões locais ausentes do runtime.
A aplicação não apresenta sessões de teste como autenticação Cognito.


## Transições de sessão no navegador

Login, troca de persona e logout são serializados: enquanto uma operação está em
andamento, os controles de autenticação ficam desabilitados e a área privada
mostra “Atualizando sessão”. O bloqueio vale também antes de o próximo render
ocorrer, impedindo dois cliques de dispararem duas trocas.

Cada transição invalida respostas de requisições iniciadas na sessão anterior.
Isso inclui o carregamento inicial, refresh e erros 401 atrasados: um erro antigo
não encerra uma nova sessão válida. Um 401 da sessão atual continua levando ao
login. Ao confirmar a sessão, a aplicação remonta a área privada para descartar
estado e cursores, inclusive quando o login é da mesma conta.

Se uma resposta de autenticação se perder, o navegador pode já ter recebido o
cookie novo. Por isso a aplicação consulta `/auth/me` antes de liberar os controles
outra vez. Se nem essa consulta confirmar a identidade, os dados privados são
retirados da tela e o login fica disponível para nova tentativa. Cookies, tokens,
papéis e permissões continuam sujeitos à validação do backend.

No Cognito, o bloqueio permanece até o redirecionamento ou recarregamento; a nova
página confirma a sessão no servidor. A inicialização da página de callback não
invalida a troca de código nem a consulta de perfil que ela está concluindo.
