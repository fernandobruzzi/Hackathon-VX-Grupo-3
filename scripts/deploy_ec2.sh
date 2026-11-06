#!/usr/bin/env bash
set -euo pipefail

# Sem --apply, renderiza o Plano B sem credenciais; --apply roda na EC2 existente.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --locked --project "$script_dir/.." --package vx-materials-back python "$script_dir/ec2_deploy.py" "$@"
