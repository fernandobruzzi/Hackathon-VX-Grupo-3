#!/usr/bin/env bash
set -euo pipefail

# Confere se a API responde. Uso: scripts/smoke_test.sh [url-base]
base_url="${1:-http://localhost:8000}"
curl --fail --silent --show-error "$base_url/api/v1/healthz"
echo
