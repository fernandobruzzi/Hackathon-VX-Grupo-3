"""CI de promoção (#178): gatilhos, medição e limites do cancelamento."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_pytest import SHARDS  # noqa: E402
from ci_queue_report import timing  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
DATABASE_TESTS = (ROOT / ".github" / "workflows" / "database-tests.yml").read_text(encoding="utf-8")
PROMOTION_JOBS = ("python", "python-back", "database", "front", "images")
BACK_TESTS = (ROOT / ".github" / "workflows" / "back-tests.yml").read_text(encoding="utf-8")
BACK_JOBS = tuple(f"back-{shard}" for shard in ("main", *SHARDS["back"]))
DATABASE_JOBS = tuple(f"database-{module}-{shard}" for module in ("api", "mcp") for shard in ("main", *SHARDS[module]))


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
    def test_complete_ci_requires_a_promotion_or_a_manual_run_on_homologacao(self):
        guard = (
            "github.base_ref == 'main' && github.event.pull_request.head.ref == 'homologacao' && "
            "github.event.pull_request.head.repo.full_name == github.repository"
        )
        manual = "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/homologacao'"
        self.assertIn(f"  style:\n    if: ${{{{ github.base_ref == 'homologacao' || ({guard}) || ({manual}) }}}}\n", CI)
        allowed = f"({guard}) || ({manual})"
        for name in (*PROMOTION_JOBS, *BACK_JOBS, *DATABASE_JOBS):
            with self.subTest(job=name):
                label = "    name: python (back)\n" if name == "python-back" else ""
                condition = f"always() && ({allowed})" if name in {"database", "python-back"} else allowed
                self.assertIn(f"  {name}:\n{label}    if: ${{{{ {condition} }}}}\n", CI)

    def test_required_checks_require_every_shard(self):
        for name, shards in (("python-back", BACK_JOBS), ("database", DATABASE_JOBS)):
            with self.subTest(job=name):
                gate = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  \S)", CI)[1]
                names = re.search(r"needs: \[([^]]+)\]", gate)[1].split(", ")
                self.assertCountEqual(names, shards)
                self.assertIn("join(needs.*.result, ' ')", gate)
                expected = " ".join(["success"] * len(shards))
                self.assertIn(f'test "$RESULTS" = "{expected}"', gate)

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

    def test_pull_request_targets_and_explicit_ci_trigger(self):
        for filename in ("ci.yml", "policy.yml"):
            with self.subTest(workflow=filename):
                workflow = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
                triggers = re.search(r"(?ms)^on:\n(.*?)(?=^\S)", workflow).group(1)
                expected = ["pull_request", "workflow_dispatch"] if filename == "ci.yml" else ["pull_request"]
                self.assertEqual(re.findall(r"(?m)^  (\w+):", triggers), expected)
                self.assertRegex(triggers, r"(?m)^    branches: \[homologacao, main\]$")
                self.assertIn("edited", triggers)  # Retargetar um PR para main também precisa validar.
                self.assertNotIn("paths", triggers)  # Checks obrigatórios não podem ficar pendentes por filtro.

    def test_superseded_runs_are_cancelled_per_promotion_pr(self):
        self.assertIn("group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}", CI)
        self.assertRegex(CI, r"(?m)^  cancel-in-progress: true$")

    def test_required_check_names_stay(self):
        for name in ("style", *PROMOTION_JOBS):
            self.assertRegex(CI, rf"(?m)^  {name}:$")
        self.assertIn("module: [mcp, api]", CI)
        self.assertIn("name: python (back)", CI)

    def test_cancellable_workflow_never_deploys_or_migrates_outside_the_runner(self):
        # Cancelar no meio de um deploy deixaria lock e revisão pela metade.
        for command in ("deploy_ecs", "deploy_ec2", "bootstrap_aws", "--apply", "aws ", "secrets."):
            self.assertNotIn(command, CI + DATABASE_TESTS + BACK_TESTS)
        migrations = re.findall(r"MIGRATION_DATABASE_URL: (\S+)", CI + DATABASE_TESTS + BACK_TESTS)
        self.assertTrue(migrations)
        self.assertTrue(all("@localhost:5432/" in url for url in migrations))


if __name__ == "__main__":
    unittest.main()
