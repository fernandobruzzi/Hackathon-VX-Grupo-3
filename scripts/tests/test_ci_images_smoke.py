"""O script local reproduz o job images-smoke do CI (#157) sem divergir dele."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts" / "ci_images_smoke.sh").read_text(encoding="utf-8")


def ci_job(name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", CI, re.M | re.S)
    assert match, name
    return match.group(1)


def commands(text: str) -> list[str]:
    """Comandos de verificação, na ordem, sem variáveis de porta ou diretório."""
    pattern = "|".join(
        (
            r"scripts/smoke_test\.sh \S+ --mode \w+",
            r"docker compose up [^\n]+",
            r"docker compose --profile demo run [^\n]+",
            r"docker compose exec -T agent [^\n]+",
            r"python3 scripts/ci_smoke_kit\.py data/desafio01",
        )
    )
    normalized = []
    for command in re.findall(f"({pattern})", text):
        command = re.sub(r"scripts/smoke_test\.sh \S+", "scripts/smoke_test.sh URL", command)
        normalized.append(command.strip())
    return normalized


class ImagesSmokeParityTests(unittest.TestCase):
    def test_local_script_runs_the_ci_steps_in_the_same_order(self):
        job = ci_job("images-smoke")
        self.assertEqual(commands(SCRIPT), commands(job))
        self.assertIn("scripts/smoke_test.sh URL --mode local", commands(job))
        self.assertIn("scripts/smoke_test.sh URL --mode flow", commands(job))

    def test_local_script_checks_the_same_packaged_references(self):
        for check in re.findall(r"docker run --rm \"\$COMPOSE_PROJECT_NAME-(\w+)\" ([^\n]+)", ci_job("images-smoke")):
            self.assertIn(f'docker run --rm "$COMPOSE_PROJECT_NAME-{check[0]}" {check[1].split(" >")[0]}', SCRIPT)

    def test_local_script_is_isolated_and_always_cleans_up(self):
        self.assertIn("set -euo pipefail", SCRIPT)
        self.assertIn("trap cleanup EXIT", SCRIPT)
        self.assertIn("docker compose down -v --remove-orphans", SCRIPT)
        self.assertIn("docker compose logs --no-color --tail=100", SCRIPT)
        self.assertRegex(SCRIPT, r'COMPOSE_PROJECT_NAME="\$\{COMPOSE_PROJECT_NAME:-vx-ci-local-')
        self.assertIn("COMPOSE_FILE=docker-compose.yml:.github/compose-smoke.yml", SCRIPT)
        self.assertIn("COMPOSE_FILE=docker-compose.yml:.github/compose-smoke.yml", CI)


if __name__ == "__main__":
    unittest.main()
