# AGENTS.md

Guía mínima para agentes que trabajan en este repositorio.

## Stack

- Python 3.10+, hatchling
- CLI: argparse + subcomandos
- Audio: ffmpeg + PulseAudio
- Transcripción: WhisperX (default) o faster-whisper (`--no-diarize`)
- Minuta (opcional, `--groq`): Groq API (`llama-3.3-70b-versatile`)
- Persistencia: SQLite (`reunions.db`)

## Comandos importantes

```bash
make setup          # venv local + torch cu124
make install        # pip install -e ".[dev]"
make test           # pytest
make lint           # ruff check
make check          # lint + test
bash scripts/pipx-install.sh   # instalación global con pipx
graba-reunion setup
graba-reunion check-deps
graba-reunion list
graba-reunion show 1
```

Detalle de setup, tokens HF y variables: ver [README.md](README.md).

## Estructura

```text
src/graba_reunion/
  cli.py              # router argparse
  config.py           # Settings + .env
  paths.py            # rutas sesión y DB
  recording.py        # ffmpeg
  enrichment.py       # Groq + SQLite
  groq_summary.py     # llamada Groq
  db.py               # SQLite
  setup_wizard.py     # wizard setup
  deps_installer.py   # reparar torch CUDA
  commands/           # list, show, setup, check-deps, record
  transcription/      # whisperx, faster_whisper, srt
scripts/              # setup.sh, pipx-install.sh
tests/                # pytest + fixtures
```

## Convenciones

- Código (nombres, funciones, logs técnicos): inglés
- Comentarios y docs internas: español
- Commits: Conventional Commits en inglés
- Diff mínimo; no refactors masivos sin pedido
- `show 1` / `list` rank 1 = reunión más reciente (`recorded_at DESC`)

## Tests

- Framework: pytest en `tests/`
- Correr: `make test`
- Mockear Groq, ffmpeg, whisperx y GPU; no requerir CUDA en tests
- Fixtures en `tests/fixtures/`

## Qué NO hacer

- No depender de `../diarizacion`
- No commitear `.env`, `.venv`, `*.mp3`, `reunion_*.txt`, `*.db`
- No añadir secretos al repo
- No instalar dependencias pesadas sin necesidad en el entorno del agente
- No añadir CI sin que lo pidan
- No borrar tests para hacer pasar la suite

## Configuración

- Secretos y audio: `.env` en la raíz (plantilla `.env.example`)
- Wizard: `graba-reunion setup`
- WhisperX viene en `dependencies`; torch CUDA requiere `scripts/pipx-install.sh` o `make setup`
