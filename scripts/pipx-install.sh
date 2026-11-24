#!/usr/bin/env bash
# Instala graba-reunion con pipx eligiendo un Python compatible con WhisperX (3.10-3.13).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TORCH_INDEX="${GRABA_TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"

pick_python() {
  if [[ -n "${GRABA_PYTHON:-}" ]]; then
    if ! command -v "$GRABA_PYTHON" >/dev/null 2>&1; then
      echo "GRABA_PYTHON=$GRABA_PYTHON no está en el PATH" >&2
      exit 1
    fi
    echo "$GRABA_PYTHON"
    return
  fi

  local candidate version major minor
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    major="${version%%.*}"
    minor="${version#*.}"
    if [[ "$major" -eq 3 && "$minor" -ge 10 && "$minor" -le 13 ]]; then
      echo "$candidate"
      return
    fi
  done

  echo "No hay un Python 3.10-3.13 en el PATH (WhisperX no soporta 3.14+ todavía)." >&2
  echo "Instalá p. ej. python3.12 y reintentá, o usá: GRABA_PYTHON=python3.12 $0" >&2
  exit 1
}

PYTHON_BIN="$(pick_python)"
PYTHON_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Usando $PYTHON_BIN (Python $PYTHON_VER)"

pipx install --force -e . \
  --python "$PYTHON_BIN" \
  --pip-args="--extra-index-url ${TORCH_INDEX}"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/graba-reunion"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/.env" ]]; then
  cp -n .env.example "$CONFIG_DIR/.env"
  echo "Semilla de config en $CONFIG_DIR/.env"
fi

echo
echo "Listo."
echo "Siguiente paso: ejecutá  graba-reunion setup"
echo "  Ahí configurás tokens, mic/monitor y el autostart del indicador"
echo "  (graba-reunion-mic al iniciar sesión)."
echo "Config: ${GRABA_CONFIG:-$CONFIG_DIR/.env}"
