"""RunTask: idempotência por tentativa, contrato AWS e ausência de credenciais no override."""

import uuid
from unittest.mock import Mock

import botocore.session
import pytest
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

from vx_materials_api.services.batch_runner import LaunchRequest
from vx_materials_api.services.ecs_batch_runner import EcsFargateRunner


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setenv("ECS_CLUSTER", "vx")
    monkeypatch.setenv("ECS_BATCH_TASK_DEFINITION", "arn:aws:ecs:us-east-1:123456789012:task-definition/vx-batch:3")
    monkeypatch.setenv("ECS_SUBNET_IDS", "subnet-0123456789abcdef0")
    monkeypatch.setenv("ECS_SECURITY_GROUP_IDS", "sg-0123456789abcdef0")
    monkeypatch.setenv("DATABASE_URL", "api-secret-must-not-travel")
    monkeypatch.setenv("AGENT_INTERNAL_TOKEN_SECRET", "internal-secret-must-not-travel")
    client = Mock()
    client.run_task.return_value = {"tasks": [{"taskArn": "arn:task"}]}
    return EcsFargateRunner(client=client)


def request(attempt="first"):
    job_id = "11111111-1111-4111-8111-111111111111"
    return LaunchRequest(job_id, f"runs/{job_id}/manifest.json", attempt)


def test_real_aws_schema_and_manifest_only_override(runner):
    assert runner.launch(request()) == "arn:task"
    params = runner.client.run_task.call_args.kwargs
    model = botocore.session.get_session().get_service_model("ecs")
    validate_parameters(params, model.operation_model("RunTask").input_shape)
    overrides = params["overrides"]["containerOverrides"]
    assert overrides == [
        {
            "name": "Batch",
            "command": [
                "vx-back",
                "sanitize",
                "--job-id",
                request().job_id,
                "--manifest-key",
                request().manifest_key,
            ],
        }
    ]
    assert "secret" not in str(params)
    assert params["taskDefinition"].endswith(":3")


def test_retry_is_idempotent_but_resume_gets_another_task(runner):
    runner.launch(request())
    first = runner.client.run_task.call_args.kwargs["clientToken"]
    runner.launch(request())
    assert runner.client.run_task.call_args.kwargs["clientToken"] == first
    runner.launch(request("resumed"))
    assert runner.client.run_task.call_args.kwargs["clientToken"] != first


def test_wrong_manifest_refused_before_aws_call(runner):
    with pytest.raises(RuntimeError, match="Manifesto"):
        runner.launch(LaunchRequest(str(uuid.uuid4()), request().manifest_key))
    runner.client.run_task.assert_not_called()


@pytest.mark.parametrize("response", [{"tasks": [], "failures": [{"reason": "capacity"}]}, {"tasks": []}])
def test_ecs_unconfirmed_launch_is_failure(runner, response):
    runner.client.run_task.return_value = response
    with pytest.raises(RuntimeError, match="ECS_BATCH_LAUNCH_FAILED"):
        runner.launch(request())


def test_sdk_error_does_not_expose_values_in_persisted_error(runner):
    runner.client.run_task.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private-value"}}, "RunTask"
    )
    with pytest.raises(RuntimeError) as caught:
        runner.launch(request())
    assert "private-value" not in str(caught.value)


def test_definition_must_pin_revision(runner, monkeypatch):
    monkeypatch.setenv("ECS_BATCH_TASK_DEFINITION", "vx-batch")
    with pytest.raises(RuntimeError, match="revisão fixa"):
        EcsFargateRunner(client=Mock())
