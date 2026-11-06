# Plano B: EC2, Compose e HTTPS

Preparação local da #29. A execução em EC2, permissões e login real continuam
dependendo da conta do workshop; este documento não registra uma homologação AWS.
Utiliza a configuração e os segredos de [`deployment/README.md`](../deployment/README.md).

## Preparar sem conta AWS

```bash
scripts/deploy_ec2.sh --config deployment/aws.example.json --host 203.0.113.10.nip.io --render-dir deployment/generated/ec2
docker compose -f deployment/generated/ec2/compose.json config --no-env-resolution --quiet
```

O IP acima é apenas exemplo reservado para documentação. O render escreve
`compose.json` e `Caddyfile`, não consulta AWS nem cria arquivos com segredos.
Compose 2.30+ é necessário para `env_file` no formato raw. O Caddy oficial é fixado
por digest multi-arquitetura; atualizar a versão em uma alteração revisada.
O template offline permite a ausência dos env files para validar a estrutura.
`--apply` reescreve o Compose exigindo todos os arquivos de segredos antes de subir.
Não iniciar o template offline como se ele fosse uma implantação pronta.

## Pré-requisitos da EC2

- Linux com arquitetura igual às imagens, Docker, Compose 2.30+, Git, Python e uv.
- Instance profile com leitura dos segredos necessários, ECR, S3 e Bedrock conforme
  o uso. Não copiar credenciais pessoais estáticas para os containers.
- IMDSv2 com response hop limit suficiente para Docker (normalmente 2). Conferir
  acesso do SDK dentro dos containers; credenciais disponíveis no host não provam isso.
- IP público estável, idealmente Elastic IP se a conta permitir. Não parar a
  instância entre preparar o callback e a demo sem conservar o endereço.
- SG libera 80/443 para entrada. API/Agent não publicam portas. RDS privado libera
  5432 do SG desta EC2. Conferir VPC, rotas, DNS, egress e NACLs.
- Acesso administrativo por SSM ou canal autorizado do workshop; o script não cria
  instância, instance profile ou regras de rede por suposição.
- ECR, RDS, usuários SQL, segredos e bucket versionado preparados conforme o Plano A.

O script exige credenciais obtidas por instance profile na execução real. Os ARNs
de task roles do formato de configuração ECS não são utilizados pelo Compose:
o fallback não depende de conseguir criar a role de infraestrutura Express.

## HTTPS sem criar uma entrada DNS própria

Um hostname como `<ip-publico>.nip.io` pode resolver para o IP da EC2 sem alterar
uma zona DNS própria. Também é possível usar um domínio já apontado ao servidor.
Conferir resolução pública e permitir 80/443 antes de iniciar o Caddy.

Não há garantia de emissão instantânea: ACME, rate limits, DNS externo e filtros de
DNS/rebinding podem impedir a operação. O Caddy só usa certificado publicamente
confiável depois da validação ACME; não usar `tls internal` para a demonstração.
Um IP puro é recusado pelo script para evitar apresentar TLS local como HTTPS público.

Caddy faz reverse proxy para `api:8000` e persiste certificados/configuração em
volumes do projeto. Os logs de containers têm rotação. Não apagar os volumes de
Caddy entre atualizações, para evitar emissões repetidas e limites do provedor.
O acesso público da API continua na mesma origem do front.

## Publicar no host EC2

Copiar o clone/configuração não secreta para a EC2 pelo canal autorizado. Usar os
mesmos digests imutáveis de API/Agent/batch. Na EC2:

```bash
scripts/deploy_ec2.sh --config deployment/aws.local.json --host <hostname-publico> --release <commit>-ec2 --apply
```

O comando verifica a conta, instance profile, arquitetura e consistência dos
segredos. Usa o lock S3 do mesmo projeto, para não executar migrações simultâneas
com o ECS. Busca os segredos em memória e escreve um arquivo por serviço, em
diretório 0700 e arquivos 0600. Senhas são passadas ao login ECR por stdin.

Executa pull, migração/senhas, bootstrap, índice, API/Agent/Caddy e espera liveness
HTTPS com verificação normal do certificado. Não existe banco PostgreSQL local
nesse Compose. API, Agent e operações usam root filesystem somente leitura e /tmp
temporário. Cada serviço recebe somente seu conjunto de segredos.

Arquivos `.env` usam `format: raw`: `$`, aspas e outros caracteres não passam por
expansão de shell/Compose. Valores multilinha são recusados. Não executar `compose
config` sem `--no-env-resolution` depois da aplicação, pois a saída poderia mostrar
valores resolvidos. Não versionar nem compartilhar esses arquivos. Manter apenas
as releases privadas necessárias para operação/rollback e limpar cópias antigas
após verificar a rotação.

Como o instance profile é da máquina, todos os containers compartilham a autoridade
IAM do host; credenciais SQL separadas não representam isolamento IAM entre containers.

## Login e cookie

Se o hostname ainda não existir na configuração, o primeiro estágio pode usar
`auth_backend=disabled` para obter o certificado, sem habilitar sessões locais.
Em seguida, preencher `public_origin=https://<hostname-publico>`, configurar Cognito
e mudar para `auth_backend=cognito`. O script recusa origem diferente do hostname.

Registrar exatamente `https://<hostname-publico>/auth/callback/` no app client,
preservando o callback do ECS se ambos forem usados. A mudança de origem exige
novo login; cookies host-only de um endereço não devem ser copiados para outro.

Conferir no navegador `__Host-vx_session` Secure, HttpOnly, SameSite=Lax, Path=/,
sem Domain, depois validar `/auth/me`, CSRF, os três papéis, chat/MCP e logout.
Executar o smoke autenticado a partir de uma máquina externa. O script não declara
login homologado só porque liveness HTTPS passou.

## Batch sob demanda e limitação da tela

Para preparar propostas administrativamente após subir o ambiente:

```bash
scripts/deploy_ec2.sh --config deployment/aws.local.json --host <hostname-publico> --release <commit>-ec2 --apply --run-batch
```

Isso executa `vx-back sanitize` com a credencial `batch_user`, mantendo propostas
e aprovações pela API. O modo administrativo existente não cria o job de usuário
com progresso da tela. `BATCH_RUNNER` fica vazio no fallback: a ação de iniciar
job pela API retorna indisponibilidade, sem fingir execução.

O runner `local_process` é só de desenvolvimento e não é habilitado em produção.
Não montar o Docker socket na API para contornar essa restrição. Caso a demo exija
o botão de batch também no Plano B, entregar antes um mecanismo de execução de
produção ou usar o runner Fargate quando RunTask estiver disponível, com configuração
e permissões conferidas. Essa limitação precisa constar no roteiro do fallback.

## Falhas e atualização

Os volumes Caddy persistem entre releases. Alterar digests e publicar novamente
recria os serviços para aplicar também a rotação de segredos. O recibo não contém
credenciais. Para rollback, usar configuração/digests anteriores compatíveis com
o schema; não executar downgrade automático do banco.

Em falha, o lock é preservado. Antes de liberar sua versão, conferir se algum
container de migração/batch ainda está executando. Não usar `down -v` como rotina
de atualização, pois isso descarta os certificados persistidos.

Referências: [HTTPS automático Caddy](https://caddyserver.com/docs/automatic-https),
[Cognito e callback](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html),
[IMDS em containers EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html).
