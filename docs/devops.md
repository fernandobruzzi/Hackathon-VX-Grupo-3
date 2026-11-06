# Operação, CI e preparação para AWS

## Integração com testes locais

O fluxo é `branch da issue → homologacao → main`. `homologacao` reúne entregas
validadas localmente; `main` representa produção. As duas branches são permanentes.
A branch `homologacao` não é, por si só, um ambiente implantado na AWS.

Crie branches `<type>/<issue>-<slug>` a partir de `homologacao`, atualize-as por
rebase e abra os PRs com `--base homologacao`. Cada PR leva os comandos e resultados
dos checks locais, incluindo testes pulados e verificações não executadas.
Integre com rebase apenas depois de conferir essa evidência. Os comandos por área
estão no [guia do time](../AGENTS.md#commands).

Os workflows `CI` e `Repository policy` só são disparados por `pull_request`
com destino `main`. PRs para `homologacao`, inclusive a sincronização vinda de
`main`, e pushes, inclusive o merge em `main`, não iniciam esses workflows. Não há
gatilho agendado ou manual. Isso concentra os minutos de CI na promoção para produção, sem executar de novo o mesmo lote após o
merge. Corrija falhas de desenvolvimento localmente antes de publicar outra versão.

## Promover para produção

1. Congele novas integrações em `homologacao` até concluir a promoção e a
   sincronização abaixo. Confira os checks locais de integração do lote e liste
   suas entregas no PR; mantenha o lote abaixo do limite de 250 commits da política.
2. Abra o PR no mesmo repositório:

   ```bash
   gh pr create --base main --head homologacao
   ```

3. Aguarde todos os checks completos e `policy`. O checkout padrão do evento
   `pull_request` testa a combinação proposta com `main`. Se houver conflito ou
   `main` mudar, resolva e revalide a combinação antes de integrar; não rebase a
   branch compartilhada nem contorne os checks obrigatórios.
4. Integre **com merge commit**, preservando os SHAs das entregas e a branch:

   ```bash
   gh pr merge <n> --merge
   ```

   Rebase ou squash nessa etapa reescreveriam os commits de `homologacao` e fariam
   as próximas promoções reapresentar entregas antigas. O repositório precisa
   permitir merge commits; veja a configuração administrativa abaixo.
5. Abra o PR de sincronização de volta, preservando a exigência de PR nas duas
   branches:

   ```bash
   gh pr create --base homologacao --head main
   gh pr merge <n-da-sincronizacao> --merge
   ```

   Esse PR também usa merge commit e não dispara validação remota. Confira o
   histórico e o diff antes de integrar: ele traz o merge já validado de produção
   para a branch de integração. Se houve integração concorrente ou conflitos,
   mantenha o congelamento e reconcilie com o responsável pela entrega, sem
   force-push, reset ou exclusão das branches.
6. Confirme que `main` é ancestral de `homologacao` e libere a integração. Os SHAs
   das pontas podem diferir por causa do merge de sincronização:

   ```bash
   git fetch origin
   git merge-base --is-ancestor origin/main origin/homologacao
   ```

A promoção integra código em `main`; deploy e migração de produção seguem o
[runbook de publicação](../deployment/README.md).

## O que o CI comprova

O CI preserva os testes Python, PostgreSQL 16 com pgvector, divergência entre
modelos e migrações, contratos OpenAPI, tipos do front, formatação e build estático.
O comando instalado `vx-db upgrade` roda duas vezes em um banco separado dos testes.
Os nomes dos jobs completos permanecem os mesmos.

Uma atualização nova do mesmo PR de produção cancela a execução anterior.
Dependências uv/npm e camadas Docker têm cache; uv é fixado na versão do Dockerfile.
Cada imagem tem escopo próprio no BuildKit. Um job cancelado pode não salvar cache;
`Remove isolated stack` continua sendo executado para limpar os recursos.

Este workflow é descartável: não publica, não migra banco fora do runner e não usa
segredos da AWS. `scripts/tests/test_ci_queue.py` protege essa separação. Deploy e
migração reais seguem o lock S3 do runbook; se forem automatizados, precisam de
workflow e grupo próprios com `cancel-in-progress: false`.

### Histórico da fila (#108)

Em 6/11/2026, execuções de `main` separadas por 23 e 42 segundos esperaram 265 e
278 segundos na fila, com duração útil próxima de cinco minutos. A #108 passou a
cancelar execuções superadas. A política atual (#178) remove o disparo por push e
agrupa a validação no PR de promoção. Para inspecionar execuções existentes:

```bash
uv run --package vx-materials-back python scripts/ci_queue_report.py --limit 20
```

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

Antes de abrir ou integrar um PR, execute as suítes das áreas afetadas. Regras
compartilhadas exigem os três módulos. Os processos pytest são separados porque
há arquivos com o mesmo nome em módulos diferentes:

```bash
uv sync --all-packages --locked
(cd back && uv run --locked pytest)
(cd mcp && uv run --locked pytest)
(cd api && uv run --locked pytest)
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
```

Para CI, política ou scripts operacionais:

```bash
uv run --locked --package vx-materials-back pytest scripts/tests
node --test scripts/tests/*.test.cjs
```

Banco, migrações e busca exigem as suítes API/MCP com PostgreSQL e
`TEST_DATABASE_URL`, conforme o [guia](../AGENTS.md#commands). Dê a cada execução
concorrente seu próprio banco `_test`. Sem a variável, os testes de banco são
pulados; relate os skips em vez de tratá-los como validação concluída.

Para front ou contratos, rode em `front/`:

```bash
npm ci
npm run format:check
npm run api:check
npm test
npm run typecheck
npm run build
```

Para Docker e integração entre serviços, construa e teste a stack local:

```bash
docker compose up --build -d --wait api
scripts/smoke_test.sh http://localhost:8000 --mode local
```

O modo `flow` é uma verificação local adicional de batch, aprovações e auditoria,
com reset da demo; não é executado pelo CI atual:

```bash
DEMO_MODE=true scripts/load_demo_data.sh
scripts/smoke_test.sh http://localhost:8000 --mode flow
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

Na verificação de 6/11/2026, o repositório permitia apenas rebase merge, com merge
commits desabilitados. A conta usada nesta mudança tinha push, sem administração.
Os itens abaixo são requisitos de ativação, não configurações já aplicadas:

- Definir `homologacao` como branch padrão para que novos PRs tenham essa base.
- Em `main`, exigir PR, atualização em relação à base e os checks `style`,
  `python (back)`, `python (mcp)`, `python (api)`, `database`, `front`, `images`
  e `policy`, sem bypass ou push direto.
- Habilitar merge commits para promoção e sincronização e remover a exigência
  de histórico linear das duas branches permanentes, se houver. Preservar rebase
  para os PRs de trabalho; squash permanece desabilitado.
- Em `homologacao`, exigir PR e remover checks obrigatórios de CI e política.
  Eles não são disparados nessa base e ficariam pendentes indefinidamente.
  PRs de trabalho exigem evidência local; a sincronização `main` → `homologacao`
  também passa por PR, sem exceção de push direto.
- Proteger as duas branches de force-push e exclusão. Preservar `homologacao`
  após promoções: desabilitar a exclusão automática de branches de origem ou
  garantir a proteção que impede sua exclusão. Excluir branches de trabalho
  explicitamente após o merge.
- Revisar os workflows como parte da promoção: um PR pode alterar seu próprio
  workflow, e a checagem de política não substitui revisão de código.

A política aceita a promoção somente da `homologacao` deste repositório para
`main`, e a sincronização de `main` de volta para `homologacao`. As duas operações
preservam merge commits. Para PRs de trabalho, a validação local mantém o formato
de branch, atribuições automáticas conhecidas e a restrição a merge commits por
conferência na revisão. `node --test` testa o validador com exemplos; não inspeciona
automaticamente a branch e os commits da entrega.

### Ativar o fluxo e migrar PRs existentes

1. Criar `homologacao` a partir da `main` atual, integrar nela a mudança de
   workflows/documentação e aplicar as configurações administrativas acima.
2. Revisar cada PR de trabalho ainda aberto para `main` com seu responsável.
   Atualizar a branch sobre `homologacao`, repetir os testes locais, mudar a base
   com `gh pr edit <n> --base homologacao` e conferir o diff e as evidências.
   A troca de base pode invalidar comentários e aprovações.
3. Fazer a primeira promoção pelo procedimento acima. A validação completa
   continua obrigatória antes de entrar em `main`. Até integrar a mudança em
   `homologacao`, outros PRs de trabalho ainda podem carregar os gatilhos antigos.
   Depois da integração, suas branches precisam receber a nova base e ter o
   destino revisado. A mudança fica presente nas duas branches após a promoção;
   o commit que entra em `main` já contém o workflow sem gatilho de push.
4. Conferir a branch padrão antes de depender de `Closes #<n>`: o GitHub só fecha
   automaticamente issues quando o PR entra na branch padrão. Enquanto ela for
   `main`, fechar manualmente a issue após a integração em `homologacao`, citando
   o PR integrado.

Mudar a base de um PR não cancela uma execução já iniciada. Esta mudança não
cancela execuções antigas nem altera automaticamente PRs existentes; qualquer
intervenção neles deve ser combinada explicitamente com seus responsáveis.
A mudança dos gatilhos não recupera minutos já consumidos.

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
