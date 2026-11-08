#!/usr/bin/env bash
# Reproduz localmente o job images-smoke do CI (#157), na mesma ordem:
# imagens, referências empacotadas, recorte do kit, smoke local, reset da demo,
# smoke flow e medição do Agent. Usa um projeto Compose descartável, com banco,
# volumes, rede e portas próprios, e remove tudo ao terminar, inclusive em falha
# ou Ctrl+C. Não toca na stack local padrão nem em ambientes externos.
#
#   scripts/ci_images_smoke.sh             # build com cache local do Docker
#   scripts/ci_images_smoke.sh --no-cache  # build limpo, como um runner novo
set -euo pipefail

cd "$(dirname "$0")/.."
build_args=()
case "${1:-}" in
  "") ;;
  --no-cache) build_args+=(--no-cache) ;;
  *) echo "uso: $0 [--no-cache]" >&2; exit 2 ;;
esac

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-vx-ci-local-$(date +%s)-$$}"
export APP_ENV=local LOCAL_TEST_SESSION=true
export DB_PORT="${DB_PORT:-15432}" API_BIND_PORT="${API_BIND_PORT:-18000}"
export APP_ORIGIN="http://127.0.0.1:$API_BIND_PORT"
export AGENT_INTERNAL_TOKEN_SECRET=ci_only_internal_token_secret_with_32_bytes
base="http://127.0.0.1:$API_BIND_PORT"
work="$(mktemp -d)"

step() { echo "== $(date +%H:%M:%S) $*"; }
cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ]; then
    step "logs (status $status)"
    docker compose logs --no-color --tail=100 || true
  fi
  step "removendo $COMPOSE_PROJECT_NAME"
  docker compose down -v --remove-orphans || true
  images="$(docker image ls --format '{{.Repository}}:{{.Tag}}' | grep "^$COMPOSE_PROJECT_NAME-" || true)"
  [ -z "$images" ] || docker image rm $images >/dev/null || true
  rm -rf "$work"
  step "fim, status $status"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

step "imagens api, agent e batch ($COMPOSE_PROJECT_NAME)"
docker build ${build_args[@]+"${build_args[@]}"} --target api \
  -t "$COMPOSE_PROJECT_NAME-api" -t "$COMPOSE_PROJECT_NAME-migrate" \
  -t "$COMPOSE_PROJECT_NAME-bootstrap" -t "$COMPOSE_PROJECT_NAME-demo" .
docker build ${build_args[@]+"${build_args[@]}"} --target agent -t "$COMPOSE_PROJECT_NAME-agent" .
docker build ${build_args[@]+"${build_args[@]}"} --target batch \
  -t "$COMPOSE_PROJECT_NAME-batch" -t "$COMPOSE_PROJECT_NAME-index" .

step "referências empacotadas, sem bind mounts"
docker run --rm "$COMPOSE_PROJECT_NAME-agent" python -c 'import os; from domain.pdm_loader import load_pdm; assert load_pdm(os.environ["PDM_WORKBOOK_PATH"]).classes'
docker run --rm "$COMPOSE_PROJECT_NAME-batch" vx-back --help >/dev/null
docker run --rm "$COMPOSE_PROJECT_NAME-api" python -c 'import ssl; assert ssl.create_default_context(cafile="/app/certs/rds-global-bundle.pem").cert_store_stats()["x509_ca"] > 0'

step "recorte determinístico do kit"
python3 scripts/ci_smoke_kit.py data/desafio01 "$work/vx-smoke-data/desafio01"
export CI_SMOKE_DATA_DIR="$work/vx-smoke-data"
export COMPOSE_FILE=docker-compose.yml:.github/compose-smoke.yml

step "stack isolada"
docker compose up -d --no-build --wait --wait-timeout 300 api
step "smoke local"
scripts/smoke_test.sh "$base" --mode local
step "reset da demo"
DEMO_MODE=true docker compose --profile demo run --rm --no-deps --pull never demo reset --confirm vx_materiais
step "smoke flow"
scripts/smoke_test.sh "$base" --mode flow
step "concorrência e cancelamento do Agent"
docker compose exec -T agent python - --requests 8 < scripts/measure_agent.py
