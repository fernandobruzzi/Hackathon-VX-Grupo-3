# Preparar e publicar na conta do workshop

Estas ferramentas foram validadas **localmente**, inclusive contra os contratos
do SDK AWS. Nenhum recurso foi provisionado na AWS e nenhuma permissão da conta do
workshop foi comprovada. A homologação RDS/ECS continua na #6 e o login real na #91.

## Configuração e validação offline

Pré-requisitos no computador: Git, Python 3.12, uv e Docker. Da raiz:

```bash
cp deployment/aws.example.json deployment/aws.local.json
scripts/preflight_aws.sh --config deployment/aws.local.json --offline --render-dir deployment/generated
scripts/bootstrap_aws.sh --config deployment/aws.local.json
scripts/deploy_ecs.sh --config deployment/aws.local.json
uv run --package vx-materials-back python -m unittest discover -s scripts/tests -p test_aws.py
```

Os três comandos sem `--apply` não criam sessão AWS. O exemplo possui conta,
ARNs e digests fictícios: substituir pelos recursos autorizados. `aws.local.json`
e `generated/` são ignorados pelo Git e não entram no contexto Docker.
Configuração contém identificadores e ARNs, nunca URLs de banco ou senhas.

O render produz `web`, `migrate`, `bootstrap`, `index` e `batch`. Na aplicação real,
o script registra primeiro o batch e injeta sua **revisão exata** no web antes de
registrá-lo. O `web.json` e o recibo são atualizados com o que foi registrado.
No render offline o runner do web fica desabilitado até essa revisão existir.

## Assim que chegarem as credenciais

Configurar um profile temporário pelo mecanismo fornecido pelo workshop; não
colar credenciais em comandos, documentos, issues ou arquivos versionados.

```bash
scripts/preflight_aws.sh --config deployment/aws.local.json --profile workshop
```

O relatório diferencia `PASS`, `DENIED`, `FAIL` e `NOT_PROVEN`. Ele verifica conta,
trust principals das roles, rotas públicas, VPC dos SGs/RDS, RDS privado disponível,
cluster, metadados de segredos, cotas e configuração Cognito quando preenchida.
`PASS` de leitura não comprova criação de recursos, PassRole, condições de trust,
permission boundaries, SCPs, conectividade da task ou privilégios SQL.

O relatório de cotas lista valores configurados, não o consumo disponível nem a
garantia de capacidade. Confirmar vCPU Fargate, ENIs/IPs, ALBs, RDS e limites dos
modelos escolhidos. Conferir também expiração das credenciais do workshop.
O Express usa canário por padrão: reservar capacidade/IPs para a revisão antiga
e a nova coexistirem, mesmo com contagem desejada igual a uma task.

Para pequenas invocações reais e potencialmente cobradas de embeddings/chat:

```bash
scripts/preflight_aws.sh --config deployment/aws.local.json --profile workshop --invoke-models
```

Titan exige retorno de 512 dimensões. O chat usa o modelo/profile configurado com
uma resposta curta. Um chat model vazio continua `NOT_PROVEN`. SCP que bloqueie
destinos de um inference profile pode impedir a chamada mesmo com acesso à origem.

## Pré-requisitos que o script não inventa

- Região e conta aprovadas pelo workshop.
- Roles existentes de execução, aplicação web, batch e infraestrutura Express.
  As três primeiras precisam de trust para `ecs-tasks.amazonaws.com`; infraestrutura,
  para `ecs.amazonaws.com`. Confirmar condições e permission boundaries.
- VPC e subnets públicas com rota IGW; tasks com IP público para saída sem NAT.
  RDS deve estar em subnets privadas da mesma VPC. Conferir DNS, NACLs e egress.
- SG web recebe 8000 somente do SG do balanceador Express; Agent 8001 sem ingresso
  externo. SG RDS recebe 5432 dos SGs web/batch. A API não publica diretamente na internet.
- RDS PostgreSQL disponível e suportando `vector`, banco e `migration_user` preparados.
- Segredos e, no segundo estágio, Cognito User Pool/app client/grupos reais.

Não presumir que uma role genérica do workshop sirva a todos os serviços. Se IAM,
RDS ou Express forem negados, registrar o código e recurso no diagnóstico e pedir
ao responsável da conta uma alternativa autorizada. Não tentar remover boundaries.

## Bootstrap limitado e repetível

```bash
scripts/bootstrap_aws.sh --config deployment/aws.local.json --profile workshop --apply
```

Cria/reutiliza repositórios ECR com tags imutáveis, log group com retenção de sete
dias, bucket privado/versionado e cluster ECS. Não cria IAM/VPC/RDS/Cognito.
Recursos que serão modificados precisam da tag `vx-project=<name>`; um bucket ou
log group existente sem essa propriedade é recusado. Erros de acesso não são
tratados como recurso ausente. A criptografia KMS existente do bucket é preservada.

As tasks usam `awslogs`; a execution role precisa de ECR, CloudWatch e dos ARNs
exatos de Secrets Manager, mais `kms:Decrypt` quando aplicável. A task role web
precisa de armazenamento para manifestos e de `ecs:RunTask` somente na família de
batch autorizada, `iam:PassRole` somente nas roles de execução/batch e condição
`iam:PassedToService=ecs-tasks.amazonaws.com`. Registrar novas revisões e atualizar
o recurso autorizado na política faz parte de publicar uma versão.

O operador precisa de register/describe/run/stop de tasks, create/update/describe
Express, `ListServiceDeployments`, `DescribeServiceRevisions` e PassRole das roles
referenciadas. A espera valida o estado `SUCCESSFUL` da revisão exata no canário;
não depende do `rolloutState`, que é próprio de rolling update. O lock usa acesso do operador a
`locks/<name>/deploy.json`; não conceder esse prefixo à aplicação.

## Banco e segredos

O bootstrap SQL de [`AGENTS.md`](../AGENTS.md#database-on-aws) continua exigindo
execução pelo master do RDS, de uma máquina/task com acesso privado. Verificar
`pg_available_extensions`, `rds.allowed_extensions`, ownership do banco e grants
reais. `rds_superuser` não equivale ao superuser de PostgreSQL local.

Criar segredos `SecretString` para as URLs completas de `api_user`, `mcp_reader`,
`batch_user` e `migration_user`. Todas usam `postgresql+psycopg`, o endpoint DNS real
do mesmo RDS e o mesmo banco operacional. Exigir estes parâmetros:

```text
sslmode=verify-full&sslrootcert=/app/certs/rds-global-bundle.pem
```

As imagens incluem o CA bundle oficial do RDS com SHA-256 fixado no Dockerfile.
Se a AWS renovar o bundle, conferir a nova cadeia e atualizar o checksum em PR;
não remover a verificação. O download usa o truststore oficial, sem certificados privados.

Construir URLs com `sqlalchemy.engine.URL.create(...).render_as_string(hide_password=False)`
em um processo seguro que grave diretamente no Secrets Manager. Não concatenar
senhas em uma URL: `@`, `/`, `%`, `?`, `#` e aspas precisam do encoding correto.
Não imprimir o resultado nem passá-lo em argumentos visíveis do shell.

`database_passwords` referencia um segredo JSON com `API_DB_PASSWORD`,
`BATCH_DB_PASSWORD` e `MCP_DB_PASSWORD`. Os valores devem coincidir com as URLs.
`internal_token` referencia texto aleatório com pelo menos 32 bytes.
`session_encryption` referencia uma chave Fernet persistente; opcionalmente,
`cognito_client_secret` referencia o segredo do app client confidencial.

O deploy confere essa consistência em memória e não imprime valores. A task de
migração recebe a URL de migração e os três passwords. Web/Agent não recebem
credenciais de migração. Depois da rotação, reiniciar consumidores e conferir
conexões: variáveis injetadas não se atualizam sozinhas.

## Construir imagens e usar digests

Autenticar Docker no ECR com `aws ecr get-login-password` canalizado para
`docker login --password-stdin`. Usar profile/região corretos e não imprimir a senha.
Construir cada target com `docker buildx build --platform linux/amd64 --target api`
(ou `agent`/`batch`), tag exclusiva de commit e `--push`. Para `architecture=ARM64`,
usar `linux/arm64`. Não publicar imagens ARM de um laptop como task X86_64.

Consultar o digest no ECR e substituir os três campos `images` por
`<registry>/<repository>@sha256:<digest>`. Tags `latest` são recusadas pelo validador.
O deploy exige que os digests existam no ECR antes de executar qualquer migração.

## Primeiro HTTPS e conexão Cognito

1. Manter `auth_backend=disabled` e `public_origin` vazio no primeiro estágio.
   Sessões locais continuam desligadas. Essa publicação serve para obter HTTPS,
   não permite entrar no produto e não conclui a homologação.
2. Executar uma release exclusiva:

   ```bash
   scripts/deploy_ecs.sh --config deployment/aws.local.json --profile workshop --release <commit>-https --apply
   ```

3. Ler `deployment/generated/receipt.json`. O script executa migração, senhas,
   bootstrap e índice, verifica exit codes e espera a **nova** revisão de web,
   sem aceitar a revisão antiga saudável como evidência. Guarda o ARN anterior.
4. Preencher `public_origin` com o HTTPS observado, sem barra final. Registrar
   `<public_origin>/auth/callback/` no app client. Ativar apenas code flow e scopes
   `openid email profile`. Criar grupos e contas conforme [`autenticacao.md`](../docs/autenticacao.md).
5. Preencher pool/client/domain e chave Fernet, mudar `auth_backend=cognito`,
   repetir preflight e publicar `<commit>-auth`. O validador confere HTTPS, região,
   chave, callback, scopes e correspondência de eventual client secret.
6. Executar login no navegador, conferir cookie `__Host-vx_session`, logout,
   três papéis, CSRF, decisão técnica/fiscal e um turno MCP. O smoke autenticado
   aceita o cookie jar de uma sessão Solicitante real. Registrar evidências na #91.

O runner web recebe a revisão fixa do batch. Overrides levam somente job/manifesto,
nunca token Cognito ou senha SQL. O mesmo job/tentativa gera o mesmo clientToken;
resume persiste outra tentativa e pode iniciar outra task. A expiração por heartbeat
existente continua sendo a barreira para tasks que não começam ou deixam de progredir.

Embeddings ficam desligados por padrão. `embedding_repository=bedrock_titan_v1`
é uma decisão explícita: a indexação da base inteira pode fazer milhares de chamadas.
Não usar `simulated_v1`/Ollama no deploy. A configuração recusa esses nomes.
API, Agent e CLI também recusam iniciar com `simulated_v1` fora de `APP_ENV=local`
ou quando há marcadores de runtime AWS, mesmo que o ambiente se declare local.
O planejador de chat atual continua determinístico: definir `BEDROCK_CHAT_MODEL_ID`
não implementa um planejador LLM. A chamada curta do preflight só comprova acesso
ao modelo. O repositório de embeddings atual fixa Titan V2; outros IDs exigem outra
implementação e reindexação compatível.

## Falhas, exclusão mútua e rollback

Um lock S3 condicional impede dois deploys com o mesmo `name` ao mesmo tempo.
O bucket precisa estar versionado. Sucesso remove apenas a versão do próprio lock.
Em erro, timeout ou interrupção, o lock é preservado: uma task pode ter iniciado
mesmo que a resposta tenha se perdido. Conferir tasks ECS e interromper/aguardar
as pendentes antes de remover **a versão correta** do lock. Nunca limpar locks
automaticamente só porque o processo local terminou.

RunTask usa tokens por release/etapa, sujeitos ao prazo de idempotência do ECS.
Usar nova release ao mudar imagens/configuração; não reaproveitar identificadores
para argumentos diferentes. Migração/bootstrap devem continuar idempotentes.

O recibo mantém a definição anterior do web. Rollback de imagem não reverte schema:
conferir compatibilidade antes de atualizar o serviço para o ARN anterior. Não há
downgrade automático nem exclusão automática de RDS/bucket.

## O que continua dependendo da conta

- IAM/PassRole e operação real do Express com sidecar, SG e endereço público.
- Instalação de vector, grants e logins SQL por TLS no RDS.
- Quotas/model access e invocações reais do Bedrock.
- Login Cognito e cookies aceitos pelo navegador em HTTPS (#91).
- Plano B EC2/Caddy preparado em [`docs/ec2.md`](../docs/ec2.md); validar na EC2 (#29).
- Reset completo de propostas/pedidos/sessões da demo (#34).

Referências: [Express com task definition](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html),
[role de infraestrutura](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html),
[RDS truststore](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem),
[Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html).
