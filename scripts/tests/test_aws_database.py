"""Regressões offline do preparo de segredos e do RDS: nada consulta a AWS."""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import botocore.session
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_database import INIT_SCRIPT, ensure_secrets, init_task, new_values  # noqa: E402
from aws_deploy import validate_secrets  # noqa: E402
from aws_support import ConfigurationError, load_config  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[2] / "deployment" / "aws.example.json"
ENDPOINT = "vx-grupo3.abc.us-east-1.rds.amazonaws.com"


def not_found():
    return ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue")


class FakeSecrets:
    def __init__(self, stored=None):
        self.stored = dict(stored or {})
        self.created = []

    def arn(self, name):
        return f"arn:aws:secretsmanager:us-east-1:123456789012:secret:{name}-AbCdEf"

    def get_secret_value(self, SecretId):
        name = next((n for n in self.stored if SecretId in (n, self.arn(n))), None)
        if name is None:
            raise not_found()
        return {"SecretString": self.stored[name]}

    def create_secret(self, Name, SecretString, Tags):
        assert Tags == [{"Key": "vx-project", "Value": "vx-grupo3"}]
        self.stored[Name] = SecretString
        self.created.append(Name)
        return {"ARN": self.arn(Name)}

    def describe_secret(self, SecretId):
        return {"ARN": self.arn(SecretId)}


class AwsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(EXAMPLE)

    def session(self, secrets, endpoint=ENDPOINT):
        rds = Mock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "PubliclyAccessible": False,
                    "Engine": "postgres",
                    "DBInstanceStatus": "available",
                    "Endpoint": {"Address": endpoint},
                }
            ]
        }
        session = Mock()
        session.client.side_effect = lambda service, **kwargs: {"secretsmanager": secrets, "rds": rds}[service]
        return session

    def test_generated_secrets_pass_deploy_validation(self):
        secrets = FakeSecrets()
        arns = ensure_secrets(self.config, self.session(secrets), ENDPOINT)
        self.assertEqual(set(arns), set(self.config["secrets"]))
        self.assertEqual(len(secrets.created), 7)
        config = {**self.config, "auth_backend": "disabled", "secrets": arns}
        validate_secrets(config, self.session(secrets))
        key = base64.urlsafe_b64decode(secrets.stored["vx-grupo3/session-encryption"])
        self.assertEqual(len(key), 32)

    def test_rerun_reuses_values_and_never_overwrites(self):
        secrets = FakeSecrets()
        ensure_secrets(self.config, self.session(secrets), ENDPOINT)
        before = dict(secrets.stored)
        ensure_secrets(self.config, self.session(secrets), ENDPOINT)
        self.assertEqual(secrets.stored, before)
        self.assertEqual(len(secrets.created), 7)
        with self.assertRaises(ConfigurationError):
            ensure_secrets(self.config, self.session(secrets), "other.rds.amazonaws.com")
        self.assertEqual(secrets.stored, before)

    def test_generated_passwords_need_no_escaping(self):
        values = new_values()
        for password in values["passwords"].values():
            self.assertRegex(password, r"^[0-9a-f]{48}$")
        self.assertGreaterEqual(len(values["internal_token"].encode()), 32)

    def test_init_task_matches_ecs_contract_and_keeps_master_in_secrets(self):
        master = "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds!db-1234-AbCdEf"
        definition = init_task(self.config, self.config["images"]["api"], master, ENDPOINT)
        model = botocore.session.get_session().get_service_model("ecs")
        validate_parameters(definition, model.operation_model("RegisterTaskDefinition").input_shape)
        container = definition["containerDefinitions"][0]
        self.assertNotIn("taskRoleArn", definition)
        self.assertEqual(
            {s["name"] for s in container["secrets"]}, {"MASTER_USER", "MASTER_PASSWORD", "MIGRATION_DB_PASSWORD"}
        )
        self.assertTrue(all(s["valueFrom"].startswith("arn:") for s in container["secrets"]))
        self.assertNotIn("PASSWORD", json.dumps(container["environment"]))
        compile(INIT_SCRIPT, "rds-init", "exec")
        self.assertIn('sslmode="verify-full"', INIT_SCRIPT)


if __name__ == "__main__":
    unittest.main()
