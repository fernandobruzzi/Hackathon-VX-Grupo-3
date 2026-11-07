"""Regressões offline: contratos ECS, isolamento de segredos e falhas de implantação."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import botocore.session
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters
from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_deploy import deploy, deployment_lock, one_off, register, validate_secrets, wait_for_service  # noqa: E402
from aws_preflight import Report, preflight  # noqa: E402
from aws_support import ConfigurationError, canonical_task, load_config, render, task_definitions  # noqa: E402


def boto3_client_can_paginate(operation):
    return botocore.session.get_session().create_client("ecs", region_name="us-east-1").can_paginate(operation)


EXAMPLE = Path(__file__).resolve().parents[2] / "deployment" / "aws.example.json"


class AwsTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(EXAMPLE)

    def config_file(self, value):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.json"
        path.write_text(json.dumps(value))
        return path

    def test_rejects_wrong_account_region_mutable_images_and_literal_secrets(self):
        for section, key, value in (
            ("roles", "web", "arn:aws:iam::999999999999:role/wrong"),
            ("images", "api", self.config["images"]["api"].split("@")[0] + ":latest"),
            ("images", "api", self.config["images"]["api"].replace("us-east-1", "us-west-2")),
            ("secrets", "api_database", "postgresql://secret-password@db/catalog"),
            ("secrets", "api_database", self.config["secrets"]["api_database"] + ":key::"),
        ):
            with self.subTest(section=section, key=key, value=value):
                config = copy.deepcopy(self.config)
                config[section][key] = value
                with self.assertRaises(ConfigurationError):
                    load_config(self.config_file(config))

    def test_unknown_config_and_invalid_architecture_fail(self):
        for key, value in (("APP_ENV", "local"), ("architecture", "arm")):
            config = copy.deepcopy(self.config)
            config[key] = value
            with self.assertRaises(ConfigurationError):
                load_config(self.config_file(config))

    def test_all_task_definitions_match_real_ecs_sdk_schema(self):
        model = botocore.session.get_session().get_service_model("ecs")
        for definition in task_definitions(self.config).values():
            validate_parameters(definition, model.operation_model("RegisterTaskDefinition").input_shape)
        validate_parameters(
            {
                "cluster": self.config["cluster"],
                "serviceName": self.config["name"],
                "infrastructureRoleArn": self.config["roles"]["infrastructure"],
                "taskDefinitionArn": "arn:aws:ecs:us-east-1:123456789012:task-definition/vx-web:1",
                "networkConfiguration": {
                    "subnets": self.config["subnets"],
                    "securityGroups": self.config["security_groups"],
                },
                "healthCheckPath": "/api/v1/healthz",
                "scalingTarget": {"minTaskCount": 1, "maxTaskCount": 1},
            },
            model.operation_model("CreateExpressGatewayService").input_shape,
        )

    def test_web_secrets_exclude_migration_passwords_and_agent_is_internal(self):
        definitions = task_definitions(self.config)
        main, agent = definitions["web"]["containerDefinitions"]
        self.assertEqual(main["name"], "Main")
        self.assertEqual(main["portMappings"][0]["name"], "http")
        self.assertNotIn("portMappings", agent)
        self.assertEqual(main["dependsOn"], [{"containerName": "Agent", "condition": "HEALTHY"}])
        for container in (main, agent):
            env = {e["name"]: e["value"] for e in container["environment"]}
            self.assertEqual(env["APP_ENV"], "production")
            self.assertEqual(env["LOCAL_TEST_SESSION"], "false")
            self.assertTrue(container["linuxParameters"]["initProcessEnabled"])
            self.assertNotIn(self.config["secrets"]["migration_database"], json.dumps(container))
            self.assertNotIn("API_DB_PASSWORD", json.dumps(container))
        self.assertEqual(definitions["batch"]["taskRoleArn"], self.config["roles"]["batch"])

    def test_render_and_config_loading_do_not_create_aws_session(self):
        with tempfile.TemporaryDirectory() as directory, patch("boto3.Session", side_effect=AssertionError("network")):
            render(load_config(EXAMPLE), directory)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 5)

    def test_register_reuses_revision_but_detects_image_or_secret_drift(self):
        desired = task_definitions(self.config)["web"]
        actual = copy.deepcopy(desired)
        actual.update(status="ACTIVE", taskDefinitionArn="arn:old", revision=1)
        actual["containerDefinitions"][0]["cpu"] = 0
        self.assertTrue(canonical_task(actual, desired))
        ecs = Mock()
        ecs.describe_task_definition.return_value = {"taskDefinition": actual}
        self.assertEqual(register(ecs, desired), "arn:old")
        ecs.register_task_definition.assert_not_called()
        actual["containerDefinitions"][0]["secrets"][0]["valueFrom"] = "arn:changed"
        ecs.register_task_definition.return_value = {"taskDefinition": {"taskDefinitionArn": "arn:new"}}
        self.assertEqual(register(ecs, desired), "arn:new")

    def test_one_off_checks_failure_and_uses_stable_client_token(self):
        ecs = Mock()
        ecs.run_task.return_value = {"tasks": [{"taskArn": "arn:task"}]}
        ecs.describe_tasks.return_value = {"tasks": [{"containers": [{"exitCode": 0}]}]}
        with redirect_stdout(io.StringIO()):
            one_off(ecs, self.config, "arn:definition", "release1", "migrate")
            first = ecs.run_task.call_args.kwargs
            one_off(ecs, self.config, "arn:definition", "release1", "migrate")
        self.assertEqual(first["clientToken"], ecs.run_task.call_args.kwargs["clientToken"])
        self.assertEqual(first["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"], "ENABLED")
        ecs.describe_tasks.return_value = {"tasks": [{"containers": [{"exitCode": 1}]}]}
        with redirect_stdout(io.StringIO()), self.assertRaises(ConfigurationError):
            one_off(ecs, self.config, "arn:definition", "release2", "migrate")
        ecs.run_task.return_value = {"tasks": [], "failures": [{"reason": "capacity"}]}
        with self.assertRaises(ConfigurationError):
            one_off(ecs, self.config, "arn:definition", "release3", "migrate")

    def test_lock_releases_only_its_version_on_success_and_preserves_failures(self):
        session = Mock()
        s3 = session.client.return_value
        s3.put_object.return_value = {"VersionId": "our-version"}
        with deployment_lock(self.config, session, "release"):
            pass
        self.assertEqual(s3.put_object.call_args.kwargs["IfNoneMatch"], "*")
        self.assertEqual(s3.delete_object.call_args.kwargs["VersionId"], "our-version")
        s3.delete_object.reset_mock()
        with self.assertRaises(RuntimeError), deployment_lock(self.config, session, "failed-release"):
            raise RuntimeError("task outcome uncertain")
        s3.delete_object.assert_not_called()
        s3.put_object.side_effect = ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        s3.delete_object.reset_mock()
        with self.assertRaises(ClientError), deployment_lock(self.config, session, "release2"):
            self.fail("Não pode obter lock ocupado")
        s3.delete_object.assert_not_called()

    def test_cognito_requires_https_and_keeps_session_secret_only_on_api(self):
        config = copy.deepcopy(self.config)
        config["auth_backend"] = "cognito"
        with self.assertRaises(ConfigurationError):
            load_config(self.config_file(config))
        config.update(
            public_origin="https://example.com",
            cognito_domain="https://login.example.com",
            cognito_user_pool_id="us-east-1_pool",
            cognito_app_client_id="app",
        )
        main, agent = task_definitions(load_config(self.config_file(config)))["web"]["containerDefinitions"]
        self.assertIn("SESSION_ENCRYPTION_KEY", {s["name"] for s in main["secrets"]})
        self.assertNotIn("SESSION_ENCRYPTION_KEY", {s["name"] for s in agent["secrets"]})
        config["public_origin"] = "http://public.example.com"
        with self.assertRaises(ConfigurationError):
            load_config(self.config_file(config))

    def test_web_runner_uses_registered_batch_revision(self):
        arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/vx-batch:7"
        main = task_definitions(self.config, arn)["web"]["containerDefinitions"][0]
        env = {e["name"]: e["value"] for e in main["environment"]}
        self.assertEqual(env["ECS_BATCH_TASK_DEFINITION"], arn)
        self.assertEqual(env["BATCH_RUNNER"], "ecs_fargate")
        self.assertNotIn("BATCH_DATABASE_URL", env)

    def test_deploy_waits_for_new_revision_instead_of_accepting_old_healthy_service(self):
        ecs, ecr = Mock(), Mock()
        web_arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/vx-grupo3-web:1"
        ecs.describe_services.side_effect = [
            {"services": []},
            {
                "services": [
                    {
                        "runningCount": 1,
                        "pendingCount": 0,
                        "currentServiceRevisions": [{"arn": "new", "runningTaskCount": 1}],
                    }
                ]
            },
        ]
        ecs.can_paginate.return_value = False
        ecs.list_service_deployments.side_effect = [
            {"serviceDeployments": [{"targetServiceRevisionArn": "old", "status": "SUCCESSFUL"}]},
            {"serviceDeployments": [], "nextToken": "page-2"},
            {"serviceDeployments": [{"targetServiceRevisionArn": "new", "status": "SUCCESSFUL"}]},
        ]
        ecs.describe_service_revisions.side_effect = [
            {"serviceRevisions": [{"serviceRevisionArn": "old", "taskDefinition": "arn:old"}]},
            {"serviceRevisions": [{"serviceRevisionArn": "new", "taskDefinition": web_arn}]},
        ]
        ecs.create_express_gateway_service.return_value = {"service": {"serviceArn": "arn:service"}}
        ecs.describe_express_gateway_service.return_value = {
            "service": {
                "activeConfigurations": [
                    {
                        "taskDefinitionArn": web_arn,
                        "ingressPaths": [{"accessType": "PUBLIC", "endpoint": "https://example.com"}],
                    }
                ]
            }
        }
        response = io.BytesIO(b'{"status":"ok"}')
        response.status = 200
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("aws_deploy.client", side_effect=lambda session, name: ecs if name == "ecs" else ecr),
            patch("aws_deploy.validate_secrets"),
            patch("aws_deploy.deployment_lock", return_value=nullcontext()),
            patch(
                "aws_deploy.register",
                side_effect=lambda client, d: f"arn:aws:ecs:us-east-1:123456789012:task-definition/{d['family']}:1",
            ),
            patch("aws_deploy.one_off", return_value="arn:task") as run,
            patch("aws_deploy.time.sleep") as sleep,
            patch("aws_deploy.urlopen", return_value=response),
            redirect_stdout(io.StringIO()),
        ):
            receipt = Path(directory) / "receipt.json"
            deploy(self.config, Mock(), "release", receipt)
            self.assertEqual([c.args[-1] for c in run.call_args_list], ["migrate", "bootstrap", "index"])
            sleep.assert_called_once_with(10)
            ecs.get_paginator.assert_not_called()
            self.assertEqual(ecs.list_service_deployments.call_args_list[2].kwargs.get("nextToken"), "page-2")
            self.assertEqual(json.loads(receipt.read_text())["public_origin"], "https://example.com")

    def test_redeploy_reads_previous_revision_from_express_not_describe_services(self):
        ecs, ecr = Mock(), Mock()
        web_arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/vx-grupo3-web:2"
        existing = {"serviceArn": "arn:service", "status": "ACTIVE", "runningCount": 1, "pendingCount": 0}
        ecs.describe_services.side_effect = [
            {"services": [existing]},
            {"services": [{**existing, "currentServiceRevisions": [{"arn": "new", "runningTaskCount": 1}]}]},
        ]
        ecs.list_service_deployments.return_value = {
            "serviceDeployments": [{"targetServiceRevisionArn": "new", "status": "SUCCESSFUL"}]
        }
        ecs.describe_service_revisions.return_value = {
            "serviceRevisions": [{"serviceRevisionArn": "new", "taskDefinition": web_arn}]
        }
        ecs.update_express_gateway_service.return_value = {"service": {"serviceArn": "arn:service"}}
        ecs.describe_express_gateway_service.side_effect = [
            {
                "service": {
                    "infrastructureRoleArn": self.config["roles"]["infrastructure"],
                    "activeConfigurations": [{"taskDefinitionArn": "arn:previous"}],
                }
            },
            {
                "service": {
                    "activeConfigurations": [
                        {
                            "taskDefinitionArn": web_arn,
                            "ingressPaths": [{"accessType": "PUBLIC", "endpoint": "https://example.com"}],
                        }
                    ]
                }
            },
        ]
        response = io.BytesIO(b'{"status":"ok"}')
        response.status = 200
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("aws_deploy.client", side_effect=lambda session, name: ecs if name == "ecs" else ecr),
            patch("aws_deploy.validate_secrets"),
            patch("aws_deploy.deployment_lock", return_value=nullcontext()),
            patch(
                "aws_deploy.register",
                side_effect=lambda client, d: f"arn:aws:ecs:us-east-1:123456789012:task-definition/{d['family']}:2",
            ),
            patch("aws_deploy.one_off", return_value="arn:task"),
            patch("aws_deploy.time.sleep"),
            patch("aws_deploy.urlopen", return_value=response),
            redirect_stdout(io.StringIO()),
        ):
            receipt = Path(directory) / "receipt.json"
            deploy(self.config, Mock(), "release", receipt)
            self.assertEqual(json.loads(receipt.read_text())["previous_task_definition"], "arn:previous")
            ecs.create_express_gateway_service.assert_not_called()

    def test_service_deployments_follow_next_token_of_the_real_api(self):
        model = botocore.session.get_session().get_service_model("ecs")
        operation = model.operation_model("ListServiceDeployments")
        self.assertIn("nextToken", operation.input_shape.members)
        self.assertIn("nextToken", operation.output_shape.members)
        self.assertFalse(boto3_client_can_paginate("list_service_deployments"))

    def test_canary_rollback_is_failure_even_if_old_service_is_healthy(self):
        ecs = Mock()
        ecs.list_service_deployments.return_value = {
            "serviceDeployments": [{"targetServiceRevisionArn": "new", "status": "ROLLBACK_SUCCESSFUL"}]
        }
        ecs.describe_service_revisions.return_value = {
            "serviceRevisions": [
                {
                    "serviceRevisionArn": "new",
                    "taskDefinition": "arn:new",
                }
            ]
        }
        with self.assertRaises(ConfigurationError, msg="rollback não é sucesso de deploy"):
            wait_for_service(ecs, self.config, "arn:service", "arn:new")
        ecs.describe_services.assert_not_called()

    def test_report_never_prints_aws_exception_message(self):
        report = Report()

        def deny():
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "sensitive-password"}}, "Read")

        report.check("test", deny)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(report.finish(), 1)
        self.assertNotIn("sensitive-password", output.getvalue())
        self.assertIn("DENIED", output.getvalue())

    def test_wrong_account_stops_preflight_before_resource_access(self):
        session = Mock()
        session.client.return_value.get_caller_identity.return_value = {"Account": "999999999999"}
        with self.assertRaises(ConfigurationError):
            preflight(self.config, session)
        self.assertEqual([call.args[0] for call in session.client.call_args_list], ["sts"])

    def test_database_secrets_preserve_special_passwords_and_require_verified_tls(self):
        session = Mock()
        clients = {name: Mock() for name in ("secretsmanager", "rds")}
        session.client.side_effect = lambda service, **kwargs: clients[service]
        password = "p@ss/word:%?#'with-symbols"
        values = {
            "internal_token": "s" * 32,
            "database_passwords": json.dumps(
                dict.fromkeys(("API_DB_PASSWORD", "BATCH_DB_PASSWORD", "MCP_DB_PASSWORD"), password)
            ),
        }
        for key, role in (
            ("api_database", "api_user"),
            ("agent_database", "mcp_reader"),
            ("batch_database", "batch_user"),
            ("migration_database", "migration_user"),
        ):
            values[key] = URL.create(
                "postgresql+psycopg",
                username=role,
                password=password,
                host="db.rds.example",
                database="vx_materiais",
                query={"sslmode": "verify-full", "sslrootcert": "/app/certs/rds-global-bundle.pem"},
            ).render_as_string(hide_password=False)
        inverse = {arn: key for key, arn in self.config["secrets"].items()}
        clients["secretsmanager"].get_secret_value.side_effect = lambda SecretId: {
            "SecretString": values[inverse[SecretId]]
        }
        clients["rds"].describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "PubliclyAccessible": False,
                    "Engine": "postgres",
                    "DBInstanceStatus": "available",
                    "Endpoint": {"Address": "db.rds.example"},
                }
            ]
        }
        validate_secrets(self.config, session)
        values["api_database"] = values["api_database"].replace("sslmode=verify-full", "sslmode=require")
        with self.assertRaises(ConfigurationError):
            validate_secrets(self.config, session)


if __name__ == "__main__":
    unittest.main()
