"""Contas fictícias das três personas no Cognito, sem imprimir senhas.

Cria um usuário por persona com o e-mail já verificado e sem convite, já que os
endereços em `example.com` não recebem mensagens. Define a senha permanente,
associa somente o grupo da persona e guarda as credenciais no segredo
`<name>/demo-accounts`. Repetir o comando reaproveita as senhas guardadas.
"""

import argparse
import json
import secrets as random
import string
import sys

from aws_support import ConfigurationError, load_config

PERSONAS = (
    ("ana.souza@vx-grupo3.example.com", "Ana Souza", "ROLE_SOLICITANTE"),
    ("bruno.oliveira@vx-grupo3.example.com", "Bruno Oliveira", "ROLE_GOVERNANCA_PDM"),
    ("carla.pereira@vx-grupo3.example.com", "Carla Pereira", "ROLE_AUDITOR_FISCAL"),
)
GROUPS = {group for _, _, group in PERSONAS}


def new_password():
    """Atende a política do pool: 12+ caracteres com maiúscula, minúscula e número."""
    alphabet = string.ascii_letters + string.digits
    while True:
        value = "".join(random.choice(alphabet) for _ in range(20))
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value):
            return value


def ensure_accounts(config, session):
    from botocore.exceptions import ClientError

    pool = config["cognito_user_pool_id"]
    if not pool:
        raise ConfigurationError("Preencha cognito_user_pool_id antes de criar contas")
    cognito = session.client("cognito-idp", region_name=config["region"])
    secrets = session.client("secretsmanager", region_name=config["region"])
    name = f"{config['name']}/demo-accounts"
    try:
        stored = json.loads(secrets.get_secret_value(SecretId=name)["SecretString"])
        created = False
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        stored = {email: new_password() for email, _, _ in PERSONAS}
        secrets.create_secret(
            Name=name, SecretString=json.dumps(stored), Tags=[{"Key": "vx-project", "Value": config["name"]}]
        )
        created = True
    for email, full_name, group in PERSONAS:
        try:
            cognito.admin_create_user(
                UserPoolId=pool,
                Username=email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": full_name},
                ],
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "UsernameExistsException":
                raise
        if created:
            cognito.admin_set_user_password(UserPoolId=pool, Username=email, Password=stored[email], Permanent=True)
        current = {
            g["GroupName"] for g in cognito.admin_list_groups_for_user(UserPoolId=pool, Username=email)["Groups"]
        }
        for extra in current - {group}:
            cognito.admin_remove_user_from_group(UserPoolId=pool, Username=email, GroupName=extra)
        if group not in current:
            cognito.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=group)
        print(f"PASS {group}: {full_name} <{email}>")
    print(f"Senhas no segredo {name}; nenhuma foi impressa")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if not args.apply:
        for email, full_name, group in PERSONAS:
            print(f"OFFLINE {group}: {full_name} <{email}>")
        return 0
    import boto3

    session = boto3.Session(profile_name=args.profile, region_name=config["region"])
    if session.client("sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ConfigurationError("Conta AWS diferente da configurada")
    ensure_accounts(config, session)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"FAIL AWS: {type(error).__name__}; nenhuma senha foi impressa", file=sys.stderr)
        sys.exit(1)
