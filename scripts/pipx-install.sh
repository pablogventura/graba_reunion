#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TORCH_INDEX="${GRABA_TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"

pipx install --force -e . \
  --pip-args="--extra-index-url ${TORCH_INDEX}"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/graba-reunion"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/.env" ]]; then
  cp -n .env.example "$CONFIG_DIR/.env"
  echo "Semilla de config en $CONFIG_DIR/.env"
fi

echo "Listo. Siguiente paso: graba-reunion setup"
echo "Config: ${GRABA_CONFIG:-$CONFIG_DIR/.env}"
