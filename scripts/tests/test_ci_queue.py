"""CI de promoção (#178): gatilhos, medição e limites do cancelamento."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_queue_report import timing  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
DATABASE_TESTS = (ROOT / ".github" / "workflows" / "database-tests.yml").read_text(encoding="utf-8")
REQUIRED_JOBS = ("style", "python", "database", "front", "images")
DATABASE_JOBS = ("database-api-demo", "database-api-batch", "database-api-main", "database-mcp")


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
    def test_complete_ci_requires_the_same_repository_promotion(self):
        guard = (
            "${{ github.event.pull_request.head.ref == 'homologacao' && "
            "github.event.pull_request.head.repo.full_name == github.repository }}"
        )
        for name in (*REQUIRED_JOBS, *DATABASE_JOBS):
            with self.subTest(job=name):
                expected = guard.replace("${{ ", "${{ always() && ") if name == "database" else guard
                self.assertIn(f"  {name}:\n    if: {expected}\n", CI)

    def test_required_database_check_requires_all_suites(self):
        job = CI.split("\n  database:\n", 1)[1].split("\n  front:\n", 1)[0]
        self.assertIn(f"needs: [{', '.join(DATABASE_JOBS)}]", job)
        self.assertIn("join(needs.*.result, ' ')", job)
        self.assertIn('test "$RESULTS" = "success success success success"', job)

    def test_isolated_images_run_both_smokes_and_reset_before_the_full_flow(self):
        self.assertIn("COMPOSE_PROJECT_NAME: vx-ci-${{ github.run_id }}-${{ github.run_attempt }}", CI)
        for service in ("api", "migrate", "bootstrap", "demo", "agent", "batch", "index"):
            self.assertIn("${{ env.COMPOSE_PROJECT_NAME }}-" + service + ":latest", CI)
        local = CI.index("scripts/smoke_test.sh http://127.0.0.1:18000 --mode local")
        reset = CI.index("docker compose --profile demo run --rm --no-deps --pull never demo reset")
        flow = CI.index("scripts/smoke_test.sh http://127.0.0.1:18000 --mode flow")
        self.assertLess(local, reset)
        self.assertLess(reset, flow)
        self.assertIn('DEMO_MODE: "true"', CI)
        self.assertIn("if: failure() || cancelled()", CI)
        self.assertIn("if: always()", CI)
        self.assertNotRegex(CI, r"docker compose[^\n]*run[^\n]*--no-build")

    def test_validation_only_runs_for_pull_requests_targeting_main(self):
        for filename in ("ci.yml", "policy.yml"):
            with self.subTest(workflow=filename):
                workflow = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
                triggers = re.search(r"(?ms)^on:\n(.*?)(?=^\S)", workflow).group(1)
                self.assertEqual(re.findall(r"(?m)^  (\w+):", triggers), ["pull_request"])
                self.assertRegex(triggers, r"(?m)^    branches: \[main\]$")
                self.assertIn("edited", triggers)  # Retargetar um PR para main também precisa validar.
                self.assertNotIn("paths", triggers)  # Checks obrigatórios não podem ficar pendentes por filtro.

    def test_superseded_runs_are_cancelled_per_promotion_pr(self):
        self.assertIn("group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}", CI)
        self.assertRegex(CI, r"(?m)^  cancel-in-progress: true$")

    def test_required_check_names_stay(self):
        for name in REQUIRED_JOBS:
            self.assertRegex(CI, rf"(?m)^  {name}:$")
        self.assertIn("module: [back, mcp, api]", CI)

    def test_cancellable_workflow_never_deploys_or_migrates_outside_the_runner(self):
        # Cancelar no meio de um deploy deixaria lock e revisão pela metade.
        for command in ("deploy_ecs", "deploy_ec2", "bootstrap_aws", "--apply", "aws ", "secrets."):
            self.assertNotIn(command, CI + DATABASE_TESTS)
        migrations = re.findall(r"MIGRATION_DATABASE_URL: (\S+)", CI + DATABASE_TESTS)
        self.assertTrue(migrations)
        self.assertTrue(all("@localhost:5432/" in url for url in migrations))


if __name__ == "__main__":
    unittest.main()
