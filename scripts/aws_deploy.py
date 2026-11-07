"""Bootstrap mínimo e deploy ECS usando rede, RDS, roles e segredos já autorizados."""

import argparse
import base64
import hashlib
import json
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen

from aws_support import ConfigurationError, canonical_task, load_config, render, task_definitions


def client(session, service):
    from botocore.config import Config

    return session.client(
        service, config=Config(connect_timeout=5, read_timeout=30, retries={"mode": "standard", "max_attempts": 4})
    )


def aws_session(config, profile):
    import boto3

    session = boto3.Session(profile_name=profile, region_name=config["region"])
    if client(session, "sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ConfigurationError("Conta AWS diferente da configurada")
    return session


def bootstrap(config, session):
    """Não cria IAM, VPC ou RDS: a política real do workshop determina esses recursos."""
    from botocore.exceptions import ClientError

    tags = [{"Key": "vx-project", "Value": config["name"]}]
    ecr = client(session, "ecr")
    for target in ("api", "agent", "batch"):
        repository = config["images"][target].split("/", 1)[1].split("@", 1)[0]
        try:
            current = ecr.describe_repositories(repositoryNames=[repository])["repositories"][0]
            if current["imageTagMutability"] != "IMMUTABLE":
                raise ConfigurationError("Repositório existente aceita tags mutáveis; ajuste explicitamente antes")
        except ClientError as error:
            if error.response["Error"]["Code"] != "RepositoryNotFoundException":
                raise
            ecr.create_repository(
                repositoryName=repository,
                imageTagMutability="IMMUTABLE",
                imageScanningConfiguration={"scanOnPush": True},
                tags=[{"Key": "vx-project", "Value": config["name"]}],
            )
    logs = client(session, "logs")
    try:
        logs.create_log_group(logGroupName=config["log_group"], tags={"vx-project": config["name"]})
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
        existing = logs.list_tags_log_group(logGroupName=config["log_group"])["tags"]
        if existing.get("vx-project") != config["name"]:
            raise ConfigurationError(
                "Log group existente sem tag de propriedade; nenhuma retenção foi alterada"
            ) from error
    logs.put_retention_policy(logGroupName=config["log_group"], retentionInDays=7)
    s3 = client(session, "s3")
    bucket = config["bucket"]
    created_bucket = False
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=config["account_id"])
        existing = s3.get_bucket_tagging(Bucket=bucket)["TagSet"]
        if {t["Key"]: t["Value"] for t in existing}.get("vx-project") != config["name"]:
            raise ConfigurationError("Bucket existente sem tag de propriedade")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
            raise
        arguments = {"Bucket": bucket}
        if config["region"] != "us-east-1":
            arguments["CreateBucketConfiguration"] = {"LocationConstraint": config["region"]}
        s3.create_bucket(**arguments)
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": tags})
        created_bucket = True
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    if created_bucket:
        s3.put_bucket_encryption(
            Bucket=bucket,
            ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            },
        )
    ecs = client(session, "ecs")
    result = ecs.describe_clusters(clusters=[config["cluster"]])
    if not result["clusters"]:
        if ":" in config["cluster"]:
            raise ConfigurationError("Cluster ARN inexistente; informe nome para criar")
        ecs.create_cluster(clusterName=config["cluster"], tags=[{"key": "vx-project", "value": config["name"]}])
    elif result["clusters"][0]["status"] != "ACTIVE":
        raise ConfigurationError("Cluster existente inativo")
    print("PASS ECR, logs, bucket privado/versionado e cluster; IAM/rede/RDS/Cognito continuam pré-requisitos")


@contextmanager
def deployment_lock(config, session, release):
    s3 = client(session, "s3")
    key = f"locks/{config['name']}/deploy.json"
    result = s3.put_object(
        Bucket=config["bucket"],
        Key=key,
        IfNoneMatch="*",
        ContentType="application/json",
        Body=json.dumps({"release": release, "owner": str(uuid.uuid4()), "created_at": time.time()}).encode(),
        ExpectedBucketOwner=config["account_id"],
    )
    version = result.get("VersionId")
    if not version:
        # O bootstrap habilita versionamento. Não apagar uma chave sem identificar a própria versão.
        raise ConfigurationError("Bucket sem versionamento; lock exige intervenção explícita")
    completed = False
    try:
        yield
        completed = True
    finally:
        # Um timeout pode deixar uma task remota executando. Nessa situação, só remover
        # o lock por versão depois de conferir ECS e encerrar as tasks pendentes.
        if completed:
            s3.delete_object(
                Bucket=config["bucket"], Key=key, VersionId=version, ExpectedBucketOwner=config["account_id"]
            )


def register(ecs, definition):
    from botocore.exceptions import ClientError

    try:
        existing = ecs.describe_task_definition(taskDefinition=definition["family"])["taskDefinition"]
        if existing["status"] == "ACTIVE" and canonical_task(existing, definition):
            return existing["taskDefinitionArn"]
    except ClientError as error:
        if error.response["Error"][
            "Code"
        ] != "ClientException" or "Unable to describe task definition" not in error.response["Error"].get(
            "Message", ""
        ):
            raise
    return ecs.register_task_definition(**definition)["taskDefinition"]["taskDefinitionArn"]


def one_off(ecs, config, definition, release, step):
    token = hashlib.sha256(f"{config['name']}:{release}:{step}".encode()).hexdigest()
    result = ecs.run_task(
        cluster=config["cluster"],
        taskDefinition=definition,
        launchType="FARGATE",
        platformVersion="1.4.0",
        count=1,
        clientToken=token,
        startedBy=f"deploy-{token[:24]}",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": config["subnets"],
                "securityGroups": config["security_groups"],
                "assignPublicIp": "ENABLED",
            }
        },
    )
    if result.get("failures") or len(result.get("tasks", [])) != 1:
        raise ConfigurationError(f"RunTask falhou em {step}; confira ECS e CloudWatch")
    arn = result["tasks"][0]["taskArn"]
    print(f"RUN {step}: {arn}", flush=True)
    ecs.get_waiter("tasks_stopped").wait(
        cluster=config["cluster"], tasks=[arn], WaiterConfig={"Delay": 10, "MaxAttempts": 120}
    )
    tasks = ecs.describe_tasks(cluster=config["cluster"], tasks=[arn])
    if tasks.get("failures") or not tasks["tasks"]:
        raise ConfigurationError(f"Task {step} indisponível após espera")
    containers = tasks["tasks"][0].get("containers", [])
    if not containers or any(c.get("exitCode") != 0 for c in containers):
        raise ConfigurationError(f"Task {step} terminou sem sucesso; confira logs (segredos não são impressos)")
    return arn


def validate_secrets(config, session):
    """Confere TLS, usuários e consistência das senhas sem registrar os valores."""
    from sqlalchemy.engine import make_url

    secrets = client(session, "secretsmanager")
    values = {
        key: secrets.get_secret_value(SecretId=arn)["SecretString"]
        for key, arn in config["secrets"].items()
        if arn and (key not in {"session_encryption", "cognito_client_secret"} or config["auth_backend"] == "cognito")
    }
    if len(values["internal_token"].encode()) < 32:
        raise ConfigurationError("Segredo interno precisa de pelo menos 32 bytes")
    if (
        config["auth_backend"] == "cognito"
        and len(base64.b64decode(values["session_encryption"], altchars=b"-_", validate=True)) != 32
    ):
        raise ConfigurationError("Chave Fernet de sessão inválida")
    if config["auth_backend"] == "cognito":
        app = client(session, "cognito-idp").describe_user_pool_client(
            UserPoolId=config["cognito_user_pool_id"], ClientId=config["cognito_app_client_id"]
        )["UserPoolClient"]
        if (
            not app.get("AllowedOAuthFlowsUserPoolClient")
            or app.get("AllowedOAuthFlows") != ["code"]
            or "openid" not in app.get("AllowedOAuthScopes", [])
            or config["public_origin"] + "/auth/callback/" not in app.get("CallbackURLs", [])
            or (app.get("ClientSecret") or None) != (values.get("cognito_client_secret") or None)
        ):
            raise ConfigurationError("App client Cognito diverge do fluxo, callback, scopes ou segredo configurados")
    passwords = json.loads(values["database_passwords"])
    rds = client(session, "rds").describe_db_instances(DBInstanceIdentifier=config["rds_instance"])["DBInstances"][0]
    if rds["PubliclyAccessible"] or rds["Engine"] != "postgres" or rds["DBInstanceStatus"] != "available":
        raise ConfigurationError("RDS precisa estar privado e disponível")
    databases = set()
    for key, role, variable in (
        ("api_database", "api_user", "API_DB_PASSWORD"),
        ("agent_database", "mcp_reader", "MCP_DB_PASSWORD"),
        ("batch_database", "batch_user", "BATCH_DB_PASSWORD"),
        ("migration_database", "migration_user", None),
    ):
        url = make_url(values[key])
        if url.drivername != "postgresql+psycopg" or url.username != role or url.host != rds["Endpoint"]["Address"]:
            raise ConfigurationError("URL de banco incompatível com a role/RDS configurados")
        if (
            url.query.get("sslmode") != "verify-full"
            or url.query.get("sslrootcert") != "/app/certs/rds-global-bundle.pem"
        ):
            raise ConfigurationError("URLs exigem sslmode=verify-full e o CA bundle da imagem")
        if not url.password or (variable and passwords.get(variable) != url.password):
            raise ConfigurationError("Senhas dos segredos de URL e de migração não conferem")
        databases.add(url.database)
    if len(databases) != 1 or not next(iter(databases)) or next(iter(databases)).endswith("_test"):
        raise ConfigurationError("Todos os serviços devem usar o mesmo banco operacional, nunca _test")


def service_deployments(ecs, cluster, service):
    """ListServiceDeployments não tem paginator no SDK: seguir nextToken explicitamente."""
    deployments, token = [], None
    while True:
        page = ecs.list_service_deployments(cluster=cluster, service=service, **({"nextToken": token} if token else {}))
        deployments.extend(page.get("serviceDeployments", []))
        token = page.get("nextToken")
        if not token:
            return deployments


def wait_for_service(ecs, config, service_arn, definition):
    """Express usa canário: rolloutState de rolling update não é uma condição válida."""
    deadline = time.monotonic() + 1200
    revisions = {}
    while time.monotonic() < deadline:
        deployments = service_deployments(ecs, config["cluster"], service_arn)
        unknown = list({d["targetServiceRevisionArn"] for d in deployments} - revisions.keys())
        for offset in range(0, len(unknown), 20):
            result = ecs.describe_service_revisions(serviceRevisionArns=unknown[offset : offset + 20])
            if result.get("failures"):
                raise ConfigurationError("Não foi possível conferir a revisão do serviço")
            revisions.update({r["serviceRevisionArn"]: r["taskDefinition"] for r in result.get("serviceRevisions", [])})
        matching = [d for d in deployments if revisions.get(d["targetServiceRevisionArn"]) == definition]
        matching.sort(key=lambda d: d.get("createdAt").timestamp() if d.get("createdAt") else 0, reverse=True)
        if matching:
            status = matching[0]["status"]
            if status in {
                "STOPPED",
                "STOP_REQUESTED",
                "ROLLBACK_REQUESTED",
                "ROLLBACK_IN_PROGRESS",
                "ROLLBACK_SUCCESSFUL",
                "ROLLBACK_FAILED",
            }:
                raise ConfigurationError("Deploy interrompido ou em rollback; conferir recibo sem reverter o banco")
            if status == "SUCCESSFUL":
                # Serviços Express não expõem taskDefinition em DescribeServices: conferir a revisão.
                target = matching[0]["targetServiceRevisionArn"]
                observed = ecs.describe_services(cluster=config["cluster"], services=[service_arn])
                services = observed.get("services", [])
                if (
                    services
                    and services[0]["runningCount"] > 0
                    and services[0]["pendingCount"] == 0
                    and any(
                        r.get("arn") == target and r.get("runningTaskCount", 0) > 0
                        for r in services[0].get("currentServiceRevisions", [])
                    )
                ):
                    return
        time.sleep(10)
    raise ConfigurationError("Timeout esperando o canário da nova task definition; deploy não concluído")


def deploy(config, session, release, receipt_path):
    ecs = client(session, "ecs")
    for image in config["images"].values():
        repository, digest = image.split("/", 1)[1].split("@", 1)
        client(session, "ecr").describe_images(repositoryName=repository, imageIds=[{"imageDigest": digest}])
    validate_secrets(config, session)
    with deployment_lock(config, session, release):
        definitions = task_definitions(config)
        registered = {name: register(ecs, definition) for name, definition in definitions.items() if name != "web"}
        web_definition = task_definitions(config, registered["batch"])["web"]
        Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
        (Path(receipt_path).parent / "web.json").write_text(json.dumps(web_definition, indent=2) + "\n")
        registered["web"] = register(ecs, web_definition)
        existing = ecs.describe_services(cluster=config["cluster"], services=[config["name"]])
        if any(failure.get("reason") != "MISSING" for failure in existing.get("failures", [])):
            raise ConfigurationError("Consulta ao serviço ECS falhou; não criar outro serviço")
        service = next((s for s in existing.get("services", []) if s["status"] == "ACTIVE"), None)
        previous = None
        if service:
            current = ecs.describe_express_gateway_service(serviceArn=service["serviceArn"])["service"]
            if current["infrastructureRoleArn"] != config["roles"]["infrastructure"]:
                raise ConfigurationError("Role de infraestrutura diverge; não recriar serviço automaticamente")
            # DescribeServices não traz taskDefinition em serviços Express.
            previous = next((c.get("taskDefinitionArn") for c in current.get("activeConfigurations", [])), None)
        receipt = {
            "release": release,
            "task_definitions": registered,
            "previous_task_definition": previous,
            "tasks": {},
        }

        def save():
            path = Path(receipt_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, indent=2) + "\n")

        save()
        for step in ("migrate", "bootstrap", "index"):
            receipt["tasks"][step] = one_off(ecs, config, registered[step], release, step)
            save()
        parameters = {
            "taskDefinitionArn": registered["web"],
            "healthCheckPath": "/api/v1/healthz",
            "networkConfiguration": {"subnets": config["subnets"], "securityGroups": config["security_groups"]},
            "scalingTarget": {"minTaskCount": 1, "maxTaskCount": 1},
        }
        if service:
            response = ecs.update_express_gateway_service(serviceArn=service["serviceArn"], **parameters)
        else:
            response = ecs.create_express_gateway_service(
                cluster=config["cluster"],
                serviceName=config["name"],
                infrastructureRoleArn=config["roles"]["infrastructure"],
                tags=[{"key": "vx-project", "value": config["name"]}],
                **parameters,
            )
        receipt["service_arn"] = response["service"]["serviceArn"]
        save()
        wait_for_service(ecs, config, receipt["service_arn"], registered["web"])
        details = ecs.describe_express_gateway_service(serviceArn=receipt["service_arn"])["service"]
        endpoints = [
            p["endpoint"]
            for c in details.get("activeConfigurations", [])
            if c.get("taskDefinitionArn") == registered["web"]
            for p in c.get("ingressPaths", [])
            if p.get("accessType") == "PUBLIC"
        ]
        if not endpoints:
            raise ConfigurationError("Endpoint público da revisão nova ainda indisponível; consulte o recibo")
        express = endpoints[0].rstrip("/")
        if not express.startswith("https://"):
            express = "https://" + express
        # Um domínio próprio (CloudFront na frente do Express) pode ser a origem pública.
        # Ele precisa responder como o Express, senão cookies e callback apontariam para outro lugar.
        origin = config["public_origin"] or express
        for url in dict.fromkeys((express, origin)):
            with urlopen(url + "/api/v1/healthz", timeout=30) as response:
                if response.status != 200 or json.load(response).get("status") != "ok":
                    raise ConfigurationError(f"Liveness HTTPS falhou em {url}")
        receipt["express_origin"] = express
        receipt["public_origin"] = origin
        save()
        print(
            f"PASS deploy/liveness: {origin}; login, callback Cognito e smoke autenticado ainda precisam de validação"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap", "deploy"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--apply", action="store_true", help="Sem esta opção, só renderiza/mostra o plano offline")
    parser.add_argument("--render-dir", default="deployment/generated")
    parser.add_argument("--release", help="Identificador imutável e exclusivo da implantação, por exemplo o commit")
    args = parser.parse_args()
    config = load_config(args.config)
    render(config, args.render_dir)
    if not args.apply:
        print(f"OFFLINE {args.command}: tasks geradas; nenhuma consulta AWS executada")
        return 0
    if args.command == "deploy" and not args.release:
        parser.error("--apply deploy exige --release para idempotência de RunTask")
    session = aws_session(config, args.profile)
    if args.command == "bootstrap":
        bootstrap(config, session)
    else:
        deploy(config, session, args.release, Path(args.render_dir) / "receipt.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Exceções de parsing/SDK podem carregar URLs de banco e valores de parâmetros.
        print(
            f"FAIL AWS: {type(error).__name__}; confira preflight, recibo e logs, sem expor segredos", file=sys.stderr
        )
        sys.exit(1)
