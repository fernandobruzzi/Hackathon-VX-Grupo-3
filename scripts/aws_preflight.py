"""Inspeção AWS sem mutações; invocação de modelos exige --invoke-models explícito."""

import argparse
import json
import sys

from aws_support import ConfigurationError, load_config, render


class Report:
    def __init__(self):
        self.items = []

    def add(self, name, status, detail):
        self.items.append({"check": name, "status": status, "detail": detail})

    def check(self, name, callback):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            detail = callback()
            self.add(name, "PASS", detail or "Consulta concluída; não comprova permissão de escrita")
        except ClientError as error:
            code = error.response["Error"]["Code"]
            self.add(name, "DENIED" if "Denied" in code or "Unauthorized" in code else "FAIL", code)
        except (BotoCoreError, ConfigurationError, ValueError, KeyError) as error:
            # Mensagens completas podem conter URLs ou dados de autenticação.
            self.add(name, "FAIL", type(error).__name__)

    def finish(self):
        print(json.dumps(self.items, indent=2, ensure_ascii=False))
        return int(any(item["status"] in {"FAIL", "DENIED"} for item in self.items))


def preflight(config, session, invoke_models=False):
    from botocore.config import Config

    sdk = Config(connect_timeout=5, read_timeout=30, retries={"mode": "standard", "max_attempts": 2})
    report = Report()

    def client(service):
        return session.client(service, region_name=config["region"], config=sdk)

    identity = client("sts").get_caller_identity()
    if identity["Account"] != config["account_id"]:
        raise ConfigurationError("Credenciais pertencem a outra conta; nenhuma outra consulta foi executada")
    report.add("account", "PASS", f"Conta esperada, região {config['region']}")
    for kind, arn in config["roles"].items():

        def check_role(role_arn=arn, role_kind=kind):
            role = client("iam").get_role(RoleName=role_arn.rsplit("/", 1)[-1])["Role"]
            if role["Arn"] != role_arn:
                raise ConfigurationError("ARN da role diverge")
            principal = "ecs.amazonaws.com" if role_kind == "infrastructure" else "ecs-tasks.amazonaws.com"
            statements = role["AssumeRolePolicyDocument"]["Statement"]
            if not any(
                s.get("Effect") == "Allow"
                and principal
                in (
                    [s.get("Principal", {}).get("Service")]
                    if isinstance(s.get("Principal", {}).get("Service"), str)
                    else s.get("Principal", {}).get("Service", [])
                )
                for s in statements
            ):
                raise ConfigurationError("Trust principal incompatível")
            return "Trust principal presente; condições, boundary e PassRole ainda precisam de canário"

        report.check(f"role.{kind}", check_role)

    def network():
        ec2 = client("ec2")
        subnets = ec2.describe_subnets(SubnetIds=config["subnets"])["Subnets"]
        vpcs = {s["VpcId"] for s in subnets}
        if len(vpcs) != 1:
            raise ConfigurationError("Subnets em VPCs diferentes")
        vpc = next(iter(vpcs))
        groups = ec2.describe_security_groups(GroupIds=config["security_groups"])["SecurityGroups"]
        if any(g["VpcId"] != vpc for g in groups):
            raise ConfigurationError("Security group em outra VPC")
        tables = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc]}])["RouteTables"]
        for subnet in subnets:
            matches = [t for t in tables if any(a.get("SubnetId") == subnet["SubnetId"] for a in t["Associations"])]
            if not matches:
                matches = [t for t in tables if any(a.get("Main") for a in t["Associations"])]
            if len(matches) != 1 or not any(
                r.get("DestinationCidrBlock") == "0.0.0.0/0"
                and r.get("GatewayId", "").startswith("igw-")
                and r.get("State") == "active"
                for r in matches[0]["Routes"]
            ):
                raise ConfigurationError("Task sem rota pública ativa para internet gateway")
        return "Subnets públicas e SGs na mesma VPC; testar ENI/IP público e tráfego real na task"

    report.check("network", network)

    def rds():
        instance = client("rds").describe_db_instances(DBInstanceIdentifier=config["rds_instance"])["DBInstances"][0]
        if instance["PubliclyAccessible"] or instance["Engine"] != "postgres":
            raise ConfigurationError("RDS precisa ser PostgreSQL privado")
        subnets = client("ec2").describe_subnets(SubnetIds=config["subnets"])["Subnets"]
        if instance["DBSubnetGroup"]["VpcId"] != subnets[0]["VpcId"]:
            raise ConfigurationError("RDS está em outra VPC")
        if instance["DBInstanceStatus"] != "available":
            raise ConfigurationError("RDS ainda não está disponível")
        return "RDS privado disponível; vector, SSL, grants e senhas exigem conexão dentro da VPC"

    report.check("rds", rds)
    ecs = client("ecs")

    def cluster():
        result = ecs.describe_clusters(clusters=[config["cluster"]])
        if result.get("failures") or not result["clusters"] or result["clusters"][0]["status"] != "ACTIVE":
            raise ConfigurationError("Cluster ausente/inativo")
        return "Cluster ativo"

    report.check("ecs.cluster", cluster)
    report.check(
        "ecs.express.read",
        lambda: (ecs.list_services(cluster=config["cluster"], resourceManagementType="ECS"), None)[1],
    )
    for key, arn in config["secrets"].items():
        if not arn or (key in {"session_encryption", "cognito_client_secret"} and config["auth_backend"] != "cognito"):
            continue
        report.check(
            f"secret.metadata.{arn.rsplit(':', 1)[-1]}",
            lambda secret=arn: (client("secretsmanager").describe_secret(SecretId=secret), None)[1],
        )
    for service in ("ecs", "rds", "vpc", "bedrock", "elasticloadbalancing"):

        def quotas(code=service):
            pages = client("service-quotas").get_paginator("list_service_quotas").paginate(ServiceCode=code)
            return [
                {"name": q["QuotaName"], "code": q["QuotaCode"], "value": q["Value"], "unit": q["Unit"]}
                for page in pages
                for q in page.get("Quotas", [])
            ]

        report.check(f"quotas.{service}", quotas)
    for name, model in (("embedding", config["bedrock_embedding_model"]), ("chat", config["bedrock_chat_model"])):
        if not model:
            report.add(f"bedrock.{name}", "NOT_PROVEN", "Modelo não selecionado")
            continue
        if invoke_models:

            def invoke(kind=name, model_id=model):
                runtime = client("bedrock-runtime")
                if kind == "embedding":
                    response = runtime.invoke_model(
                        modelId=model_id,
                        contentType="application/json",
                        accept="application/json",
                        body=json.dumps({"inputText": "Teste de material", "dimensions": 512, "normalize": True}),
                    )
                    with response["body"] as stream:
                        value = json.loads(stream.read())
                    if len(value.get("embedding", [])) != 512:
                        raise ConfigurationError("Embedding não possui 512 dimensões")
                else:
                    runtime.converse(
                        modelId=model_id,
                        messages=[{"role": "user", "content": [{"text": "Responda OK"}]}],
                        inferenceConfig={"maxTokens": 16},
                    )
                return "Invocação real concluída; pequena cobrança pode ser aplicada"

            report.check(f"bedrock.{name}.invoke", invoke)
        else:
            report.add(
                f"bedrock.{name}.invoke", "NOT_PROVEN", "Use --invoke-models para testar acesso real e dimensões"
            )
    pool, app = config["cognito_user_pool_id"], config["cognito_app_client_id"]
    if pool and app:

        def cognito():
            from urllib.parse import urlsplit

            value = client("cognito-idp").describe_user_pool_client(UserPoolId=pool, ClientId=app)["UserPoolClient"]
            if not value.get("AllowedOAuthFlowsUserPoolClient") or value.get("AllowedOAuthFlows") != ["code"]:
                raise ConfigurationError("Cognito precisa usar apenas Authorization Code")
            callbacks = value.get("CallbackURLs", [])
            if not callbacks or "openid" not in value.get("AllowedOAuthScopes", []):
                raise ConfigurationError("Cognito sem callback ou escopo openid")
            if any(
                urlsplit(url).scheme != "https"
                and not (urlsplit(url).scheme == "http" and urlsplit(url).hostname == "localhost")
                for url in callbacks
            ):
                raise ConfigurationError("Callback inseguro fora de localhost")
            if config["public_origin"] and config["public_origin"] + "/auth/callback/" not in callbacks:
                raise ConfigurationError("Callback exato da origem pública não está registrado")
            return "Code flow/openid e callbacks conferidos; conferir URI exata e executar PKCE no navegador"

        report.check("cognito.client", cognito)
    else:
        report.add("cognito", "NOT_PROVEN", "User pool/app client ainda não configurados")
    report.add("deployment.permissions", "NOT_PROVEN", "Read APIs não comprovam IAM/PassRole/ECS Create/RDS DDL")
    report.add(
        "deployment.canary", "NOT_PROVEN", "Executar task real, migração, logins SQL e login HTTPS na conta do workshop"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--offline", action="store_true", help="Valida/renderiza sem criar sessão AWS")
    parser.add_argument("--render-dir")
    parser.add_argument(
        "--invoke-models", action="store_true", help="Faz pequenas chamadas reais, com possível cobrança"
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if args.render_dir:
        render(config, args.render_dir)
    if args.offline:
        if args.invoke_models:
            parser.error("--offline não aceita --invoke-models")
        print("PASS configuração e renderização offline; permissões e recursos AWS NÃO comprovados")
        return 0
    import boto3

    report = preflight(
        config, boto3.Session(profile_name=args.profile, region_name=config["region"]), args.invoke_models
    )
    return report.finish()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Saída curta: nunca imprimir respostas AWS, tokens ou URLs de banco.
        print(f"FAIL preflight: {type(error).__name__}; confira configuração e credenciais", file=sys.stderr)
        sys.exit(1)
