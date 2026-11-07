"""Garantias do deploy automático: só main publica, nada é cancelado no meio e a
configuração do workflow passa pelas mesmas validações do deploy manual."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_ci_config import render  # noqa: E402
from aws_support import ConfigurationError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
EXAMPLE = ROOT / "deployment" / "aws.example.json"
DIGEST = "sha256:" + "a" * 64
REGISTRY = "123456789012.dkr.ecr.us-east-1.amazonaws.com"


class DeployWorkflowTests(unittest.TestCase):
    def test_runs_only_on_main_pushes_and_manual_dispatch(self):
        triggers = re.search(r"(?ms)^on:\n(.*?)(?=^\S)", WORKFLOW).group(1)
        self.assertEqual(re.findall(r"(?m)^  (\w+):", triggers), ["push", "workflow_dispatch"])
        self.assertRegex(triggers, r"(?m)^    branches: \[main\]$")
        self.assertNotIn("pull_request", WORKFLOW)
        self.assertIn("if: github.ref == 'refs/heads/main'", WORKFLOW)

    def test_a_running_deploy_is_never_cancelled(self):
        self.assertRegex(WORKFLOW, r"(?m)^  group: deploy-production$")
        self.assertRegex(WORKFLOW, r"(?m)^  cancel-in-progress: false$")

    def test_uses_short_lived_oidc_credentials_only(self):
        self.assertRegex(WORKFLOW, r"(?m)^  id-token: write$")
        self.assertRegex(WORKFLOW, r"(?m)^  contents: read$")
        self.assertIn("role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)
        self.assertNotIn("aws-access-key-id", WORKFLOW)

    def test_builds_x86_images_and_deploys_by_digest(self):
        self.assertEqual(WORKFLOW.count("platforms: linux/amd64"), 3)
        for target in ("api", "agent", "batch"):
            self.assertIn(f"@${{{{ steps.{target}.outputs.digest }}}}", WORKFLOW)
        self.assertIn('--release "$RELEASE"', WORKFLOW)
        self.assertIn("github.run_attempt", WORKFLOW)

    def test_canary_reads_only_the_projects_ecs_service(self):
        template = yaml.load((ROOT / "deployment" / "infra.yaml").read_text(), Loader=yaml.BaseLoader)
        role = template["Resources"]["GitHubDeployRole"]["Properties"]
        service = "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:service/${Name}/${Name}"
        revision = "arn:aws:ecs:${AWS::Region}:${AWS::AccountId}:service-revision/${Name}/${Name}/*"
        expected = {
            "ecs:ListServiceDeployments": {service},
            "ecs:DescribeServiceRevisions": {service, revision},
        }
        grants = {action: set() for action in expected}
        for policy in role["Policies"]:
            for statement in policy["PolicyDocument"]["Statement"]:
                actions = statement["Action"]
                resources = statement["Resource"]
                for action in [actions] if isinstance(actions, str) else actions:
                    if action in grants:
                        grants[action].update([resources] if isinstance(resources, str) else resources)
        self.assertEqual(grants, expected)

    def test_oidc_trust_accepts_the_immutable_repository_subject_for_main(self):
        template = yaml.load((ROOT / "deployment" / "infra.yaml").read_text(), Loader=yaml.BaseLoader)
        repository_pattern = template["Parameters"]["GitHubRepository"]["AllowedPattern"]
        for repository in ("", "owner/repo", "owner@123456/repo@456789"):
            with self.subTest(repository=repository):
                self.assertIsNotNone(re.fullmatch(repository_pattern, repository))
        for repository in ("owner@123456/repo", "owner/repo@456789", "owner/*", "owner/repo:pull_request"):
            with self.subTest(repository=repository):
                self.assertIsNone(re.fullmatch(repository_pattern, repository))

        role = template["Resources"]["GitHubDeployRole"]["Properties"]
        (trust,) = role["AssumeRolePolicyDocument"]["Statement"]
        self.assertEqual(trust["Principal"], {"Federated": "GitHubOidcProvider"})
        self.assertEqual(trust["Action"], "sts:AssumeRoleWithWebIdentity")
        self.assertEqual(
            trust["Condition"],
            {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    "token.actions.githubusercontent.com:sub": "repo:${GitHubRepository}:ref:refs/heads/main",
                }
            },
        )

    def config(self):
        return json.loads(EXAMPLE.read_text())

    def images(self):
        return {t: f"{REGISTRY}/vx-grupo3-{t}@{DIGEST}" for t in ("api", "agent", "batch")}

    def test_render_replaces_images_and_architecture_and_validates(self):
        source = {**self.config(), "architecture": "ARM64"}
        with tempfile.TemporaryDirectory() as directory:
            config = render(json.dumps(source), self.images(), Path(directory) / "aws.ci.json")
        self.assertEqual(config["architecture"], "X86_64")
        self.assertEqual(config["images"], self.images())
        self.assertEqual(config["secrets"], source["secrets"])

    def test_render_refuses_missing_config_tags_and_foreign_registries(self):
        cases = [
            (None, self.images()),
            ("{", self.images()),
            (json.dumps(self.config()), {**self.images(), "api": f"{REGISTRY}/vx-grupo3-api:latest"}),
            (
                json.dumps(self.config()),
                {**self.images(), "agent": f"999999999999.dkr.ecr.us-east-1.amazonaws.com/x@{DIGEST}"},
            ),
            (json.dumps(self.config()), {"api": self.images()["api"]}),
        ]
        for raw, images in cases:
            with self.subTest(images=images), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ConfigurationError):
                    render(raw, images, Path(directory) / "aws.ci.json")


if __name__ == "__main__":
    unittest.main()
