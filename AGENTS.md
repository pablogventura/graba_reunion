# AGENTS.md

Guía mínima para agentes que trabajan en este repositorio.

## Stack

- Python 3.10+, hatchling
- CLI: argparse + subcomandos
- Audio: ffmpeg + PulseAudio (ALSA opcional)
- Transcripción: WhisperX (default) o faster-whisper (`--no-diarize`)
- Minuta (opcional, `--groq`): Groq API (`llama-3.3-70b-versatile`)
- Persistencia: archivos `{prefijo}_*.txt` y `{prefijo}_*_minuta.md`
- Config: `$XDG_CONFIG_HOME/graba-reunion/.env` (override `GRABA_CONFIG`)
- Salida default: `$XDG_DATA_HOME/graba-reunion/recordings`

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
graba-reunion voices
graba-reunion search "entrega del laboratorio"
graba-reunion phrases archivo.mp3
graba-reunion view
graba-reunion-mic   # indicador: autograba cuando otra app usa el mic
```

Detalle de setup, tokens HF y variables: ver [README.md](README.md) y la [guía completa](docs/guia-completa.md).

## Estructura

```text
src/graba_reunion/
  cli.py              # router argparse
  config.py           # Settings + .env
  paths.py            # rutas de sesión
  meetings.py         # listado desde los .txt
  recording.py        # ffmpeg
  enrichment.py       # minuta Groq en markdown
  groq_summary.py     # llamada Groq
  search.py           # búsqueda por tema, palabra o participante
  phrases.py          # JSON de frases (segundos del MP3 y hora)
  viewer/             # visor local: servidor y página estática
  setup_wizard.py     # wizard setup
  deps_installer.py   # reparar torch CUDA
  commands/           # list, show, setup, check-deps, record, voices, search, phrases
  transcription/      # whisperx, faster_whisper, srt
  voices.py           # perfiles de voz y renombre en el txt
  voice_enroll.py     # diarización de MP3 ya grabados y clips
  mic_watch.py        # detección PipeWire y antirrebote
  mic_indicator.py    # icono GNOME y autograbación
scripts/              # setup.sh, pipx-install.sh, graba-reunion-mic
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

- Secretos y audio: `~/.config/graba-reunion/.env` (plantilla `.env.example`); fallback de lectura al `.env` del repo
- Wizard: `graba-reunion setup` (migra el `.env` del repo a XDG al escribir)
- Defaults sin GPU: `device=cpu`, `compute_type=int8`
- WhisperX viene en `dependencies`; torch CUDA: `graba-reunion setup --install-deps` o `scripts/pipx-install.sh`
