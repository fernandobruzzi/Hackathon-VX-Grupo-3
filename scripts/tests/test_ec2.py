"""Plano B: render sem credenciais, portas privadas e arquivos de segredos restritos."""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_support import ConfigurationError, load_config  # noqa: E402
from ec2_deploy import (  # noqa: E402
    apply_ec2,
    compose_plan,
    docker_login,
    origin_for,
    render_ec2,
    write_private_env,
    write_secret_files,
)

EXAMPLE = Path(__file__).resolve().parents[2] / "deployment" / "aws.example.json"
PYTHON_IMAGE = "python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54"


class Ec2Tests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(EXAMPLE)

    def test_plain_ip_path_and_shell_text_are_rejected(self):
        for host in (
            "203.0.113.10",
            "https://example.com",
            "example.com/path",
            "example.com:443",
            "$(exit).example",
            "a..example",
        ):
            with self.subTest(host=host), self.assertRaises(ConfigurationError):
                origin_for(host)
        self.assertEqual(origin_for("203.0.113.10.nip.io"), "https://203.0.113.10.nip.io")

    def test_only_caddy_publishes_ports_and_no_local_database_is_created(self):
        plan = compose_plan(self.config, "203.0.113.10.nip.io", "caddy:2-alpine")
        self.assertNotIn("db", plan["services"])
        for name, service in plan["services"].items():
            if name != "caddy":
                self.assertNotIn("ports", service)
                self.assertEqual(service["env_file"][0]["format"], "raw")
                self.assertEqual(service["environment"]["APP_ENV"], "production")
                self.assertEqual(service["environment"]["LOCAL_TEST_SESSION"], "false")
        self.assertEqual(plan["services"]["caddy"]["ports"], ["80:80", "443:443"])
        self.assertIn("caddy-data:/data", plan["services"]["caddy"]["volumes"])
        self.assertEqual(plan["services"]["api"]["environment"]["AGENT_URL"], "http://agent:8001")
        self.assertEqual(plan["services"]["api"]["environment"]["BATCH_RUNNER"], "")

    def test_callback_origin_mismatch_is_rejected(self):
        self.config["public_origin"] = "https://different.example"
        with self.assertRaises(ConfigurationError):
            compose_plan(self.config, "203.0.113.10.nip.io", "caddy:2-alpine")

    def test_applied_plan_requires_every_secret_file(self):
        plan = compose_plan(self.config, "203.0.113.10.nip.io", "caddy:2-alpine", require_secrets=True)
        for name, service in plan["services"].items():
            if name != "caddy":
                self.assertTrue(service["env_file"][0]["required"])

    def test_render_never_reads_credentials_or_writes_secret_files(self):
        with tempfile.TemporaryDirectory() as directory, patch("boto3.Session", side_effect=AssertionError("network")):
            render_ec2(self.config, "203.0.113.10.nip.io", directory, "caddy:2-alpine")
            self.assertTrue((Path(directory) / "compose.json").exists())
            self.assertFalse(list(Path(directory).glob("*.env")))
            self.assertEqual(
                (Path(directory) / "Caddyfile").read_text(), "203.0.113.10.nip.io {\n\treverse_proxy api:8000\n}\n"
            )

    def test_private_env_preserves_password_symbols_and_rejects_multiline_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "api.env"
            value = "postgresql://user:p@ss$'?#%/db"
            write_private_env(target, {"DATABASE_URL": value})
            self.assertEqual(target.read_text(), f"DATABASE_URL={value}\n")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ConfigurationError):
                write_private_env(target, {"DATABASE_URL": "first\nSECOND=bad"})
            link = Path(directory) / "link.env"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                write_private_env(link, {"DATABASE_URL": "replace"})

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose necessário para validar o runtime")
    def test_real_container_receives_raw_values_without_interpolation(self):
        if subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode:
            self.skipTest("Daemon Docker indisponível")
        with tempfile.TemporaryDirectory() as directory:
            value = "fake-value$'\"#%"
            write_private_env(Path(directory) / "check.env", {"SMOKE_RAW": value})
            manifest = {
                "services": {
                    "check": {
                        "image": PYTHON_IMAGE,
                        "network_mode": "none",
                        "env_file": [{"path": "check.env", "format": "raw"}],
                        "command": ["python", "-c", "import os; assert os.environ['SMOKE_RAW']==" + repr(value)],
                    }
                }
            }
            path = Path(directory) / "compose.json"
            path.write_text(json.dumps(manifest))
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    "vx-raw-" + uuid.uuid4().hex[:12],
                    "-f",
                    str(path),
                    "run",
                    "--rm",
                    "--no-deps",
                    "check",
                ],
                text=True,
                capture_output=True,
                check=True,
                timeout=120,
            )

    def test_migration_passwords_and_urls_remain_separated_by_service(self):
        session = Mock()
        password_values = {
            "API_DB_PASSWORD": "api-password",
            "BATCH_DB_PASSWORD": "batch-password",
            "MCP_DB_PASSWORD": "mcp-password",
        }
        by_arn = {arn: key for key, arn in self.config["secrets"].items()}

        def secret(SecretId):
            key = by_arn[SecretId]
            return {"SecretString": json.dumps(password_values) if key == "database_passwords" else key + "-value"}

        session.client.return_value.get_secret_value.side_effect = secret
        with tempfile.TemporaryDirectory() as directory:
            write_secret_files(self.config, session, directory)
            api = (Path(directory) / "api.env").read_text()
            agent = (Path(directory) / "agent.env").read_text()
            migration = (Path(directory) / "migrate.env").read_text()
            self.assertIn("DATABASE_URL=api_database-value", api)
            self.assertIn("DATABASE_URL=agent_database-value", agent)
            self.assertNotIn("migration_database", api + agent)
            self.assertNotIn("API_DB_PASSWORD", api + agent)
            self.assertIn("MIGRATION_DATABASE_URL=migration_database-value", migration)
            self.assertIn("API_DB_PASSWORD=api-password", migration)

    def test_registry_password_is_only_stdin_not_an_argument_or_log(self):
        import base64

        session = Mock()
        session.client.return_value.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                    "authorizationToken": base64.b64encode(b"AWS:private-password").decode(),
                }
            ]
        }
        with patch("ec2_deploy.subprocess.run") as run:
            docker_login(self.config, session)
        self.assertNotIn("private-password", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.kwargs["input"], "private-password")
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_apply_refuses_personal_credentials_before_touching_docker_or_secrets(self):
        session = Mock()
        session.get_credentials.return_value.method = "shared-credentials-file"
        with patch("ec2_deploy.subprocess.run") as run, patch("ec2_deploy.validate_secrets") as secrets:
            with self.assertRaises(ConfigurationError):
                apply_ec2(self.config, session, "203.0.113.10.nip.io", "/unused", "caddy:2-alpine", "release")
        run.assert_not_called()
        secrets.assert_not_called()

    def test_apply_runs_operations_before_web_and_optional_batch_after_https(self):
        session = Mock()
        session.get_credentials.return_value.method = "iam-role"
        response = io.BytesIO(b'{"status":"ok"}')
        response.status = 200
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("ec2_deploy.platform.machine", return_value="x86_64"),
            patch("ec2_deploy.validate_secrets"),
            patch("ec2_deploy.deployment_lock", return_value=nullcontext()),
            patch("ec2_deploy.write_secret_files"),
            patch("ec2_deploy.docker_login"),
            patch("ec2_deploy.subprocess.run") as run,
            patch("ec2_deploy.urlopen", return_value=response),
            redirect_stdout(io.StringIO()),
        ):
            apply_ec2(
                self.config, session, "203.0.113.10.nip.io", directory, "caddy:2-alpine", "release", run_batch=True
            )
            commands = [c.args[0] for c in run.call_args_list]
            operations = [command[-1] for command in commands if "run" in command]
            self.assertEqual(operations, ["migrate", "bootstrap", "index", "batch"])
            up = next(i for i, command in enumerate(commands) if "up" in command)
            self.assertLess(up, len(commands) - 1)
            receipt = json.loads((Path(directory) / "receipt.json").read_text())
            self.assertFalse(receipt["authentication_validated"])


if __name__ == "__main__":
    unittest.main()
