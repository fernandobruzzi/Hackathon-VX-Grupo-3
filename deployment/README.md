# Preparar e publicar na conta do workshop

Estas ferramentas foram usadas na conta do workshop (#6): pré-requisitos por
CloudFormation, RDS preparado, migração, carga, índice e serviço Express. O login
real continua na #91.

## Sequência usada na conta do workshop

A conta do workshop entrega só a VPC padrão. A role `WSParticipantRole` pode criar
IAM, RDS e ECS em `us-east-1`; outras regiões são negadas.

1. Credenciais: `aws login --profile workshop` reaproveita a sessão do console. As
   credenciais duram cerca de 15 minutos e o CLI as renova sozinho. O boto3 só faz
   isso com `botocore[crt]`, então rode os scripts Python com
   `uv run --locked --with 'botocore[crt]' --package vx-materials-back python scripts/<script>.py ... --profile workshop`.
   Variáveis exportadas por `aws configure export-credentials` expiram no meio do
   deploy e deixam o lock para trás.
2. Pré-requisitos, sem segredos no template: roles de execução, web, batch e
   infraestrutura Express; SG das tasks sem ingresso; SG do RDS liberando 5432 só
   para as tasks; RDS privado com senha do master gerenciada pelo próprio RDS.

   ```bash
   aws cloudformation create-stack --stack-name vx-grupo3-infra \
     --template-body file://deployment/infra.yaml --capabilities CAPABILITY_NAMED_IAM \
     --parameters ParameterKey=VpcId,ParameterValue=<vpc> 'ParameterKey=SubnetIds,ParameterValue="<s1>,<s2>,<s3>,<s4>"'
   ```

3. Preencher `aws.local.json` com as saídas da stack (roles, SG das tasks,
   instância) e criar ECR, log group, bucket e cluster com
   `bootstrap_aws.sh --apply`.
4. Segredos: `aws_database.py secrets --endpoint <DatabaseEndpoint> --apply`
   gera senhas hexadecimais, monta as URLs com `URL.create` e imprime só os ARNs.
   Copiar os ARNs para `secrets`. Repetir o comando não sobrescreve nada.
5. Imagens: em Mac Apple Silicon, use `architecture=ARM64` e
   `docker buildx build --platform linux/arm64`, que não precisa de emulação.
   Copiar os digests para `images`.
6. RDS pelo master: `aws_database.py init --master-secret-arn <DatabaseMasterSecretArn> --apply`
   roda o SQL de `AGENTS.md` dentro da VPC e confere o dono do banco e o `vector`.
7. Preflight e deploy, como nas seções abaixo.

O Express anexa às tasks um SG próprio, que só libera a porta 8000 a partir do
balanceador. O Agent (8001) fica sem ingresso, e o SG das tasks não precisa de
regra. A política gerenciada da role de infraestrutura não cobre
`ecs:DescribeServices`, `ecs:UpdateService` nem `cloudwatch:DescribeAlarms`. Sem
essas permissões, o CloudTrail mostra AccessDenied e o deployment fica parado com
zero tasks; o template as concede só para os serviços do cluster. Enquanto um
deployment Express está em andamento, um novo update recebe `ConflictException`:
espere o deployment terminar antes de repetir.

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
4. Atualizar a stack com `PublicOrigin=<origem HTTPS observada>`, sem barra final.
   O template cria o User Pool só com cadastro por administrador, o domínio do
   Hosted UI, os grupos `ROLE_*` e um app client público. O client usa code flow
   com `openid email profile`, callback `<origem>/auth/callback/` e logout
   `<origem>/login/`. As saídas `Cognito*` vão para `aws.local.json`.
5. Contas da demo: `aws_demo_accounts.py --apply` cria Ana Souza (Solicitante),
   Bruno Oliveira (Governança PDM) e Carla Pereira (Fiscal) em `example.com`, sem
   convite por e-mail, cada uma só no próprio grupo. As senhas ficam no segredo
   `<name>/demo-accounts` e nunca são impressas; leia-as com
   `aws secretsmanager get-secret-value --secret-id <name>/demo-accounts`.
6. Mudar `auth_backend=cognito`, repetir preflight e publicar `<commit>-auth`. O
   validador confere HTTPS, região, chave, callback, scopes e correspondência de
   eventual client secret. A chave Fernet já vem do segredo `session-encryption`.
7. Executar login no navegador, conferir cookie `__Host-vx_session`, logout,
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
O chat usa Claude Sonnet 5 quando `BEDROCK_CHAT_MODEL_ID` estiver preenchido.
O exemplo AWS configura `bedrock_chat_model=us.anthropic.claude-sonnet-5` em
`us-east-1`; o render existente transmite isso ao Agent. O perfil encaminha a
inferência entre regiões dos EUA. Para São Paulo, avaliar explicitamente o perfil
global e seus destinos antes de alterar a configuração. O ID simples não funciona
como inferência regional em `us-east-1`. Conferir a
[ficha oficial do Sonnet 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html).

Localmente, preencher `.env` com `AWS_REGION=us-east-1` e
`BEDROCK_CHAT_MODEL_ID=us.anthropic.claude-sonnet-5` e recriar o Agent:
`docker compose up -d --build agent`. Fornecer credenciais AWS válidas ao container
pelos mecanismos usuais do SDK; um perfil no host não é montado automaticamente.
No ECS/EC2 usar task role/instance profile, sem chave no frontend. A role do Agent
precisa de `bedrock:InvokeModel` no perfil e nos modelos de destino; SCPs precisam
permitir os destinos do perfil. A conta também precisa satisfazer os requisitos
de acesso ao modelo/Anthropic e ter quota. Não é necessário `InvokeModelWithResponseStream`
para este fluxo síncrono. A chamada do preflight comprova acesso, não a qualidade da entrevista.
O template `infra.yaml` concede esse acesso na role web compartilhada pelo Agent,
restrito ao perfil US do Sonnet 5 e aos destinos `us-east-1`, `us-east-2` e `us-west-2`;
os destinos só podem ser invocados por esse perfil. A alteração precisa ser aplicada
à stack existente antes de ativar o chat. Não acrescenta acesso ao Sonnet 5 na role do batch.

O system prompt `material_registration_system_v1` fica em
`mcp/vx_materials_mcp/chatbot/prompts.py`. Por turno, o Agent interpreta o pedido
com saída estruturada, exige trechos literais do usuário para atributos propostos,
executa o ciclo MCP existente e pede ao modelo uma resposta baseada na ficha.
São no máximo duas chamadas Converse e cinco tools. Classe/nome/atributos são
validados; prontidão, duplicidade e aprovação continuam no domínio/API.
A API envia a classe e o nome da última ficha persistida com os atributos aceitos.
O Agent reaproveita esses atributos apenas para o mesmo item na mesma classe;
outra identidade começa com os dados da mensagem atual. Remoções explícitas são
persistidas como `null`, sem reextrair valores retirados das mensagens antigas.
A consulta de duplicidade também usa apenas o nome e os atributos aceitos, para
que a busca MCP não extraia novamente fatos retirados ou pertencentes a outro item.
Trechos explícitos de revisão de peça continuam na consulta, preservando a exigência
de revisão pelo motor de identidade mesmo quando a referência aceita não contém o sufixo.
Se o modelo deixar a classe inconclusiva para uma ficha já conhecida, o turno
retorna erro sem substituir o estado aceito, as mensagens ou a versão da conversa.
Em botões de escolha/descarte, o modelo reconstrói a descrição pelo histórico;
a mensagem do botão fica fora da interpretação e a ação estruturada permanece
autoritativa no ciclo determinístico.
Falhas AWS e respostas inválidas retornam 503 sanitizado, sem fallback silencioso.
O SDK usa conexão de 2 s, leitura de 8 s e uma tentativa por chamada; o prazo global
do Agent continua 20 s. Medir latência real de Sonnet 5 na #107 antes da demo.

Sem `BEDROCK_CHAT_MODEL_ID`, o fluxo local permanece por regras e não faz chamadas
de modelo. Testes usam transporte simulado; acesso, custo e qualidade precisam ser
validados com a conta real. O repositório de embeddings continua fixando Titan V2;
outros IDs exigem outra implementação e reindexação compatível.

## Domínio próprio

O Express não aceita domínio próprio e reverte mudanças no balanceador que
gerencia. Para servir em `vx.cerne.pro`, a stack recebe `CustomDomain` e
`ExpressEndpoint` (host do Express, sem `https://`). Ela cria um certificado ACM
validado por DNS e um CloudFront sem cache. O CloudFront repassa cookies, query e
`Origin`, mas não o `Host`, porque o balanceador do Express roteia pelo próprio
host. Por isso a API devolve redirects do front como caminhos relativos.

1. Se o domínio tiver registros CAA, incluir `0 issue "amazon.com"` no apex. Sem
   isso o ACM não emite. No Vercel DNS, os CAA padrão permitem só Let's Encrypt,
   Sectigo e Google.
2. Atualizar a stack com `CustomDomain`, `ExpressEndpoint` e
   `PublicOrigin=https://<domínio>`, que também troca o callback do Cognito. O
   update espera a validação: ler o registro em
   `aws acm describe-certificate` e criar o CNAME `_…` no DNS.
3. Criar o CNAME do subdomínio para a saída `CustomDomainTarget`.
4. Mudar `public_origin` em `aws.local.json` e publicar uma release nova. O deploy
   exige liveness tanto no Express quanto no domínio próprio. Entre o update da
   stack e o deploy, o login pelo endereço antigo falha no Hosted UI, porque o
   callback já mudou.

## Deploy automático a cada promoção (#277)

O workflow `Deploy` publica cada push em `main`. Ele assume por OIDC a role
`<name>-github-deploy`, que só aceita tokens de `main` deste repositório e não
usa chaves de longa duração. Em seguida, constrói as três imagens X86_64 no
runner e roda o mesmo `aws_deploy.py` com release
`<sha>-<run_id>-<tentativa>`. O resumo da execução mostra release, origem e task
definition.

Preparação, uma vez por conta:

1. Atualizar a stack com `GitHubRepository` no mesmo formato que o GitHub
   emite no campo `sub` do token OIDC. Este repositório usa o formato imutável
   `<owner>@<owner-id>/<repo>@<repo-id>`. Rode na raiz do clone para obter o valor:

   ```bash
   gh api 'repos/{owner}/{repo}' --jq '"\(.owner.login)@\(.owner.id)/\(.name)@\(.id)"'
   ```

   Se a stack já foi criada com `<owner>/<repo>`, atualize o parâmetro antes da
   primeira promoção com o workflow. O formato sem IDs continua disponível para
   repositórios que ainda o usam. [Referência de OIDC do GitHub](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims).

   A stack cria o provedor OIDC e a role. A role recebe ECR só nos repositórios
   `<name>-*`, acesso ao cluster e às famílias de tasks do projeto,
   PassRole só nas quatro roles, acesso ao prefixo `locks/` do bucket e leitura
   dos segredos que o deploy confere.
2. Criar as variáveis do repositório no GitHub, sem segredos:
   - `AWS_DEPLOY_ROLE_ARN`: saída `GitHubDeployRoleArn`;
   - `AWS_REGION`;
   - `AWS_DEPLOY_NAME`: o `name` da configuração;
   - `AWS_DEPLOY_CONFIG`: o conteúdo de `aws.local.json`. O workflow troca as
     imagens pelos digests construídos e fixa `X86_64`.

   Sem `AWS_DEPLOY_ROLE_ARN`, o job é ignorado.
3. Depois da preparação, um disparo manual em `main` (Actions → Deploy → Run
   workflow) publica o commit atual.

Falha no meio mantém o lock, como no deploy manual. Confira as tasks ECS antes de
remover a versão do lock e use "Re-run all jobs": a nova tentativa gera release,
tags e tokens novos. Deploys manuais continuam possíveis. Para não competir com
o automático, use a mesma configuração e confira se não há execução em andamento.

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

## Homologação no workshop

Comprovado na conta do workshop (#6): roles e PassRole, Express com o Agent como
sidecar, HTTPS público servindo o front pela API e Agent sem ingresso. Também
comprovados: RDS privado, `vector` 0.8.2, migração e senhas, e logins TLS
`verify-full` de `api_user`, `batch_user` e `mcp_reader`. Na #91: login Cognito
real com cookie `__Host-vx_session` Secure, HttpOnly, SameSite=Lax e host-only,
`/auth/me` sem tokens, turno de chat pelo Agent, logout encerrando também a sessão
do Hosted UI e domínio próprio pelo CloudFront. Uma sessão real de Solicitante
com CSRF válido recebeu `403 FORBIDDEN` do controle de papéis ao tentar uma
decisão técnica. O teste usou um UUID inexistente para evitar decidir uma
proposta da fila.

Com uma sessão real de Governança, as páginas
`/saneamento/revisao/?id=<UUID>` e `/enriquecimento/revisao/?id=<UUID>`
renderizaram os materiais das propostas persistidas. Um job de saneamento
disparado pela API executou no Fargate e terminou com 13.144 propostas, com
correções automáticas desativadas. Uma task avulsa publicou duas propostas de
enriquecimento para revisão. Os registros estão nas issues
[#6](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/6) e
[#91](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/91).

Validações pendentes:

- Invocações reais do Bedrock.
- Plano B EC2/Caddy preparado em [`docs/ec2.md`](../docs/ec2.md); validar na EC2 (#29).
- Reset completo de propostas/pedidos/sessões da demo (#34).

Referências: [Express com task definition](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-getting-started.html),
[role de infraestrutura](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html),
[RDS truststore](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem),
[Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html).
