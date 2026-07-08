# graba-reunion

Graba reuniones (micrófono + audio del monitor PulseAudio), transcribe con diarización ([WhisperX](https://github.com/m-bain/whisperX)) y genera título + minuta con [Groq](https://groq.com/), guardando todo en SQLite.

## Inicio rápido

```bash
# Instalación global (recomendada)
bash scripts/pipx-install.sh

# O venv local para desarrollo
make setup

# Configurar tokens y audio
graba-reunion setup

# Verificar dependencias
graba-reunion check-deps

# Grabar reunión
graba-reunion
```

## Requisitos de sistema

- Linux con PulseAudio
- `ffmpeg` (`sudo apt install ffmpeg`)
- Python 3.10+
- GPU NVIDIA con CUDA recomendada para WhisperX

## Instalación

### pipx (uso diario)

WhisperX y faster-whisper se instalan como dependencias del paquete. Para torch con CUDA:

```bash
bash scripts/pipx-install.sh
```

Equivalente manual:

```bash
pipx install --force -e . \
  --pip-args="--extra-index-url https://download.pytorch.org/whl/cu124"
```

### Desarrollo local

```bash
make setup          # crea .venv + torch cu124 + pip install -e ".[dev]"
make check          # ruff + pytest
```

## Cuenta Groq

1. Crear API key en [console.groq.com](https://console.groq.com/)
2. Modelo por defecto: `llama-3.3-70b-versatile` (`GRABA_GROQ_MODEL`)

## Cuenta y modelos Hugging Face

1. Crear token de lectura en [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Aceptar condiciones de uso en:
   - [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3. Pegar el token en `.env` como `HF_TOKEN`

Sin estos pasos, WhisperX falla con error 401/403 al descargar modelos pyannote.

## Modelos Whisper

- Por defecto: `large-v3` (`GRABA_WHISPERX_MODEL`)
- Se descargan automáticamente en el primer uso (~3 GB en `~/.cache`)
- Modo `--no-diarize` usa `faster-whisper` con los mismos modelos, sin pyannote

## PulseAudio

Listar fuentes:

```bash
pactl list sources short
```

- `GRABA_MIC`: fuente del micrófono
- `GRABA_MON`: monitor de la salida (termina en `.monitor`)

El wizard `graba-reunion setup` lista fuentes y ayuda a elegirlas.

## Variables de entorno

| Variable | Obligatoria | Flujo | Descripción |
|----------|-------------|-------|-------------|
| `GROQ_API_KEY` | sí | minuta | API key de Groq |
| `HF_TOKEN` | sí | diarización | Token Hugging Face |
| `GRABA_MIC` | sí | grabar | Fuente PulseAudio del micrófono |
| `GRABA_MON` | sí | grabar | Monitor PulseAudio |
| `GRABA_GROQ_MODEL` | no | minuta | Modelo Groq (default `llama-3.3-70b-versatile`) |
| `GRABA_WHISPERX_MODEL` | no | diarización | Modelo WhisperX (default `large-v3`) |
| `GRABA_WHISPERX_LANGUAGE` | no | diarización | Idioma (default `es`) |
| `GRABA_WHISPERX_DEVICE` | no | transcripción | `cuda` o `cpu` |
| `GRABA_WHISPERX_COMPUTE_TYPE` | no | transcripción | `float16`, `int8`, etc. |
| `GRABA_WHISPERX_BATCH_SIZE` | no | diarización | Batch size (default `16`) |
| `GRABA_MODEL` | no | `--no-diarize` | Modelo faster-whisper |
| `GRABA_LANGUAGE` | no | `--no-diarize` | Idioma faster-whisper |
| `GRABA_DB` | no | SQLite | Ruta de `reunions.db` |

Copiá `.env.example` a `.env` o usá `graba-reunion setup`.

## Comandos

```bash
graba-reunion                  # grabar + transcribir + minuta
graba-reunion setup            # wizard de configuración
graba-reunion setup --install-deps -y  # reparar torch CUDA
graba-reunion check-deps       # verificar dependencias
graba-reunion list             # listar reuniones (1 = más reciente)
graba-reunion show 1           # ver minuta de la última
graba-reunion show 1 --transcript
graba-reunion --skip-groq      # sin Groq ni SQLite
graba-reunion --no-diarize     # faster-whisper sin speakers
graba-reunion --enrich-only reunion_....txt
```

## Salida por sesión

| Modo | Archivos |
|------|----------|
| default | `.mp3`, `.txt`, `_minuta.md`, `reunions.db` |
| `--skip-groq` | `.mp3`, `.txt` |
| `--no-diarize` | `.mp3`, `.srt`, `.txt`, `_minuta.md` |

## Migración desde ../diarizacion

Si usabas el repo `diarizacion` hermano:

1. Copiá `HF_TOKEN` al `.env` de este repo
2. Instalá con `scripts/pipx-install.sh` o `make setup`
3. Ya no hace falta `../diarizacion`

## Troubleshooting

| Problema | Solución |
|----------|----------|
| `whisperx` no encontrado | `bash scripts/pipx-install.sh` |
| torch sin CUDA | `graba-reunion setup --install-deps -y` |
| HF 401/403 | Aceptar modelos pyannote + verificar `HF_TOKEN` |
| `ffmpeg` no encontrado | `sudo apt install ffmpeg` |
| Sin audio en grabación | Revisar `GRABA_MIC` / `GRABA_MON` con `pactl` |
| Groq inválido | Verificar `GROQ_API_KEY` en `.env` |
