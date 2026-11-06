#!/usr/bin/env bash
set -euo pipefail

# Volta a stack local ao estado inicial da demo (#34). Rode antes de cada ensaio.
# Uso: DEMO_MODE=true scripts/load_demo_data.sh [nome_do_banco]
# Na AWS, rode `vx-demo reset --confirm <banco>` como task da imagem api. Ver docs/demo.md.

database="${1:-${POSTGRES_DB:-vx_materiais}}"
if [ "${DEMO_MODE:-false}" != "true" ]; then
  echo "Recusado: defina DEMO_MODE=true. O reset apaga aprovações, auditoria, chat e pedidos." >&2
  exit 1
fi
cd "$(dirname "$0")/.."
DEMO_MODE=true docker compose --profile demo run --rm --build demo reset --confirm "$database"
