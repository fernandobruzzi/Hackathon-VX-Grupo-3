# Operação, CI e preparação para AWS

## O que o CI comprova

O CI preserva os testes Python, PostgreSQL 16 com pgvector, divergência entre
modelos e migrações, contratos OpenAPI, tipos do front, formatação e build estático.
O comando instalado `vx-db upgrade` roda duas vezes em um banco separado dos testes.

As execuções substituídas de um mesmo PR são canceladas. Execuções de `main` não
são canceladas. Dependências uv/npm e camadas Docker têm cache; uv é fixado na mesma
versão do Dockerfile. Cada imagem tem um escopo próprio no cache do BuildKit.

O job `images` constrói as três imagens e inicia um projeto Compose isolado:
migração, bootstrap, Agent e API. Depois reconstrói o índice e verifica HTML,
assets e um turno real API → Agent → MCP stdio → PDM → banco. A saúde da imagem
é liveness; não prova disponibilidade de todas as dependências.

As imagens incluem uma cópia imutável do kit original, sem modificar seus valores.
Assim o PDM e os dados de bootstrap existem fora dos bind mounts do Compose.
As dependências externas são instaladas antes do código, e o runtime não carrega uv,
testes ou o código-fonte completo. Alterações em código ainda reinstalam os pacotes
do workspace, mas preservam a camada das dependências externas.

## Verificação local

```bash
docker compose up --build -d --wait api
docker compose run --rm batch vx-back index
scripts/smoke_test.sh http://localhost:8000 --mode local
node --test scripts/tests/*.test.cjs
```

`DB_PORT` e `API_BIND_PORT` permitem escolher portas livres. A API e o PostgreSQL
publicam portas somente no loopback. O Agent não publica porta e usa processo init
para recolher subprocessos órfãos. O Compose espera o bootstrap e a saúde do Agent.

O modo padrão do smoke continua sendo apenas liveness, para compatibilidade:

```bash
scripts/smoke_test.sh https://origem-publica.example
```

Para testar uma sessão Solicitante real, depois da entrega do login e das aprovações:

```bash
scripts/smoke_test.sh https://origem-publica.example --mode authenticated --cookie-jar /caminho/privado/session.cookies
```

O arquivo deve usar o formato Netscape, conter `__Host-vx_session` Secure, host-only,
Path=/, e ficar fora do repositório com permissão 0600. O smoke não imprime tokens
nem cookies. Esse modo exige HTTPS, `/auth/me`, CSRF e RBAC 403; rotas ausentes
falham, sem serem tratadas como testes aprovados. O teste RBAC pressupõe que o guard
de papel execute antes da consulta ao UUID inexistente de proposta.

O modo local só aceita HTTP no loopback, cria uma sessão opaca e testa o chat e o logout.
Ele não comprova o Cognito na AWS. Configuração de sessão e migração para Cognito em
[`autenticacao.md`](autenticacao.md).
O cookie jar não comprova aceitação de cookies por um navegador nem executa PKCE;
o login completo e a navegação com IDs reais precisam de teste de navegador.

## Configurações que exigem administrador do GitHub

Na auditoria de 5/11/2026, `main` estava sem proteção e os três métodos de merge
estavam habilitados. Confirmar novamente antes de alterar:

- Exigir PR e os checks `style`, `python (back)`, `python (mcp)`, `python (api)`,
  `database`, `front`, `images` e `policy`.
- Exigir atualização em relação à base e histórico linear.
- Permitir somente rebase merge; histórico linear também aceita squash.
- Bloquear push direto e bypass que tornaria os checks opcionais.
- Habilitar exclusão automática da branch de origem após merge.

O workflow de política verifica branch `<type>/<issue>-<slug>`, atribuições
automáticas conhecidas e merge commits. Não interpreta toda menção em linguagem
natural, nem impede que um PR enfraqueça seu próprio workflow. Proteger os workflows
por revisão e checks obrigatórios é uma decisão administrativa adicional.

## Pendências de integração e limites conhecidos

Revalidar estes itens na versão atual de `main`, pois há entregas simultâneas:

| Tema | Entrega / ação |
|---|---|
| Login, sessão BFF e CSRF | Implementados localmente; homologação Cognito/HTTPS na #91 |
| RBAC e aprovação transacional | Implementados; smoke autenticado exige uma sessão real |
| Identidade por turno no MCP | Corrigida no `main` usado nesta entrega: Caller e centros seguem do JWT ao subprocesso sem alterar `os.environ` global; preservar em novas implementações |
| Batch RunTask/heartbeat | Runner `ecs_fargate` preparado na #6; testar PassRole e task real na conta |
| Rotas estáticas com IDs reais | Saneamento já usa `/saneamento/revisao?id=...`; enriquecimento ainda tem páginas mock |
| Implantação ECS/RDS | #6; ainda precisa validação real na conta do workshop |
| HTTPS alternativo | Render e script EC2/Caddy em `docs/ec2.md`; testar conta/TLS/login na #29 |
| Seed/reset da demo | #34; bootstrap idempotente não equivale a reset de sessão/proposta |

## Requisitos do primeiro deploy

1. Confirmar conta, região permitida, expiração das credenciais e roles existentes.
   Listar recursos não comprova `CreateRole`, `PassRole` ou criação de serviço.
2. Express exige role de infraestrutura além das roles de execução e aplicação.
   Reutilizar roles somente se trust policy e permissões forem compatíveis.
3. Task web: `awsvpc`, Fargate, container `Main`, uma porta TCP nomeada em 8000,
   Agent em 8001, `AGENT_URL=http://127.0.0.1:8001`, init e healthchecks explícitos.
   Os containers da task compartilham IAM; usar credenciais SQL distintas.
4. Subnets públicas precisam de rota para internet gateway e IP público na task
   para saída sem NAT. RDS privado recebe 5432 somente dos SGs de aplicação/batch.
5. Testar migrações reais no RDS como `migration_user`, nunca como superuser local.
   Verificar extensão `vector`, owner, criação/alteração de roles e logins de cada serviço.
6. Usar TLS `verify-full` e CA do RDS. Construir URLs com encoding correto para
   senhas; não interpolar senhas arbitrárias em URLs de Compose.
7. Injetar segredos por Secrets Manager, distinguindo permissões da execution role
   e task role. Rotação exige atualizar o banco e reiniciar consumidores.
8. Executar migração/bootstrap uma vez, com exclusão mútua. Não entregar a senha
   de migração ao serviço web.
9. Fazer invocação real do Bedrock: Titan V2 usa 1024 dimensões por padrão; pedir 512.
   Conferir modelo/profile, regiões de destino, permissões e cotas. Não iniciar
   milhares de chamadas de embeddings sem orçamento, limites e checkpoints.
10. Registrar callback HTTPS exato, PKCE S256, state/nonce e origem pública correta.
    Não copiar defaults locais para o ambiente implantado.

O Plano B precisa de HTTPS antes de configurar Cognito. Caddy com hostname público
que resolva para o IP estável da EC2 reduz dependências de infraestrutura, mas requer
80/443, emissão ACME e armazenamento persistente. CloudFront oferece hostname e
certificado padrão, mas exige espera de implantação e encaminhamento de cookies,
query e headers, sem cache em auth/API. Um ALB novo não fornece certificado válido
para seu próprio hostname por si só.

Preflight, configuração de tasks, segredos por serviço e sequência de publicação
estão em [`deployment/README.md`](../deployment/README.md). Os comandos sem `--apply`
renderizam offline e não comprovam permissões ou conectividade da conta do workshop.

## Referências oficiais

- [ECS Express: task definition e container Main](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html)
- [Role de infraestrutura ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html)
- [Extensões no RDS PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Extensions.html)
- [Titan Embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)
- [Cognito: callback e PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)
- [Caddy: HTTPS automático](https://caddyserver.com/docs/automatic-https)
- [Cache Docker no GitHub Actions](https://docs.docker.com/build/ci/github-actions/cache/)
