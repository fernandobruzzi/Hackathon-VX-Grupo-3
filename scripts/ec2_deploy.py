"""Render e publicação do Plano B em uma EC2 existente, com Caddy e instance profile."""

import argparse
import base64
import copy
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from aws_deploy import aws_session, client, deployment_lock, validate_secrets
from aws_support import ConfigurationError, load_config, task_definitions

CADDY_IMAGE = "caddy:2-alpine@sha256:ae5e525ca6773b0a4ce579c774cb39b3147e1576084139229517bdbcfe3ed812"


def origin_for(host):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host:
        raise ConfigurationError("Informe um hostname DNS público, sem protocolo, porta ou caminho")
    if re.fullmatch(r"[0-9.]+", host) or any(not part or len(part) > 63 for part in host.split(".")):
        raise ConfigurationError("Um IP sozinho não resolve o certificado/callback; use um hostname público")
    return f"https://{host}"


def compose_plan(config, host, caddy_image, require_secrets=False):
    origin = origin_for(host)
    if config["public_origin"] and config["public_origin"] != origin:
        raise ConfigurationError("Hostname do Plano B diverge de public_origin; registre o callback correto")
    local = copy.deepcopy(config)
    local["public_origin"] = origin
    definitions = task_definitions(local)

    def service(container, env_file):
        result = {
            "image": container["image"],
            "init": True,
            "environment": {e["name"]: e["value"] for e in container["environment"]},
            "env_file": [{"path": env_file, "format": "raw", "required": require_secrets}],
            "read_only": True,
            "tmpfs": ["/tmp"],
        }
        if "command" in container:
            result["command"] = container["command"]
        return result

    main, agent = definitions["web"]["containerDefinitions"]
    api = service(main, "api.env")
    api["environment"]["AGENT_URL"] = "http://agent:8001"
    api["restart"] = "unless-stopped"
    api["depends_on"] = {"agent": {"condition": "service_healthy"}}
    services = {"api": api, "agent": service(agent, "agent.env")}
    services["agent"]["restart"] = "unless-stopped"
    for name in ("migrate", "bootstrap", "index", "batch"):
        services[name] = service(definitions[name]["containerDefinitions"][0], f"{name}.env")
        services[name]["profiles"] = ["operations"]
    services["caddy"] = {
        "image": caddy_image,
        "restart": "unless-stopped",
        "init": True,
        "ports": ["80:80", "443:443"],
        "volumes": ["./Caddyfile:/etc/caddy/Caddyfile:ro", "caddy-data:/data", "caddy-config:/config"],
        "depends_on": {"api": {"condition": "service_healthy"}},
    }
    for item in services.values():
        item["logging"] = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
    return {"name": config["name"] + "-ec2", "services": services, "volumes": {"caddy-data": {}, "caddy-config": {}}}


def render_ec2(config, host, directory, caddy_image, require_secrets=False):
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    plan = compose_plan(config, host, caddy_image, require_secrets)
    (destination / "compose.json").write_text(json.dumps(plan, indent=2) + "\n")
    (destination / "Caddyfile").write_text(host + " {\n\treverse_proxy api:8000\n}\n")
    return plan


def write_private_env(path, values):
    for name, value in values.items():
        if (
            not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name)
            or not isinstance(value, str)
            or any(c in value for c in "\r\n\0")
        ):
            raise ConfigurationError("Segredo incompatível com env_file raw; não usar valores multilinha")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        os.chmod(path, 0o600)
        stream.write("".join(f"{name}={value}\n" for name, value in values.items()))


def write_secret_files(config, session, directory):
    secrets = client(session, "secretsmanager")
    cache = {}

    def read(reference):
        parts = reference.split(":")
        arn = ":".join(parts[:7])
        if arn not in cache:
            cache[arn] = secrets.get_secret_value(SecretId=arn)["SecretString"]
        if len(parts) == 7:
            return cache[arn]
        if len(parts) == 10 and not parts[8] and not parts[9]:
            return json.loads(cache[arn])[parts[7]]
        raise ConfigurationError("Formato de referência de segredo não suportado")

    definitions = task_definitions(config)
    containers = {
        "api": definitions["web"]["containerDefinitions"][0],
        "agent": definitions["web"]["containerDefinitions"][1],
    }
    containers.update(
        {name: definitions[name]["containerDefinitions"][0] for name in ("migrate", "bootstrap", "index", "batch")}
    )
    for name, container in containers.items():
        write_private_env(
            Path(directory) / f"{name}.env", {s["name"]: read(s["valueFrom"]) for s in container["secrets"]}
        )


def docker_login(config, session):
    expected = f"https://{config['account_id']}.dkr.ecr.{config['region']}.amazonaws.com"
    data = client(session, "ecr").get_authorization_token(registryIds=[config["account_id"]])["authorizationData"][0]
    if data["proxyEndpoint"] != expected:
        raise ConfigurationError("Registry ECR diferente da conta/região configurada")
    username, password = base64.b64decode(data["authorizationToken"]).decode().split(":", 1)
    subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", expected],
        input=password,
        text=True,
        capture_output=True,
        check=True,
    )


def apply_ec2(config, session, host, directory, caddy_image, release, run_batch=False):
    compose_plan(config, host, caddy_image)
    credentials = session.get_credentials()
    if credentials is None or credentials.method != "iam-role":
        raise ConfigurationError("Executar na EC2 com instance profile, sem credenciais estáticas/profile de usuário")
    expected_architecture = {"X86_64": "x86_64", "ARM64": "aarch64"}[config["architecture"]]
    if platform.machine().lower() != expected_architecture:
        raise ConfigurationError("Arquitetura da EC2 difere da configuração/imagens")
    config = copy.deepcopy(config)
    config["public_origin"] = origin_for(host)
    validate_secrets(config, session)
    with deployment_lock(config, session, release + "-ec2"):
        render_ec2(config, host, directory, caddy_image, require_secrets=True)
        write_secret_files(config, session, directory)
        docker_login(config, session)
        command = [
            "docker",
            "compose",
            "--project-name",
            config["name"] + "-ec2",
            "-f",
            str(Path(directory) / "compose.json"),
        ]
        subprocess.run([*command, "--profile", "operations", "pull"], check=True)
        for step in ("migrate", "bootstrap", "index"):
            subprocess.run([*command, "run", "--rm", "--no-deps", step], check=True)
        subprocess.run(
            [*command, "up", "-d", "--wait", "--wait-timeout", "180", "--force-recreate", "agent", "api", "caddy"],
            check=True,
        )
        origin = origin_for(host)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                with urlopen(origin + "/api/v1/healthz", timeout=10) as response:
                    if response.status == 200 and json.load(response).get("status") == "ok":
                        break
            except (URLError, TimeoutError, ValueError):
                pass
            time.sleep(2)
        else:
            raise ConfigurationError("HTTPS público não ficou pronto; conferir DNS, SG 80/443 e emissão ACME")
        if run_batch:
            subprocess.run([*command, "run", "--rm", "--no-deps", "batch"], check=True)
        (Path(directory) / "receipt.json").write_text(
            json.dumps(
                {
                    "release": release,
                    "public_origin": origin,
                    "images": config["images"],
                    "auth_backend": config["auth_backend"],
                    "authentication_validated": False,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"PASS serviços e liveness HTTPS: {origin}; validar login/cookies/CSRF/RBAC no navegador")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--host", required=True, help="Hostname público apontado para o IP estável da EC2")
    parser.add_argument("--render-dir", default="deployment/generated/ec2")
    parser.add_argument("--caddy-image", default=CADDY_IMAGE)
    parser.add_argument("--release")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-batch", action="store_true", help="Executa saneamento administrativo após subir HTTPS")
    args = parser.parse_args()
    config = load_config(args.config)
    compose_plan(config, args.host, args.caddy_image)
    if not args.apply:
        render_ec2(config, args.host, args.render_dir, args.caddy_image)
        print("OFFLINE compose/Caddy preparados; env files secretos só serão escritos em --apply na EC2")
        return 0
    if not args.release:
        parser.error("--apply exige --release")
    apply_ec2(
        config, aws_session(config, None), args.host, args.render_dir, args.caddy_image, args.release, args.run_batch
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Não imprimir stdout/stderr de docker login nem conteúdos de env_file.
        print(f"FAIL Plano B: {type(error).__name__}; conferir configuração, Compose e TLS", file=sys.stderr)
        sys.exit(1)
