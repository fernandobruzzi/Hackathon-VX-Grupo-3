#!/usr/bin/env bash
set -euo pipefail

# Formata com o Prettier os arquivos do front recebidos do hook de commit.
cd front
npx prettier --write --ignore-unknown "${@#front/}"
