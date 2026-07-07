# graba-reunion

Graba reuniones (micrófono + audio del monitor PulseAudio), transcribe con **diarización de hablantes** ([WhisperX](https://github.com/m-bain/whisperX)) y genera **título + minuta** con [Groq](https://groq.com/) (`llama-3.3-70b-versatile`), guardando todo en SQLite.

## Requisitos

- Linux con PulseAudio
- `ffmpeg`
- Python 3.10+
- Para transcripción con diarización (modo por defecto):
  - WhisperX instalado (ver abajo)
  - CUDA (GPU recomendada)
  - Token de Hugging Face con acceso a [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
- Para `--no-diarize`: CLI `faster-whisper` en PATH
- API key de Groq (`GROQ_API_KEY`) para título, minuta y SQLite

## Instalación del paquete

```bash
pip install -e .
# o
pipx install -e . --force

cp .env.example .env   # pegar GROQ_API_KEY
```

## Setup de WhisperX

El proyecto usa el venv de [`../diarizacion`](../diarizacion) (`../diarizacion/.venv/bin/whisperx`). Si aún no lo tenés:

```bash
cd ../diarizacion
python3 -m venv .venv
source .venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install whisperx
cp .env.example .env   # pegar HF_TOKEN
```

El token HF se lee de `../diarizacion/.env` o de la variable de entorno `HF_TOKEN`.
Los demás parámetros de WhisperX están en constantes al inicio de `src/graba_reunion/cli.py`.

Antes de grabar, el CLI verifica que whisperx (o faster-whisper con `--no-diarize`) esté disponible.

## Consultar reuniones guardadas

```bash
# Listar (1 = más reciente)
graba-reunion list

# Ver minuta de la última reunión
graba-reunion show 1

# Ver transcripción
graba-reunion show 1 --transcript

# Minuta + transcripción
graba-reunion show 1 --all
```

Los números coinciden con la columna `#` de `list`. Si usás otra base, indicá `--db` o `-d`.

## Uso

```bash
# Grabar, transcribir, generar minuta y guardar en reunions.db
graba-reunion

# Solo grabar, sin transcribir
graba-reunion --skip-transcribe

# Transcribir sin Groq ni SQLite
graba-reunion --skip-groq

# Minuta + SQLite desde un TXT ya transcrito
graba-reunion --enrich-only reunion_2026-04-29_17-15-40.txt

# Transcripción rápida sin diarización (faster-whisper, TXT plano)
graba-reunion --no-diarize

# Transcribir un MP3 ya grabado (sin grabar de nuevo)
graba-reunion --transcribe-only reunion_2026-04-29_17-15-40.mp3

# Directorio de salida
graba-reunion -d /ruta/salida
```

Detener la grabación con **Ctrl+C** o **SIGTERM**; luego se transcribe el MP3 generado.

## Salida

Por sesión se genera `reunion_YYYY-MM-DD_HH-MM-SS.mp3` y, salvo `--skip-transcribe`:

| Modo | Archivos | Formato TXT |
|------|----------|-------------|
| default (diarización) | `.mp3`, `.txt`, `_minuta.md`, `reunions.db` | Una línea por intervención: `[SPEAKER_01]: texto` |
| `--no-diarize` | `.mp3`, `.srt`, `.txt`, `_minuta.md`, `reunions.db` | Un párrafo plano sin speakers |
| `--skip-groq` | `.mp3`, `.txt` (sin minuta ni DB) | Igual que arriba |

La minuta incluye resumen, temas, decisiones y puntos de acción. Los datos quedan en la tabla `meetings` de SQLite.

Los MP3, SRT, `.db` y minutas no se versionan (ver `.gitignore`).

## Configuración

| Variable | Uso |
|----------|-----|
| `GRABA_MIC` | Fuente PulseAudio del micrófono |
| `GRABA_MON` | Monitor del auricular/salida |
| `GRABA_MODEL` | Modelo faster-whisper (solo con `--no-diarize`) |
| `GROQ_API_KEY` | API key de Groq (o en `.env`) |
| `GRABA_DB` | Ruta de la base SQLite (por defecto `<output-dir>/reunions.db`) |
| `GRABA_GROQ_MODEL` | Modelo Groq (por defecto `llama-3.3-70b-versatile`) |

Parámetros de WhisperX (`model`, `device`, `batch_size`, etc.) están en constantes al inicio de `cli.py`.
