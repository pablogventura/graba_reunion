# graba-reunion

Graba reuniones (micrófono + audio del monitor), transcribe con diarización ([WhisperX](https://github.com/m-bain/whisperX)) y, si querés (`--groq`), genera título + minuta con [Groq](https://groq.com/) en SQLite.

**Documentación completa:** [docs/guia-completa.md](docs/guia-completa.md)

## Inicio rápido

```bash
# Instalación (desde el clone)
bash scripts/pipx-install.sh

# Tokens, mic/monitor, device CPU/GPU
graba-reunion setup
graba-reunion check-deps

# Grabar + transcribir (sin minuta)
graba-reunion
# Ctrl+C para detener y transcribir

# Con minuta Groq + SQLite
graba-reunion --groq
```

Salida por defecto: `~/.local/share/graba-reunion/recordings/`  
Config: `~/.config/graba-reunion/.env`

## Qué hace

| Paso | Default | Opcional |
|------|---------|----------|
| Grabar mic + monitor (ffmpeg) | sí | `--skip-transcribe` solo audio |
| Transcribir con speakers (WhisperX) | sí | `--no-diarize` (faster-whisper) |
| Minuta + SQLite (Groq) | no | `--groq` / `--enrich-only` |

## Requisitos

- Linux + PulseAudio (o PipeWire-as-Pulse); ALSA opcional
- `ffmpeg`
- Python 3.10+ (pipx trae el venv)
- [HF token](https://huggingface.co/settings/tokens) + aceptar licencias [pyannote diarization](https://huggingface.co/pyannote/speaker-diarization-community-1) y [segmentation](https://huggingface.co/pyannote/segmentation-3.0)
- Groq API key solo si usás `--groq`
- GPU NVIDIA recomendada; sin GPU: `device=cpu`

## Comandos frecuentes

```bash
graba-reunion                      # grabar + transcribir
graba-reunion -d .                 # grabar en el CWD
graba-reunion --groq               # + minuta y DB
graba-reunion --language en --model medium --device cpu
graba-reunion --transcribe-only archivo.mp3
graba-reunion --enrich-only archivo.txt
graba-reunion list
graba-reunion show 1               # 1 = más reciente
graba-reunion show 1 --transcript
graba-reunion setup
graba-reunion setup --install-deps -y
graba-reunion check-deps
```

## Configuración (resumen)

| Ruta | Rol |
|------|-----|
| `~/.config/graba-reunion/.env` | Config preferida |
| `GRABA_CONFIG` | Override de ruta |
| `.env` en el clone | Fallback de lectura; se migra a XDG en el primer `setup` |
| `~/.local/share/graba-reunion/recordings/` | Grabaciones por defecto |

Plantilla de variables: [`.env.example`](.env.example).

Variables clave:

- `GRABA_MIC` / `GRABA_MON` / `GRABA_AUDIO_BACKEND`
- `HF_TOKEN`, `GROQ_API_KEY` (opcional)
- `GRABA_WHISPERX_MODEL`, `LANGUAGE`, `DEVICE` (default `cpu`), `COMPUTE_TYPE`
- `GRABA_OUTPUT_DIR`, `GRABA_SESSION_PREFIX`, `GRABA_DB`

Detalle de cada variable, flujos y troubleshooting: **[guía completa](docs/guia-completa.md)**.

## Instalación (detalle breve)

```bash
# pipx (uso diario)
bash scripts/pipx-install.sh

# desarrollo
make setup
make check
```

Índice torch CUDA: `GRABA_TORCH_INDEX` (default cu124).

## Desarrollo

Ver [AGENTS.md](AGENTS.md).

```bash
make test
make lint
make check
```

## Troubleshooting rápido

| Problema | Acción |
|----------|--------|
| `whisperx` no encontrado | `graba-reunion setup --install-deps` |
| HF 401/403 | Aceptar pyannote + revisar `HF_TOKEN` |
| Sin CUDA | `device=cpu` o `setup --install-deps -y` |
| Sin audio | `pactl list sources short` (mic vs `.monitor`) |
| ¿Dónde está el `.env`? | `graba-reunion check-deps` |

Más casos: [guía completa - Troubleshooting](docs/guia-completa.md#17-troubleshooting).
