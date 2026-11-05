#!/usr/bin/env bash
set -euo pipefail

# Executa de qualquer diretório. Uso e modos: --help.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/smoke_test.py" "$@"
