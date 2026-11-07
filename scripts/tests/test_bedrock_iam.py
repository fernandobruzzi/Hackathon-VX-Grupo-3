"""Permissões offline do perfil Sonnet 5 do Agent e isolamento do batch."""

import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_support import load_config, task_definitions  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROFILE_ARN = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-5"
TITAN_ARN = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
SONNET_ARNS = (
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-5",
    "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-5",
    "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-5",
)


class CloudFormationLoader(yaml.SafeLoader):
    pass


def construct_intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {"Ref" if tag == "Ref" else f"Fn::{tag}": value}


CloudFormationLoader.add_multi_constructor("!", construct_intrinsic)


def resolve(value, config):
    references = {"AWS::Region": config["region"], "AWS::AccountId": config["account_id"]}
    if isinstance(value, dict):
        if "Fn::Sub" in value:
            return re.sub(r"\$\{([^}]+)\}", lambda match: references[match[1]], value["Fn::Sub"])
        if "Ref" in value:
            return references[value["Ref"]]
        return {key: resolve(item, config) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, config) for item in value]
    return value


def as_list(value):
    return value if isinstance(value, list) else [value]


@pytest.fixture
def deployment():
    config = load_config(ROOT / "deployment" / "aws.example.json")
    template = yaml.load((ROOT / "deployment" / "infra.yaml").read_text(), Loader=CloudFormationLoader)
    return config, template


def invocation_grants(deployment, role):
    config, template = deployment
    grants = []
    for policy in template["Resources"][role]["Properties"]["Policies"]:
        for statement in as_list(policy["PolicyDocument"]["Statement"]):
            actions = as_list(statement["Action"])
            if any(
                action.lower().startswith("bedrock:invoke") or fnmatchcase("bedrock:invokemodel", action.lower())
                for action in actions
            ):
                assert statement["Effect"] == "Allow"
                assert actions == ["bedrock:InvokeModel"]
                grants.append(resolve(statement, config))
    return grants


def test_agent_web_role_allows_its_selected_chat_profile(deployment):
    config, _ = deployment
    web = task_definitions(config)["web"]
    agent = next(container for container in web["containerDefinitions"] if container["name"] == "Agent")
    environment = {item["name"]: item["value"] for item in agent["environment"]}
    profile = (
        f"arn:aws:bedrock:{environment['AWS_REGION']}:{config['account_id']}:"
        f"inference-profile/{environment['BEDROCK_CHAT_MODEL_ID']}"
    )
    assert web["taskRoleArn"] == config["roles"]["web"]
    assert profile == PROFILE_ARN
    assert any(
        profile in as_list(grant["Resource"]) and not grant.get("Condition")
        for grant in invocation_grants(deployment, "WebTaskRole")
    ), f"WebTaskRole cannot invoke selected chat profile {profile}"


@pytest.mark.parametrize("model_arn", SONNET_ARNS)
def test_web_role_allows_sonnet_destinations_only_through_source_profile(deployment, model_arn):
    grants = [
        grant for grant in invocation_grants(deployment, "WebTaskRole") if model_arn in as_list(grant["Resource"])
    ]
    assert grants, f"WebTaskRole cannot invoke profile destination {model_arn}"
    assert all(
        grant.get("Condition") == {"StringEquals": {"bedrock:InferenceProfileArn": PROFILE_ARN}} for grant in grants
    )


def test_web_role_keeps_model_access_limited_to_titan_and_sonnet_profile(deployment):
    grants = invocation_grants(deployment, "WebTaskRole")
    resources = {resource for grant in grants for resource in as_list(grant["Resource"])}
    assert resources == {TITAN_ARN, PROFILE_ARN, *SONNET_ARNS}
    titan = [grant for grant in grants if TITAN_ARN in as_list(grant["Resource"])]
    assert all(not grant.get("Condition") for grant in titan)


def test_batch_role_retains_titan_without_chat_permissions(deployment):
    assert invocation_grants(deployment, "BatchTaskRole") == [
        {"Effect": "Allow", "Action": "bedrock:InvokeModel", "Resource": TITAN_ARN}
    ]
