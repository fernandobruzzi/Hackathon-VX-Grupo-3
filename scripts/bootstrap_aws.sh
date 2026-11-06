#!/usr/bin/env bash
set -euo pipefail

# Prepara ECR, logs, bucket e cluster; IAM/rede/RDS vêm da conta autorizada.
# Sem --apply, apenas valida/renderiza offline. Consulte deployment/README.md.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --locked --project "$script_dir/.." --package vx-materials-back python "$script_dir/aws_deploy.py" bootstrap "$@"
