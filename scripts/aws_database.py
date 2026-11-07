"""Segredos da aplicação e preparo do RDS pelo master, sem imprimir valores.

`secrets` cria no Secrets Manager as senhas, as URLs de banco, o token interno e a
chave de sessão. `init` executa dentro da VPC, como task Fargate com a imagem da API,
o SQL de "Database on AWS" (AGENTS.md) usando o segredo do master gerenciado pelo RDS.
"""

import argparse
import base64
import json
import secrets as random
import sys

from aws_support import ConfigurationError, load_config

DATABASE = "vx_materiais"
CA_BUNDLE = "/app/certs/rds-global-bundle.pem"
URL_SECRETS = {
    "api_database": ("api-database", "api_user", "API_DB_PASSWORD"),
    "agent_database": ("agent-database", "mcp_reader", "MCP_DB_PASSWORD"),
    "batch_database": ("batch-database", "batch_user", "BATCH_DB_PASSWORD"),
    "migration_database": ("migration-database", "migration_user", "MIGRATION_DB_PASSWORD"),
}
PASSWORD_KEYS = tuple(variable for _, _, variable in URL_SECRETS.values())

# Executado pela imagem da API: psycopg e o CA bundle do RDS já estão nela.
INIT_SCRIPT = """
import os, psycopg
from psycopg import sql
database = os.environ["DB_NAME"]
with psycopg.connect(host=os.environ["DB_HOST"], dbname="postgres", user=os.environ["MASTER_USER"],
                     password=os.environ["MASTER_PASSWORD"], sslmode="verify-full",
                     sslrootcert="__CA_BUNDLE__", autocommit=True) as conn:
    password = sql.Literal(os.environ["MIGRATION_DB_PASSWORD"])
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'migration_user'").fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL(verb + " ROLE migration_user LOGIN CREATEROLE PASSWORD {}").format(password))
    conn.execute("GRANT rds_superuser TO migration_user")
    # PG16: o master precisa poder assumir a role para criar o banco em nome dela.
    conn.execute(sql.SQL("GRANT migration_user TO {}").format(sql.Identifier(os.environ["MASTER_USER"])))
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone():
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER migration_user").format(sql.Identifier(database)))
    owner = conn.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (database,)
    ).fetchone()[0]
    vector = conn.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'vector'").fetchone()
    print(f"RDS_INIT database={database} owner={owner} vector={vector[0] if vector else 'AUSENTE'}")
    if owner != "migration_user" or not vector:
        raise SystemExit(1)
""".replace("__CA_BUNDLE__", CA_BUNDLE)


def secret_name(config, suffix):
    return f"{config['name']}/{suffix}"


def database_urls(endpoint, passwords, database=DATABASE):
    """URLs completas com encoding correto, como exige o runbook."""
    from sqlalchemy.engine import URL

    if set(passwords) != set(PASSWORD_KEYS):
        raise ConfigurationError("Segredo de senhas incompleto")
    return {
        key: URL.create(
            "postgresql+psycopg",
            username=role,
            password=passwords[variable],
            host=endpoint,
            port=5432,
            database=database,
            query={"sslmode": "verify-full", "sslrootcert": CA_BUNDLE},
        ).render_as_string(hide_password=False)
        for key, (_, role, variable) in URL_SECRETS.items()
    }


def new_values():
    """Senhas hexadecimais: sem caracteres que exijam escape em URL ou SQL."""
    return {
        "passwords": {variable: random.token_hex(24) for variable in PASSWORD_KEYS},
        "internal_token": random.token_urlsafe(48),
        "session_encryption": base64.urlsafe_b64encode(random.token_bytes(32)).decode(),
    }


def ensure_secrets(config, session, endpoint):
    """Cria o que falta e confere o que existe. Nunca sobrescreve nem imprime valores."""
    from botocore.exceptions import ClientError

    client = session.client("secretsmanager", region_name=config["region"])
    tags = [{"Key": "vx-project", "Value": config["name"]}]

    def read(name):
        try:
            return client.get_secret_value(SecretId=name)["SecretString"]
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            return None

    def ensure(name, value):
        current = read(name)
        if current is None:
            return client.create_secret(Name=name, SecretString=value, Tags=tags)["ARN"]
        if current != value:
            raise ConfigurationError(f"Segredo {name} existe com outro valor; rotacione explicitamente")
        return client.describe_secret(SecretId=name)["ARN"]

    generated = new_values()
    arns = {}
    stored = read(secret_name(config, "database-passwords"))
    passwords = json.loads(stored) if stored else generated["passwords"]
    arns["database_passwords"] = ensure(secret_name(config, "database-passwords"), json.dumps(passwords))
    for key, url in database_urls(endpoint, passwords).items():
        arns[key] = ensure(secret_name(config, URL_SECRETS[key][0]), url)
    for key, suffix in (("internal_token", "internal-token"), ("session_encryption", "session-encryption")):
        existing = read(secret_name(config, suffix))
        arns[key] = ensure(secret_name(config, suffix), existing or generated[key])
    arns["cognito_client_secret"] = config["secrets"].get("cognito_client_secret", "")
    return arns


def init_task(config, image, master_secret_arn, endpoint):
    return {
        "family": f"{config['name']}-rds-init",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": "256",
        "memory": "512",
        "runtimePlatform": {"operatingSystemFamily": "LINUX", "cpuArchitecture": config["architecture"]},
        "executionRoleArn": config["roles"]["execution"],
        "containerDefinitions": [
            {
                "name": "RdsInit",
                "image": image,
                "essential": True,
                "command": ["python", "-c", INIT_SCRIPT],
                "environment": [
                    {"name": "DB_HOST", "value": endpoint},
                    {"name": "DB_NAME", "value": DATABASE},
                ],
                "secrets": [
                    {"name": "MASTER_USER", "valueFrom": f"{master_secret_arn}:username::"},
                    {"name": "MASTER_PASSWORD", "valueFrom": f"{master_secret_arn}:password::"},
                    {
                        "name": "MIGRATION_DB_PASSWORD",
                        "valueFrom": f"{config['secrets']['database_passwords']}:MIGRATION_DB_PASSWORD::",
                    },
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": config["log_group"],
                        "awslogs-region": config["region"],
                        "awslogs-stream-prefix": "rds-init",
                    },
                },
            }
        ],
    }


def run_init(config, session, master_secret_arn):
    rds = session.client("rds", region_name=config["region"])
    instance = rds.describe_db_instances(DBInstanceIdentifier=config["rds_instance"])["DBInstances"][0]
    if instance["PubliclyAccessible"] or instance["DBInstanceStatus"] != "available":
        raise ConfigurationError("RDS precisa estar privado e disponível")
    ecs = session.client("ecs", region_name=config["region"])
    definition = init_task(config, config["images"]["api"], master_secret_arn, instance["Endpoint"]["Address"])
    arn = ecs.register_task_definition(**definition)["taskDefinition"]["taskDefinitionArn"]
    result = ecs.run_task(
        cluster=config["cluster"],
        taskDefinition=arn,
        launchType="FARGATE",
        platformVersion="1.4.0",
        count=1,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": config["subnets"],
                "securityGroups": config["security_groups"],
                "assignPublicIp": "ENABLED",
            }
        },
    )
    if result.get("failures") or len(result.get("tasks", [])) != 1:
        raise ConfigurationError("RunTask do preparo do RDS falhou")
    task = result["tasks"][0]["taskArn"]
    print(f"RUN rds-init: {task}", flush=True)
    ecs.get_waiter("tasks_stopped").wait(
        cluster=config["cluster"], tasks=[task], WaiterConfig={"Delay": 10, "MaxAttempts": 60}
    )
    container = ecs.describe_tasks(cluster=config["cluster"], tasks=[task])["tasks"][0]["containers"][0]
    if container.get("exitCode") != 0:
        raise ConfigurationError(f"Preparo do RDS falhou; confira o log rds-init em {config['log_group']}")
    print("PASS rds-init: migration_user, rds_superuser, banco e vector conferidos")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("secrets", "init"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--endpoint", help="secrets: endpoint DNS do RDS")
    parser.add_argument("--master-secret-arn", help="init: segredo do master gerenciado pelo RDS")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.command == "secrets":
        # O config ainda pode conter ARNs de exemplo nos segredos: só os campos usados são lidos.
        config = json.loads(open(args.config).read())
        if not args.endpoint:
            parser.error("secrets exige --endpoint")
    else:
        config = load_config(args.config)
        if not args.master_secret_arn:
            parser.error("init exige --master-secret-arn")
    if not args.apply:
        print(f"OFFLINE {args.command}: nada consultado nem criado; use --apply")
        return 0
    import boto3

    session = boto3.Session(profile_name=args.profile, region_name=config["region"])
    if session.client("sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ConfigurationError("Conta AWS diferente da configurada")
    if args.command == "secrets":
        print(json.dumps(ensure_secrets(config, session, args.endpoint), indent=2))
    else:
        run_init(config, session, args.master_secret_arn)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Exceções do SDK podem carregar valores de parâmetros: não imprimir a mensagem.
        print(f"FAIL AWS: {type(error).__name__}; nenhum segredo foi impresso", file=sys.stderr)
        sys.exit(1)
