# Guía completa de graba-reunion

Manual de uso, configuración, flujos y resolución de problemas.

## Índice

1. [Qué hace](#1-qué-hace)
2. [Requisitos](#2-requisitos)
3. [Instalación](#3-instalación)
4. [Primera configuración](#4-primera-configuración)
5. [Dónde se guardan config y archivos](#5-dónde-se-guardan-config-y-archivos)
6. [Uso diario](#6-uso-diario)
7. [Referencia de comandos](#7-referencia-de-comandos)
8. [Referencia de opciones](#8-referencia-de-opciones)
9. [Variables de entorno](#9-variables-de-entorno)
10. [Flujos de trabajo tipicos](#10-flujos-de-trabajo-típicos)
11. [Audio (Pulse / ALSA)](#11-audio-pulse--alsa)
12. [Transcripción y diarización](#12-transcripción-y-diarización)
13. [Minutas con Groq](#13-minutas-con-groq)
14. [Base de datos y consulta](#14-base-de-datos-y-consulta)
15. [CPU vs GPU](#15-cpu-vs-gpu)
16. [Desarrollo y tests](#16-desarrollo-y-tests)
17. [Troubleshooting](#17-troubleshooting)
18. [Preguntas frecuentes](#18-preguntas-frecuentes)

---

## 1. Qué hace

`graba-reunion` es una CLI para Linux que:

1. **Graba** el micrófono y el audio de salida del sistema (monitor Pulse/ALSA) en un MP3.
2. **Transcribe** con diarización de hablantes (WhisperX + pyannote) o, si preferís, sin diarización (`faster-whisper`).
3. **Opcionalmente** genera título y minuta con Groq y guarda el resultado en SQLite.

Por defecto **no** llama a Groq: solo graba y transcribe. La minuta se activa con `--groq`.

```text
[Mic] ----\
           +-- ffmpeg (amix) --> reunion_YYYY-mm-dd_HH-MM-SS.mp3
[Monitor]-/                              |
                                         v
                              WhisperX (diarize)  o  faster-whisper
                                         |
                                         v
                                    reunion_....txt
                                         |
                          (opcional --groq) v
                              minuta.md + reunions.db
```

---

## 2. Requisitos

### Sistema

| Requisito | Notas |
|-----------|--------|
| Linux | Pensado para escritorio Linux |
| PulseAudio o PipeWire (modo Pulse) | Default; ALSA como alternativa |
| `ffmpeg` | `sudo apt install ffmpeg` |
| `pactl` | Para listar fuentes en el wizard (paquete `pulseaudio-utils` o PipeWire equivalente) |
| Python 3.10+ | La install con pipx trae su propio intérprete en el venv |

### Cuentas externas

| Servicio | Cuándo lo necesitás |
|----------|---------------------|
| [Hugging Face](https://huggingface.co/settings/tokens) + aceptar licencias pyannote | Diarización (modo default) |
| [Groq](https://console.groq.com/) | Solo si usás `--groq` o `--enrich-only` |

Modelos pyannote a aceptar en HF:

- https://huggingface.co/pyannote/speaker-diarization-community-1
- https://huggingface.co/pyannote/segmentation-3.0

### Hardware

- **Con GPU NVIDIA + CUDA**: más rápido; el wizard sugiere `device=cuda` y `float16`.
- **Sin GPU**: funciona con `device=cpu` e `int8` (más lento, sobre todo `large-v3`).

---

## 3. Instalación

### Opción A: pipx (recomendada para uso diario)

Desde el clone del repositorio:

```bash
git clone https://github.com/pablogventura/graba_reunion.git
cd graba_reunion
bash scripts/pipx-install.sh
```

Eso:

- Instala el paquete en modo editable con pipx
- Usa el índice PyTorch CUDA (`GRABA_TORCH_INDEX` si está definido)
- Siembra `~/.config/graba-reunion/.env` desde `.env.example` si no existe

Comprobar:

```bash
which graba-reunion
graba-reunion check-deps
```

### Opción B: venv de desarrollo

```bash
make setup      # .venv + deps
make check      # ruff + pytest
source .venv/bin/activate
graba-reunion --help
```

### Actualizar

Si la install es editable (`pipx install -e .`), los cambios del repo se reflejan al tiro. Para reinstalar:

```bash
bash scripts/pipx-install.sh
# o
graba-reunion setup --install-deps -y
```

---

## 4. Primera configuración

```bash
graba-reunion setup
```

El wizard pregunta (Enter = mantener valor actual):

1. `HF_TOKEN` (obligatorio para diarizar)
2. `GROQ_API_KEY` (opcional; solo para `--groq`)
3. Backend de audio (`pulse` / `alsa`)
4. Micrófono y monitor (lista `pactl` si es Pulse)
5. Device (`cuda`/`cpu`) según detección de GPU
6. Idioma y modelo Whisper
7. Compute type y batch size
8. Directorio de salida, prefijo de archivos, ruta SQLite
9. Modelo Groq (si cargaste API key)

Al primer `setup` / escritura, si solo existía un `.env` en el clone del repo, **se migra** a:

```text
~/.config/graba-reunion/.env
```

y se imprime la ruta nueva.

Reparar torch CUDA sin wizard interactivo:

```bash
graba-reunion setup --install-deps -y
```

Verificar:

```bash
graba-reunion check-deps
```

---

## 5. Dónde se guardan config y archivos

### Configuración

Orden de resolución del archivo `.env`:

1. `GRABA_CONFIG` (archivo `.env` o directorio que contenga `.env`)
2. `$XDG_CONFIG_HOME/graba-reunion/.env` (default `~/.config/graba-reunion/.env`)
3. Fallback de **lectura**: `.env` en la raíz del clone del proyecto

Las escrituras (`setup`, `write_env`) van a la ruta preferida (1 o 2), no al repo, salvo que `GRABA_CONFIG` apunte ahí.

Las variables de entorno del proceso **pisan** siempre lo del archivo.

Ejemplos:

```bash
# Config en otro lado
export GRABA_CONFIG=~/mi-config/graba.env
graba-reunion setup

# Override puntual sin editar archivo
GRABA_WHISPERX_DEVICE=cpu graba-reunion --transcribe-only audio.mp3
```

### Grabaciones y textos

| Qué | Dónde por defecto |
|-----|-------------------|
| MP3 / TXT / SRT / minuta | `$XDG_DATA_HOME/graba-reunion/recordings` |
| Override | `GRABA_OUTPUT_DIR` o `-d` / `--output-dir` |
| Grabar en el directorio actual | `graba-reunion -d .` |

Nombre de sesión:

```text
{GRABA_SESSION_PREFIX}_{YYYY-MM-DD_HH-MM-SS}.mp3
{GRABA_SESSION_PREFIX}_{YYYY-MM-DD_HH-MM-SS}.txt
```

Default del prefijo: `reunion`.

### Base SQLite

| Prioridad | Ruta |
|-----------|------|
| 1 | `--db PATH` |
| 2 | `GRABA_DB` |
| 3 | `<output-dir>/reunions.db` |

Solo se escribe cuando usás `--groq` o `--enrich-only`.

### Caches de modelos

Whisper / Hugging Face / torch suelen usar:

- `~/.cache/huggingface`
- `~/.cache/torch`

Podés redirigir con `HF_HOME` o `XDG_CACHE_HOME`. El primer run con `large-v3` descarga varios GB.

---

## 6. Uso diario

### Grabar y transcribir (caso más común)

```bash
graba-reunion
```

1. Empieza a grabar (mic + monitor).
2. Cuando terminás la reunión: `Ctrl+C` (o SIGTERM).
3. Transcribe con diarización y deja el `.txt` junto al `.mp3`.

Salida típica:

```text
~/.local/share/graba-reunion/recordings/reunion_2026-09-21_15-30-00.mp3
~/.local/share/graba-reunion/recordings/reunion_2026-09-21_15-30-00.txt
```

### Grabar + minuta

```bash
graba-reunion --groq
```

Además genera `{base}_minuta.md` y una fila en SQLite.

### Grabar en el directorio actual

```bash
cd ~/Documentos/reuniones
graba-reunion -d .
```

### Solo audio, sin transcribir

```bash
graba-reunion --skip-transcribe
```

### Transcribir un MP3 que ya tenés

```bash
graba-reunion --transcribe-only ~/audio/reunion.mp3
graba-reunion --transcribe-only ~/audio/reunion.mp3 --no-diarize
graba-reunion --transcribe-only ~/audio/reunion.mp3 --groq
```

### Generar minuta de un TXT existente

```bash
graba-reunion --enrich-only ~/.../reunion_2026-09-21_15-30-00.txt
```

### Consultar reuniones guardadas (requiere haber usado `--groq`)

```bash
graba-reunion list
graba-reunion show 1
graba-reunion show 1 --transcript
graba-reunion show 1 --all
```

`1` = más reciente (`recorded_at DESC`).

---

## 7. Referencia de comandos

### Sin subcomando / `record`

Mismo comportamiento: grabar (salvo `--transcribe-only` / `--enrich-only`) y opcionalmente transcribir / enriquecer.

```bash
graba-reunion [opciones]
graba-reunion record [opciones]
```

### `setup`

Wizard de configuración y reparación de deps.

```bash
graba-reunion setup
graba-reunion setup --install-deps
graba-reunion setup --install-deps -y
```

### `check-deps`

Imprime estado de ffmpeg, whisperx, faster-whisper, tokens, mic/mon, CUDA y ruta del `.env`.

```bash
graba-reunion check-deps
```

Exit code distinto de 0 si faltan piezas esenciales (ffmpeg, whisperx, HF_TOKEN). `GROQ_API_KEY` se reporta como opcional.

### `list`

Lista reuniones en la DB (rank, fecha, título).

```bash
graba-reunion list
graba-reunion list --db ~/datos/reunions.db
```

### `show N`

Muestra la reunión número `N` (1 = más reciente).

```bash
graba-reunion show 1              # minuta
graba-reunion show 1 --transcript
graba-reunion show 2 --all        # minuta + transcripción
```

---

## 8. Referencia de opciones

Aplican al flujo de grabación/transcripción (root o `record`):

| Opción | Descripción |
|--------|-------------|
| `-d`, `--output-dir` | Directorio de salida. Default: data dir XDG o `GRABA_OUTPUT_DIR` |
| `--db PATH` | SQLite explícita |
| `--mic` / `--mon` | Fuentes de audio (override de config) |
| `--language` | Idioma ISO (`es`, `en`, ...). Aplica a WhisperX y a `--no-diarize` |
| `--model` | Modelo (`large-v3`, `medium`, `tiny`, ...) |
| `--device` | `cuda` o `cpu` (override de `GRABA_WHISPERX_DEVICE`) |
| `--transcribe-only MP3` | No graba; solo transcribe ese archivo |
| `--no-diarize` | Usa faster-whisper (sin speakers) |
| `--skip-transcribe` | Solo graba el MP3 |
| `--min-mp3-bytes N` | Mínimo de bytes para intentar transcribir (default 256) |
| `--groq` | Minuta + SQLite |
| `--groq-model` | Modelo Groq (requiere `--groq`) |
| `--enrich-only TXT` | Solo minuta Groq a partir de un TXT |

Detener la grabación: `Ctrl+C` o `kill -TERM` al PID del proceso. ffmpeg puede salir con código 255; el MP3 suele quedar usable igual.

---

## 9. Variables de entorno

Plantilla: [`.env.example`](../.env.example).

### Obligatorias según flujo

| Variable | Grabar | Diarizar | `--groq` |
|----------|--------|----------|----------|
| `GRABA_MIC` | sí | - | - |
| `GRABA_MON` | sí | - | - |
| `HF_TOKEN` | - | sí | - |
| `GROQ_API_KEY` | - | - | sí |

También se acepta `HUGGING_FACE_HUB_TOKEN` como alias de `HF_TOKEN`.

### Audio y salida

| Variable | Default | Descripción |
|----------|---------|-------------|
| `GRABA_AUDIO_BACKEND` | `pulse` | `pulse` o `alsa` |
| `GRABA_OUTPUT_DIR` | (XDG data/.../recordings) | Directorio de sesiones |
| `GRABA_SESSION_PREFIX` | `reunion` | Prefijo de nombres de archivo |
| `GRABA_DB` | `<output-dir>/reunions.db` | Ruta SQLite |

### Transcripción

| Variable | Default | Descripción |
|----------|---------|-------------|
| `GRABA_WHISPERX_MODEL` | `large-v3` | Modelo |
| `GRABA_WHISPERX_LANGUAGE` | `es` | Idioma |
| `GRABA_WHISPERX_DEVICE` | `cpu` | `cuda` / `cpu` |
| `GRABA_WHISPERX_COMPUTE_TYPE` | `int8` (cpu) / suele `float16` (cuda) | Tipo de cómputo |
| `GRABA_WHISPERX_BATCH_SIZE` | `16` | Batch WhisperX |
| `GRABA_MODEL` | alias | Si no hay `GRABA_WHISPERX_MODEL` |
| `GRABA_LANGUAGE` | alias | Si no hay `GRABA_WHISPERX_LANGUAGE` |

### Groq

| Variable | Default | Descripción |
|----------|---------|-------------|
| `GRABA_GROQ_MODEL` | `llama-3.3-70b-versatile` | Modelo |
| `GRABA_GROQ_MAX_CHARS` | `120000` | Tope de caracteres del transcript al resumir |
| `GRABA_GROQ_TEMPERATURE` | `0.2` | Temperature |

El idioma de la minuta sigue el idioma de transcripción (`es` -> minuta en español; otro código -> prompt/secciones en inglés).

### Install / rutas

| Variable | Descripción |
|----------|-------------|
| `GRABA_TORCH_INDEX` | Índice pip de torch CUDA (default cu124) |
| `GRABA_CONFIG` | Ruta al `.env` o al directorio de config |
| `XDG_CONFIG_HOME` / `XDG_DATA_HOME` | Bases XDG |

---

## 10. Flujos de trabajo típicos

### Reunión con speakers y minuta

```bash
graba-reunion --groq
# Ctrl+C al terminar
graba-reunion show 1
```

### Reunión larga en laptop sin GPU

```bash
# En setup o .env: DEVICE=cpu, MODEL=medium o small
graba-reunion --model medium --device cpu
```

### Solo capturar audio en una carpeta de proyecto

```bash
mkdir -p ~/proyectos/foo/notas && cd ~/proyectos/foo/notas
graba-reunion -d . --skip-transcribe
# más tarde:
graba-reunion --transcribe-only ./reunion_....mp3 --groq
```

### Reprocesar con otro idioma

```bash
graba-reunion --transcribe-only reunion.mp3 --language en --model large-v3
```

### Sin diarización (más simple, sin HF pyannote en runtime de speakers)

Sigue haciendo falta el stack instalado; `--no-diarize` evita la etapa pyannote:

```bash
graba-reunion --no-diarize
```

Genera también `.srt` además del `.txt`.

---

## 11. Audio (Pulse / ALSA)

### Pulse (default)

```bash
pactl list sources short
```

Elegí:

- **MIC**: fuente del micrófono (a menudo `...analog-stereo` o `mono-fallback`)
- **MON**: la que termina en `.monitor` (loopback de lo que sale por parlantes/auriculares)

El wizard lista esas fuentes y acepta número o nombre.

ffmpeg mezcla ambos con `amix` a MP3 (`libmp3lame`).

PipeWire: en la mayoría de distros modernas `pactl` y el backend `pulse` de ffmpeg siguen funcionando.

### ALSA

```bash
# En config
GRABA_AUDIO_BACKEND=alsa
GRABA_MIC=hw:0,0
GRABA_MON=hw:1,0   # o el device que corresponda
```

No hay enumerator automático: hay que poner nombres que ffmpeg entienda con `-f alsa`.

---

## 12. Transcripción y diarización

### Modo default (WhisperX)

- Modelo / idioma / device / compute / batch desde config o CLI
- Requiere `HF_TOKEN` y licencias pyannote aceptadas
- Salida principal: `.txt` con hablantes
- Artefactos extra (`.srt`, `.json`, ...) se limpian después

Workaround interno: WhisperX corre con cwd en el temp del sistema para evitar un falso positivo de seguridad de NLTK cuando el proceso parte desde `$HOME`.

### Modo `--no-diarize` (faster-whisper)

- Mismos `--language` / `--model` / device
- En CPU fuerza `int8` para compute
- Escribe `.srt` y deriva el `.txt` plano

### Modelos útiles

| Modelo | Uso |
|--------|-----|
| `large-v3` | Mejor calidad (default; pesado) |
| `medium` | Buen equilibrio |
| `small` / `tiny` | Pruebas rápidas / CPU lenta |

---

## 13. Minutas con Groq

Activación:

```bash
graba-reunion --groq
graba-reunion --enrich-only ruta/al.txt
```

Produce:

- `{base}_minuta.md` (resumen, temas, decisiones, action items, notas)
- Fila en SQLite con título, transcript, minuta, modelo

Sin `--groq`, no se llama a la API ni se toca la DB.

Idioma: alineado con `--language` / `GRABA_WHISPERX_LANGUAGE`.

---

## 14. Base de datos y consulta

Schema conceptual: una fila por sesión enriquecida (título, paths, transcript, minutes, modelo, timestamps).

```bash
graba-reunion list
#   #  grabada               título
#   1  2026-09-21 15:30:00   Sync semanal

graba-reunion show 1
graba-reunion show 1 --transcript
graba-reunion show 1 --all
```

Si la DB no existe (nunca corriste `--groq`), `list`/`show` fallan avisando la ruta esperada. Creá una reunión con `--groq` o apuntá `--db` a una DB existente.

---

## 15. CPU vs GPU

| Escenario | Config sugerida |
|-----------|-----------------|
| GPU NVIDIA OK | `GRABA_WHISPERX_DEVICE=cuda`, `COMPUTE_TYPE=float16` |
| Sin GPU / drivers rotos | `device=cpu`, `int8`; modelo `medium` o menor |
| Wizard | Detecta CUDA y sugiere `cuda` si hay |

Instalar/reparar wheels CUDA:

```bash
graba-reunion setup --install-deps -y
# o
GRABA_TORCH_INDEX=https://download.pytorch.org/whl/cu124 bash scripts/pipx-install.sh
```

`check-deps` avisa si pediste `cuda` pero torch no ve GPU.

---

## 16. Desarrollo y tests

```bash
make setup
make test
make lint
make check
```

Convenciones: ver [AGENTS.md](../AGENTS.md).

- Código: inglés
- Docs internas / comentarios: español
- Commits: Conventional Commits en inglés
- Tests mockean Groq, ffmpeg, whisperx; no requieren CUDA

Estructura relevante:

```text
src/graba_reunion/
  cli.py              # argparse
  config.py           # Settings, XDG, .env
  paths.py            # sesiones y DB
  recording.py        # ffmpeg
  setup_wizard.py
  enrichment.py       # Groq + SQLite
  transcription/      # whisperx, faster_whisper, srt
  commands/           # list, show, setup, check-deps, record
```

---

## 17. Troubleshooting

| Síntoma | Qué mirar |
|---------|-----------|
| `whisperx` no encontrado | `graba-reunion setup --install-deps` o `bash scripts/pipx-install.sh` |
| ImportError NLTK / `optparse` desde `$HOME` | Actualizá el paquete (cwd neutro en WhisperX); o ejecutá desde `/tmp` como workaround viejo |
| HF 401/403 | Token + aceptar modelos pyannote |
| ffmpeg 255 al Ctrl+C | Normal al cortar; mirá si el MP3 tiene tamaño razonable |
| Sin audio / solo un lado | `pactl list sources short`; mic vs `.monitor` |
| Torch CUDA no disponible | `setup --install-deps -y` o pasá a `cpu` |
| No encuentra config | `graba-reunion check-deps` (imprime ruta `.env`); revisá `GRABA_CONFIG` / XDG |
| `list` sin DB | Todavía no usaste `--groq`, o `--db` apunta mal |
| Groq falla | `GROQ_API_KEY`; cuota/red; transcript vacío |
| Muy lento en CPU | `--model medium` o `small` |
| Espacio en disco | Caches en `~/.cache`; modelos multi-GB |

Logs útiles:

```bash
graba-reunion check-deps
ls -la ~/.config/graba-reunion/
ls -la ~/.local/share/graba-reunion/recordings/ | tail
```

---

## 18. Preguntas frecuentes

**¿Hace falta Groq para transcribir?**  
No. Solo para minuta/`list`/`show` enriquecidos.

**¿Dónde se guarda lo que grabo si no paso `-d`?**  
En `$XDG_DATA_HOME/graba-reunion/recordings` (típicamente `~/.local/share/graba-reunion/recordings`).

**¿Puedo tener un `.env` por proyecto?**  
Sí: `GRABA_CONFIG=/ruta/al/.env` o un directorio de config.

**¿`--language` afecta a WhisperX?**  
Sí. Antes solo impactaba `--no-diarize`; ahora también al flujo con diarización.

**¿PipeWire sirve?**  
Sí, vía compat Pulse (`pactl` + `-f pulse`).

**¿Windows / macOS?**  
No está soportado; el diseño asume Linux + ffmpeg pulse/alsa.

**¿Cómo dejo de usar el `.env` del repo?**  
Corré `graba-reunion setup` una vez: migra a XDG. Después podés borrar el `.env` del clone (no lo commitees).

**¿El MP3 incluye mi voz y la de la reunión por Meet/Zoom?**  
Sí, si `GRABA_MON` es el monitor de la salida por la que escuchás la llamada, y el mic captura tu voz.

---

## Ver también

- [README.md](../README.md) - inicio rápido
- [AGENTS.md](../AGENTS.md) - notas para agentes/desarrollo
- [`.env.example`](../.env.example) - plantilla de variables
