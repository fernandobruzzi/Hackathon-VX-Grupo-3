"""Regressões offline das contas fictícias do Cognito: nada consulta a AWS."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aws_demo_accounts import GROUPS, PERSONAS, ensure_accounts, new_password  # noqa: E402
from aws_support import load_config  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[2] / "deployment" / "aws.example.json"


def error(code):
    return ClientError({"Error": {"Code": code}}, "Operation")


class DemoAccountTests(unittest.TestCase):
    def setUp(self):
        self.config = {**load_config(EXAMPLE), "cognito_user_pool_id": "us-east-1_pool"}

    def session(self, stored=None, groups=None):
        secrets, cognito = Mock(), Mock()
        if stored is None:
            secrets.get_secret_value.side_effect = error("ResourceNotFoundException")
        else:
            secrets.get_secret_value.return_value = {"SecretString": json.dumps(stored)}
        cognito.admin_list_groups_for_user.side_effect = lambda UserPoolId, Username: {
            "Groups": [{"GroupName": g} for g in (groups or {}).get(Username, [])]
        }
        session = Mock()
        session.client.side_effect = lambda service, **kwargs: {"secretsmanager": secrets, "cognito-idp": cognito}[
            service
        ]
        return session, secrets, cognito

    def test_personas_cover_each_role_once_with_unroutable_emails(self):
        self.assertEqual(len(PERSONAS), 3)
        self.assertEqual(GROUPS, {"ROLE_SOLICITANTE", "ROLE_GOVERNANCA_PDM", "ROLE_AUDITOR_FISCAL"})
        self.assertTrue(all(email.endswith(".example.com") for email, _, _ in PERSONAS))

    def test_first_run_stores_passwords_without_printing_them(self):
        session, secrets, cognito = self.session()
        output = io.StringIO()
        with redirect_stdout(output):
            ensure_accounts(self.config, session)
        stored = json.loads(secrets.create_secret.call_args.kwargs["SecretString"])
        self.assertEqual(set(stored), {email for email, _, _ in PERSONAS})
        for password in stored.values():
            self.assertNotIn(password, output.getvalue())
        for call in cognito.admin_create_user.call_args_list:
            self.assertEqual(call.kwargs["MessageAction"], "SUPPRESS")
        self.assertEqual(cognito.admin_set_user_password.call_count, 3)
        self.assertTrue(all(c.kwargs["Permanent"] for c in cognito.admin_set_user_password.call_args_list))
        added = {(c.kwargs["Username"], c.kwargs["GroupName"]) for c in cognito.admin_add_user_to_group.call_args_list}
        self.assertEqual(added, {(email, group) for email, _, group in PERSONAS})

    def test_rerun_keeps_passwords_and_removes_wrong_groups(self):
        email, _, group = PERSONAS[0]
        stored = {e: "Existing1Password" for e, _, _ in PERSONAS}
        session, secrets, cognito = self.session(stored, {email: [group, "ROLE_AUDITOR_FISCAL"]})
        cognito.admin_create_user.side_effect = error("UsernameExistsException")
        with redirect_stdout(io.StringIO()):
            ensure_accounts(self.config, session)
        secrets.create_secret.assert_not_called()
        cognito.admin_set_user_password.assert_not_called()
        cognito.admin_remove_user_from_group.assert_called_once_with(
            UserPoolId="us-east-1_pool", Username=email, GroupName="ROLE_AUDITOR_FISCAL"
        )

    def test_passwords_meet_pool_policy(self):
        for _ in range(50):
            value = new_password()
            self.assertGreaterEqual(len(value), 12)
            self.assertTrue(any(c.isupper() for c in value) and any(c.islower() for c in value))
            self.assertTrue(any(c.isdigit() for c in value))


if __name__ == "__main__":
    unittest.main()
