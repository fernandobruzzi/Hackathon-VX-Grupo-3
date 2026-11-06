"""Fila do CI em main (#108): medição e limites do cancelamento."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_queue_report import timing  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
REQUIRED_JOBS = ("style", "python", "database", "front", "images")


def job(start, end):
    return {"started_at": start, "completed_at": end}


class QueueTimingTests(unittest.TestCase):
    def test_queue_is_measured_until_the_first_job_starts(self):
        # Execução real 42202260418: criada 10:23:08, parada atrás da anterior até 10:27:33.
        run = {"id": 1, "head_sha": "2bfbe5eba918", "status": "completed", "conclusion": "success"}
        run["created_at"] = "2026-11-06T10:23:08Z"
        jobs = [
            job("2026-11-06T10:27:33Z", "2026-11-06T10:28:40Z"),
            job("2026-11-06T10:27:35Z", "2026-11-06T10:32:55Z"),
        ]
        result = timing(run, jobs)
        self.assertEqual((result.sha, result.queued_seconds, result.useful_seconds), ("2bfbe5e", 265, 322))

    def test_unfinished_run_has_no_useful_duration(self):
        run = {"id": 2, "head_sha": "03b1a14", "status": "queued", "conclusion": None}
        run["created_at"] = "2026-11-06T10:33:41Z"
        self.assertEqual(timing(run, []).queued_seconds, None)
        partial = timing(run, [job("2026-11-06T10:33:50Z", None)])
        self.assertEqual((partial.conclusion, partial.queued_seconds, partial.useful_seconds), ("queued", 9, None))


class WorkflowTests(unittest.TestCase):
    def test_superseded_runs_are_cancelled_per_pr_and_on_main(self):
        self.assertIn("group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}", CI)
        self.assertRegex(CI, r"(?m)^  cancel-in-progress: true$")

    def test_required_check_names_stay(self):
        for name in REQUIRED_JOBS:
            self.assertRegex(CI, rf"(?m)^  {name}:$")
        self.assertIn("module: [back, mcp, api]", CI)

    def test_cancellable_workflow_never_deploys_or_migrates_outside_the_runner(self):
        # Cancelar no meio de um deploy deixaria lock e revisão pela metade.
        for command in ("deploy_ecs", "deploy_ec2", "bootstrap_aws", "--apply", "aws ", "secrets."):
            self.assertNotIn(command, CI)
        migrations = re.findall(r"MIGRATION_DATABASE_URL: (\S+)", CI)
        self.assertTrue(migrations)
        self.assertTrue(all("@localhost:5432/" in url for url in migrations))


if __name__ == "__main__":
    unittest.main()
