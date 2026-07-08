#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[dev]"

cp -n .env.example .env
echo "Listo. Siguiente paso: graba-reunion setup"
