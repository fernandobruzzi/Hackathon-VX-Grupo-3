"""Espera em fila e duração útil das execuções do CI em main (#108).

Lê as execuções pela API do GitHub com `gh` e mostra, por commit, quanto tempo a execução
esperou antes do primeiro job começar e quanto durou depois disso. Só lê: não cancela nem
reexecuta nada.

    uv run --package vx-materials-back python scripts/ci_queue_report.py --limit 20
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

REPO = "fernandobruzzi/Hackathon-VX-Grupo-3"


@dataclass(frozen=True)
class RunTiming:
    run_id: int
    sha: str
    conclusion: str
    queued_seconds: int | None
    useful_seconds: int | None


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def timing(run: dict, jobs: list[dict]) -> RunTiming:
    """Fila = criação da execução até o primeiro job começar; útil = daí até o último job terminar.

    `run_started_at` não serve para medir fila: o GitHub o preenche na criação, mesmo quando a
    execução fica parada no grupo de concorrência.
    """
    created = _time(run["created_at"])
    started = [_time(job["started_at"]) for job in jobs if job.get("started_at")]
    finished = [_time(job["completed_at"]) for job in jobs if job.get("completed_at")]
    first = min(started) if started else None
    last = max(finished) if finished and len(finished) == len(jobs) else None
    return RunTiming(
        run_id=run["id"],
        sha=run["head_sha"][:7],
        conclusion=run.get("conclusion") or run["status"],
        queued_seconds=int((first - created).total_seconds()) if first else None,
        useful_seconds=int((last - first).total_seconds()) if first and last else None,
    )


def _gh(path: str) -> dict:
    output = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    runs = _gh(
        f"repos/{args.repo}/actions/workflows/ci.yml/runs?branch={args.branch}&event=push&per_page={args.limit}"
    )["workflow_runs"]
    print("execucao\tcommit\tresultado\tfila_s\tutil_s")
    for run in runs:
        jobs = _gh(f"repos/{args.repo}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
        row = timing(run, jobs)
        print(
            f"{row.run_id}\t{row.sha}\t{row.conclusion}\t"
            f"{'' if row.queued_seconds is None else row.queued_seconds}\t"
            f"{'' if row.useful_seconds is None else row.useful_seconds}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
