#!/usr/bin/env bash
set -euo pipefail

# Sem mutações AWS; --offline não consulta nem credenciais.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --locked --project "$script_dir/.." --package vx-materials-back python "$script_dir/aws_preflight.py" "$@"
