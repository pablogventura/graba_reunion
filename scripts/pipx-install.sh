#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pipx install --force -e . \
  --pip-args="--extra-index-url https://download.pytorch.org/whl/cu124"

cp -n .env.example .env
echo "Listo. Siguiente paso: graba-reunion setup"
