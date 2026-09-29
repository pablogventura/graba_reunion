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
14. [Consulta y búsqueda](#14-consulta-y-búsqueda)
15. [CPU vs GPU](#15-cpu-vs-gpu)
16. [Desarrollo y tests](#16-desarrollo-y-tests)
17. [Troubleshooting](#17-troubleshooting)
18. [Preguntas frecuentes](#18-preguntas-frecuentes)
19. [Indicador y autograbación](#19-indicador-y-autograbación)

---

## 1. Qué hace

`graba-reunion` es una CLI para Linux que:

1. **Graba** el micrófono y el audio de salida del sistema (monitor Pulse/ALSA) en un MP3.
2. **Transcribe** con diarización de hablantes (WhisperX + pyannote) o, si preferís, sin diarización (`faster-whisper`).
3. **Opcionalmente** genera título y minuta con Groq, en un markdown junto al `.txt`.

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
                              {prefijo}_...._minuta.md
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
8. Directorio de salida y prefijo de archivos
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

Default del prefijo: `reunion`. `list` y `show` leen `{prefijo}_AAAA-MM-DD_HH-MM-SS.txt`. El título sale del primer encabezado específico de `{prefijo}_..._minuta.md`. Si el encabezado es solo "Minuta de reunión" o "Meeting minutes", usa el nombre del archivo.

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

Además genera `{base}_minuta.md`. El archivo empieza con el título que devolvió Groq.

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

### Grabar solo cuando hay una llamada

`graba-reunion-mic` deja un icono en la barra. Si Discord, Meet, Teams u otra app abre el micrófono, a los 3 segundos empieza a grabar (mic + monitor). Al colgar, espera 10 segundos y corta. Si duró menos de un minuto, borra el MP3. Si duró un minuto o más, transcribe sin Groq.

Detalle en [Indicador y autograbación](#19-indicador-y-autograbación).

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

Lista reuniones a partir de los `.txt` (rank, fecha, título). El 1 es la más reciente.

```bash
graba-reunion list
```

### `show N`

Muestra la reunión número `N` (1 = más reciente). Si hay minuta, la muestra; si no, el `.txt`.

```bash
graba-reunion show 1              # minuta, o el txt si no hay minuta
graba-reunion show 1 --transcript
graba-reunion show 2 --all        # minuta + transcripción
```

### `search`

Busca en los `.txt`. El modo por defecto es por tema (embeddings locales, modelo `paraphrase-multilingual-MiniLM-L12-v2`). La primera búsqueda de tema descarga el modelo. El índice vive en `~/.local/share/graba-reunion/search-cache.json` y se rehace si cambia el `.txt` o si se borra ese JSON.

```bash
graba-reunion search "entrega del laboratorio"
graba-reunion search --word "acta"
graba-reunion search --participant Pablo "presupuesto"
graba-reunion search --participant Pablo
```

`--word` es coincidencia literal, sin distinguir mayúsculas. `--participant` se puede combinar con tema o palabra. Sin texto, lista intervenciones de esa persona. `--json` imprime los resultados para el indicador.

---

## 8. Referencia de opciones

Aplican al flujo de grabación/transcripción (root o `record`):

| Opción | Descripción |
|--------|-------------|
| `-d`, `--output-dir` | Directorio de salida. Default: data dir XDG o `GRABA_OUTPUT_DIR` |
| `--mic` / `--mon` | Fuentes de audio (override de config) |
| `--language` | Idioma ISO (`es`, `en`, ...). Aplica a WhisperX y a `--no-diarize` |
| `--model` | Modelo (`large-v3`, `medium`, `tiny`, ...) |
| `--device` | `cuda` o `cpu` (override de `GRABA_WHISPERX_DEVICE`) |
| `--transcribe-only MP3` | No graba; solo transcribe ese archivo |
| `--no-diarize` | Usa faster-whisper (sin speakers) |
| `--skip-transcribe` | Solo graba el MP3 |
| `--min-mp3-bytes N` | Mínimo de bytes para intentar transcribir (default 256) |
| `--groq` | Escribe `{base}_minuta.md` |
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
- Si hay perfiles de voz (`graba-reunion voices`), el hablante que coincide sale con su nombre. El resto sigue como `SPEAKER_00`
- Artefactos extra (`.srt`, `.json`, ...) se limpian después

Workaround interno: WhisperX corre con cwd en el temp del sistema para evitar un falso positivo de seguridad de NLTK cuando el proceso parte desde `$HOME`.

### Nombres de voz

`graba-reunion voices` diariza los MP3 que ya están en el directorio de salida, agrupa voces parecidas y deja un clip de cada una en `~/.local/share/graba-reunion/voices/clips/`. En `nombres.txt` se completa el nombre (`1=Pablo`). El mismo nombre en dos líneas las junta en un perfil. `1=-` descarta esa muestra (música u otro ruido) y no la usa para poner un nombre.

```bash
graba-reunion voices
# editar ~/.local/share/graba-reunion/voices/nombres.txt
graba-reunion voices --apply
```

A partir de ahí, cada transcripción nueva compara la voz con esos perfiles. No reescribe los `.txt` viejos. Una voz desconocida, o una toma muy distinta, sigue como `SPEAKER_XX`.

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

- `{base}_minuta.md` (título, resumen, temas, decisiones, action items, notas)

Sin `--groq`, no se llama a la API.

Idioma: alineado con `--language` / `GRABA_WHISPERX_LANGUAGE`.

---

## 14. Consulta y búsqueda

`list` y `show` leen los `.txt` del directorio de salida. El título de la lista es el primer encabezado de la minuta que no sea genérico. Si no hay minuta, el título es el nombre del archivo.

```bash
graba-reunion list
#   #  grabada               título
#   1  2026-09-21 15:30:00   Sync semanal

graba-reunion show 1
graba-reunion show 1 --transcript
graba-reunion show 1 --all
graba-reunion search "entrega del laboratorio"
```

La búsqueda por tema no usa la red de Groq. Guarda vectores en `search-cache.json`, al lado de los datos de la app, no en una base.

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
  paths.py            # sesiones
  meetings.py         # list y show desde los .txt
  recording.py        # ffmpeg
  setup_wizard.py
  enrichment.py       # minuta Groq
  search.py           # tema, palabra, participante
  transcription/      # whisperx, faster_whisper, srt
  commands/           # list, show, setup, check-deps, record, voices, search
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
| `list` vacío | No hay `{prefijo}_AAAA-MM-DD_HH-MM-SS.txt` en el directorio de salida |
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
No. Solo para la minuta. `list` y `show` leen los `.txt` aunque no haya Groq.

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

**¿Un mensaje de voz corto queda grabado?**  
El indicador lo graba, pero si dura menos de 60 segundos borra el MP3 y no transcribe.

**¿Por qué Meet figura como Firefox o Chrome?**  
PipeWire ve el proceso que abre el micrófono, no el nombre del sitio.

---

## 19. Indicador y autograbación

`graba-reunion-mic` es un icono de GNOME (AppIndicator) que arranca con la sesión gráfica.

| Icono | Significado |
|-------|-------------|
| Micrófono tachado | No está grabando (aunque otra app use el micrófono, o haya una transcripción) |
| Micrófono activo | Hay una grabación en curso, también si está en pausa |

El menú lista la app y el dispositivo (por ejemplo `Discord - HyperX...`), y debajo los nombres de las transcripciones (`.txt`) de las últimas 24 horas. Un clic en un nombre abre ese archivo con el editor de texto predeterminado.

Con el micrófono libre, **Grabar** empieza enseguida, sin esperar los 3 segundos. Si nadie más usa el micrófono, la toma se corta sola tras 10 minutos de silencio en el audio. Si después otra app abre el micrófono, al colgar vuelve la regla de los 10 segundos. Durante la grabación aparecen **Pausar**, **Detener** y **Cancelar**. Pausar manda SIGSTOP al proceso y a ffmpeg: el MP3 sigue siendo el mismo y el silencio no corta la toma. Si la llamada termina mientras está en pausa, avisa una vez y no cierra solo. Reanudar manda SIGCONT y el temporizador de silencio vuelve a cero. Detener (también **Salir**) reanuda si hacía falta y manda SIGTERM; después vale la regla de los 60 segundos. Cancelar abre un cuadro de confirmación: si aceptás, corta, borra el MP3 y no transcribe.

**Buscar** abre un diálogo (tema, palabra y participante opcional). La búsqueda corre en segundo plano con `graba-reunion search --json`. Un clic en un resultado abre el `.txt`.

### Cuándo graba

Cuenta cualquier stream de captura de PipeWire o Pulse hacia un micrófono (`Stream/Input` o `Stream/Input/Audio`). No cuenta:

- el monitor de salida (`*.monitor`)
- PipeWire con la tarjeta abierta pero sin una app leyendo audio
- el `ffmpeg` de la grabación que el propio indicador lanzó

No hay lista de aplicaciones. Meet en el navegador aparece como Chrome, Chromium o Firefox. Teams de escritorio aparece como su proceso. Discord (también Flatpak) aparece como `Discord`.

Tiempos:

- 3 segundos de uso continuo antes de empezar
- 10 segundos sin apps ajenas antes de cortar (un mute que deja el stream abierto no corta)
- menos de 60 segundos: se borra el MP3 y no hay transcripción
- 60 segundos o más: `graba-reunion --transcribe-only` (sin Groq)

La grabación usa el mismo mic y monitor de la config (`GRABA_MIC`, `GRABA_MON`). Los archivos van al directorio de salida habitual.

### Si se corta la luz o se mata el indicador

En cuanto el CLI imprime la ruta del MP3, el indicador deja una marca en `~/.local/share/graba-reunion/pending/`. Al volver a entrar a la sesión, si esa grabación no tiene `.txt`:

- menos de 60 segundos: borra el MP3 y avisa
- 60 segundos o más (o si no se puede medir la duración): lanza `--transcribe-only`

La marca se borra cuando existe el `.txt`. Si la transcripción falla, queda y se reintenta la próxima vez. El resultado sale como notificación de GNOME (libnotify), no por la consola. Un clic en el aviso de transcripción lista abre el `.txt` con el editor predeterminado. El detalle sigue en el log.

### Arranque al iniciar sesión

El archivo es `~/.config/autostart/graba-reunion-mic.desktop`. El `Exec` apunta a `scripts/graba-reunion-mic`, que usa el Python del sistema (ahí está PyGObject) y el código del repositorio. Grabar y transcribir lo hace el `graba-reunion` instalado. Arranca al entrar a la sesión, no antes del login.

Para lanzarlo a mano:

```bash
graba-reunion-mic
```

Log: `~/.local/share/graba-reunion/mic-indicator.log`.

Hace falta el paquete del indicador (`gir1.2-ayatanaappindicator3-0.1` en Debian/Ubuntu) y una extensión de iconos en la barra si el escritorio no los muestra solo.

---

## Ver también

- [README.md](../README.md) - inicio rápido
- [AGENTS.md](../AGENTS.md) - notas para agentes/desarrollo
- [`.env.example`](../.env.example) - plantilla de variables
