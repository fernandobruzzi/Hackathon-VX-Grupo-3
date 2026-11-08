"""Partições do CI por módulo, com a suíte principal cobrindo os testes novos."""

import argparse
import os
from pathlib import Path

EXPERIMENT_SEED = "tests/test_experiment.py::test_same_inputs_and_seed_give_the_same_packet"

SHARDS = {
    "back": {
        "sanitize": ("tests/test_sanitize.py",),
        "evaluation": (
            "tests/test_evaluation.py",
            "tests/test_classification.py",
            "tests/test_measure_ncm_benchmark.py",
        ),
        "experiment-seed": (EXPERIMENT_SEED,),
        "experiment": ("tests/test_experiment.py", "--deselect", EXPERIMENT_SEED),
    },
    "api": {
        "demo": ("tests/test_demo.py",),
        "batch": ("tests/test_batch_api.py",),
        "superseded": ("tests/test_superseded_proposals.py",),
        "batch-job": ("tests/test_batch_job.py",),
        "sanitize": ("tests/test_sanitize.py",),
    },
    "mcp": {
        "acceptance": ("tests/test_mvp_acceptance.py",),
        "search": ("tests/test_search.py",),
        "index": ("tests/test_automatic_index_guard.py", "tests/test_resources_prompts.py"),
    },
}


def selection(module: str, shard: str) -> tuple[str, ...]:
    groups = SHARDS[module]
    if shard != "main":
        return groups[shard]
    files = sorted({arg for group in groups.values() for arg in group if arg.endswith(".py")})
    return tuple(arg for path in files for arg in ("--ignore", path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", choices=SHARDS)
    parser.add_argument("shard")
    args = parser.parse_args()
    if args.shard not in {"main", *SHARDS[args.module]}:
        parser.error(f"Grupo inválido para {args.module}: {args.shard}")
    os.chdir(Path(__file__).resolve().parents[1] / args.module)
    command = ["uv", "run", "--locked", "pytest", "--durations=10", *selection(args.module, args.shard)]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
