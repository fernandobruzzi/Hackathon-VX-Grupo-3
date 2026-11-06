"""Configuração e task definitions, sem consultar credenciais ou modificar a AWS."""

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


def load_config(path):
    config = json.loads(Path(path).read_text())
    required = {
        "account_id",
        "region",
        "name",
        "cluster",
        "architecture",
        "subnets",
        "security_groups",
        "rds_instance",
        "bucket",
        "log_group",
        "auth_backend",
        "public_origin",
        "cognito_domain",
        "authorized_center_codes",
        "embedding_repository",
        "roles",
        "images",
        "secrets",
        "bedrock_embedding_model",
        "bedrock_chat_model",
        "cognito_user_pool_id",
        "cognito_app_client_id",
    }
    if set(config) != required:
        raise ConfigurationError("Chaves ausentes ou desconhecidas na configuração; use aws.example.json")
    if not re.fullmatch(r"\d{12}", config["account_id"]):
        raise ConfigurationError("account_id inválido")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", config["region"]):
        raise ConfigurationError("region inválida")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,31}", config["name"]):
        raise ConfigurationError("name inválido")
    if config["architecture"] not in {"X86_64", "ARM64"}:
        raise ConfigurationError("architecture deve ser X86_64 ou ARM64")
    if config["auth_backend"] not in {"disabled", "cognito"}:
        raise ConfigurationError("auth_backend deve ser disabled (primeiro HTTPS) ou cognito")
    for key in ("public_origin", "cognito_domain"):
        value = config[key]
        if value:
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise ConfigurationError(f"{key} precisa ser origem HTTPS sem caminho/credenciais")
    if config["auth_backend"] == "cognito" and not all(
        config[key] for key in ("public_origin", "cognito_domain", "cognito_user_pool_id", "cognito_app_client_id")
    ):
        raise ConfigurationError("Cognito exige origem pública, domínio, pool e app client")
    if config["cognito_user_pool_id"] and not config["cognito_user_pool_id"].startswith(config["region"] + "_"):
        raise ConfigurationError("User pool e região incompatíveis com a configuração da API")
    if (
        not isinstance(config["authorized_center_codes"], list)
        or not config["authorized_center_codes"]
        or any(
            not isinstance(code, str) or not re.fullmatch(r"\d{4}", code) for code in config["authorized_center_codes"]
        )
    ):
        raise ConfigurationError("authorized_center_codes precisa conter centros com quatro dígitos")
    if config["embedding_repository"] not in {"", "bedrock_titan_v1"}:
        raise ConfigurationError("Deploy só aceita embeddings desligados ou Bedrock real")
    if (
        config["embedding_repository"] == "bedrock_titan_v1"
        and config["bedrock_embedding_model"] != "amazon.titan-embed-text-v2:0"
    ):
        raise ConfigurationError("O repositório atual usa exclusivamente Titan Text Embeddings V2")
    for key, prefix in (("subnets", "subnet"), ("security_groups", "sg")):
        if not isinstance(config[key], list) or not config[key]:
            raise ConfigurationError(f"{key} precisa ser uma lista não vazia")
        if any(not re.fullmatch(rf"{prefix}-[0-9a-f]{{8,17}}", value) for value in config[key]):
            raise ConfigurationError(f"{key} contém ID inválido")
    roles = config["roles"]
    if set(roles) != {"execution", "web", "batch", "infrastructure"}:
        raise ConfigurationError("roles inválidas")
    for arn in roles.values():
        if not arn.startswith(f"arn:aws:iam::{config['account_id']}:role/"):
            raise ConfigurationError("Role deve pertencer à conta configurada")
    if set(config["images"]) != {"api", "agent", "batch"}:
        raise ConfigurationError("images inválidas")
    registry = f"{config['account_id']}.dkr.ecr.{config['region']}.amazonaws.com/"
    for image in config["images"].values():
        if not image.startswith(registry) or not re.fullmatch(r".+@sha256:[0-9a-f]{64}", image):
            raise ConfigurationError("Use digest ECR imutável da conta/região configurada")
    if set(config["secrets"]) != {
        "api_database",
        "agent_database",
        "batch_database",
        "migration_database",
        "database_passwords",
        "internal_token",
        "session_encryption",
        "cognito_client_secret",
    }:
        raise ConfigurationError("secrets inválidos")
    prefix = f"arn:aws:secretsmanager:{config['region']}:{config['account_id']}:secret:"
    if any(
        not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9/_+=.@-]+", value)
        for key, value in config["secrets"].items()
        if key != "cognito_client_secret" or value
    ):
        raise ConfigurationError("Segredos devem usar ARN da conta/região, sem valores literais")
    return config


def task_definitions(config, batch_definition=None):
    """Gera apenas referências a segredos; valores nunca entram no manifesto."""

    def container(name, image, database, command=None):
        result = {
            "name": name,
            "image": config["images"][image],
            "essential": True,
            "linuxParameters": {"initProcessEnabled": True},
            "environment": [
                {"name": "APP_ENV", "value": "production"},
                {"name": "LOCAL_TEST_SESSION", "value": "false"},
                {"name": "ENABLE_LOCAL_TEST_SESSIONS", "value": "false"},
                {"name": "DEMO_MODE", "value": "false"},
                {"name": "AWS_REGION", "value": config["region"]},
                {"name": "AWS_DEFAULT_REGION", "value": config["region"]},
                {"name": "STORAGE_BACKEND", "value": "s3"},
                {"name": "S3_BUCKET", "value": config["bucket"]},
                {"name": "EMBEDDING_REPOSITORY", "value": config["embedding_repository"]},
            ],
            "secrets": [{"name": "DATABASE_URL", "valueFrom": config["secrets"][database]}],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": config["log_group"],
                    "awslogs-region": config["region"],
                    "awslogs-stream-prefix": name,
                },
            },
        }
        if command:
            result["command"] = command
        for key in ("bedrock_chat_model", "bedrock_embedding_model"):
            if config[key]:
                variable = {
                    "bedrock_chat_model": "BEDROCK_CHAT_MODEL_ID",
                    "bedrock_embedding_model": "BEDROCK_EMBEDDING_MODEL_ID",
                }.get(key, key.upper())
                result["environment"].append({"name": variable, "value": config[key]})
        return result

    def task(kind, containers, role="batch"):
        return {
            "family": f"{config['name']}-{kind}",
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": "1024",
            "memory": "2048",
            "runtimePlatform": {"operatingSystemFamily": "LINUX", "cpuArchitecture": config["architecture"]},
            "executionRoleArn": config["roles"]["execution"],
            "taskRoleArn": config["roles"][role],
            "containerDefinitions": containers,
        }

    main = container("Main", "api", "api_database")
    main["portMappings"] = [{"containerPort": 8000, "protocol": "tcp", "name": "http"}]
    main["environment"].append({"name": "AGENT_URL", "value": "http://127.0.0.1:8001"})
    main["environment"].extend(
        [
            {"name": "AUTH_BACKEND", "value": config["auth_backend"]},
            {"name": "BATCH_RUNNER", "value": ""},
            {"name": "AUTHORIZED_CENTER_CODES", "value": ",".join(config["authorized_center_codes"])},
        ]
    )
    for key, variable in (
        ("public_origin", "APP_ORIGIN"),
        ("cognito_domain", "COGNITO_DOMAIN"),
        ("cognito_user_pool_id", "COGNITO_USER_POOL_ID"),
        ("cognito_app_client_id", "COGNITO_APP_CLIENT_ID"),
    ):
        if config[key]:
            main["environment"].append({"name": variable, "value": config[key]})
    if config["auth_backend"] == "cognito":
        main["secrets"].append({"name": "SESSION_ENCRYPTION_KEY", "valueFrom": config["secrets"]["session_encryption"]})
        if config["secrets"]["cognito_client_secret"]:
            main["secrets"].append(
                {"name": "COGNITO_APP_CLIENT_SECRET", "valueFrom": config["secrets"]["cognito_client_secret"]}
            )
    if batch_definition:
        next(e for e in main["environment"] if e["name"] == "BATCH_RUNNER")["value"] = "ecs_fargate"
        main["environment"].extend(
            [
                {"name": "ECS_CLUSTER", "value": config["cluster"]},
                {"name": "ECS_BATCH_TASK_DEFINITION", "value": batch_definition},
                {"name": "ECS_SUBNET_IDS", "value": ",".join(config["subnets"])},
                {"name": "ECS_SECURITY_GROUP_IDS", "value": ",".join(config["security_groups"])},
                {"name": "ECS_ASSIGN_PUBLIC_IP", "value": "ENABLED"},
                {"name": "BATCH_HEARTBEAT_TIMEOUT_SECONDS", "value": "300"},
            ]
        )
    main["dependsOn"] = [{"containerName": "Agent", "condition": "HEALTHY"}]
    agent = container("Agent", "agent", "agent_database")
    for item, port, path in ((main, 8000, "/api/v1/healthz"), (agent, 8001, "/healthz")):
        item["secrets"].append(
            {"name": "AGENT_INTERNAL_TOKEN_SECRET", "valueFrom": config["secrets"]["internal_token"]}
        )
        item["healthCheck"] = {
            "command": [
                "CMD",
                "python",
                "-c",
                f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}{path}',timeout=2)",
            ],
            "interval": 10,
            "timeout": 3,
            "retries": 6,
            "startPeriod": 30,
        }
    migration = container("Migrate", "api", "migration_database", ["sh", "-c", "vx-db upgrade && vx-db set-passwords"])
    migration["secrets"] = [{"name": "MIGRATION_DATABASE_URL", "valueFrom": config["secrets"]["migration_database"]}]
    for variable in ("API_DB_PASSWORD", "BATCH_DB_PASSWORD", "MCP_DB_PASSWORD"):
        migration["secrets"].append(
            {"name": variable, "valueFrom": f"{config['secrets']['database_passwords']}:{variable}::"}
        )
    return {
        "web": task("web", [main, agent], "web"),
        "migrate": task("migrate", [migration], "web"),
        "bootstrap": task("bootstrap", [container("Bootstrap", "api", "api_database", ["vx-bootstrap"])], "web"),
        "index": task("index", [container("Index", "batch", "batch_database", ["vx-back", "index"])]),
        "batch": task("batch", [container("Batch", "batch", "batch_database", ["vx-back", "sanitize"])]),
    }


def render(config, directory):
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    for name, definition in task_definitions(config).items():
        (destination / f"{name}.json").write_text(json.dumps(definition, indent=2) + "\n")


def canonical_task(actual, desired):
    """Compara somente os campos declarados, ignorando metadados/defaults do ECS."""

    def subset(value, template):
        if isinstance(template, dict):
            return (
                {key: subset(value.get(key), item) for key, item in template.items()}
                if isinstance(value, dict)
                else value
            )
        if isinstance(template, list):
            if not isinstance(value, list) or len(value) != len(template):
                return value
            return [subset(item, shape) for item, shape in zip(value, template, strict=True)]
        return value

    return subset(copy.deepcopy(actual), desired) == desired
