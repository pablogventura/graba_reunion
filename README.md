# graba-reunion

Graba reuniones (micrófono + audio del monitor), transcribe con diarización ([WhisperX](https://github.com/m-bain/whisperX)) y, si querés (`--groq`), genera título + minuta con [Groq](https://groq.com/).

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

# Con minuta Groq
graba-reunion --groq
```

Salida por defecto: `~/.local/share/graba-reunion/recordings/`  
Config: `~/.config/graba-reunion/.env`

## Qué hace

| Paso | Default | Opcional |
|------|---------|----------|
| Grabar mic + monitor (ffmpeg) | sí | `--skip-transcribe` solo audio |
| Transcribir con speakers (WhisperX) | sí | `--no-diarize` (faster-whisper) |
| Nombres en vez de `SPEAKER_00` | no | `graba-reunion voices` |
| Minuta (Groq) | no | `--groq` / `--enrich-only` |

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
graba-reunion --groq               # + minuta
graba-reunion --language en --model medium --device cpu
graba-reunion --transcribe-only archivo.mp3
graba-reunion --enrich-only archivo.txt
graba-reunion list
graba-reunion show 1               # 1 = más reciente
graba-reunion show 1 --transcript
graba-reunion search "entrega del laboratorio"
graba-reunion search --word "acta"
graba-reunion search --participant Pablo "presupuesto"
graba-reunion setup
graba-reunion setup --install-deps -y
graba-reunion check-deps
graba-reunion-mic              # icono: graba solo cuando otra app usa el mic
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
- `GRABA_OUTPUT_DIR`, `GRABA_SESSION_PREFIX`

## Indicador automático

`graba-reunion-mic` graba la reunión cuando otra app abre el micrófono (Discord, Meet, Teams, etc.). El icono se ve en uso solo mientras está grabando; si no, queda como micrófono libre aunque otra app lo tenga abierto. Espera 3 segundos para arrancar y 10 para cortar al colgar. Si la toma dura menos de un minuto, borra el audio. Si dura más, transcribe sin Groq. El menú del icono lista las transcripciones de las últimas 24 horas; un clic en el aviso o en el nombre abre el `.txt` con el editor predeterminado.

Con el micrófono libre, **Grabar** arranca una toma a mano. Si nadie más usa el micrófono, se corta sola tras 10 minutos de silencio en el audio. Si otra app lo abre y lo suelta, vuelve el corte a los 10 segundos. Mientras graba: **Pausar** congela el audio (el silencio no corta la toma), **Detener** aplica la regla de duración y **Cancelar** abre un cuadro para confirmar antes de borrar el MP3. **Salir** equivale a Detener. **Buscar** abre un diálogo de tema, palabra o participante.

Arranca con la sesión gráfica (`~/.config/autostart/graba-reunion-mic.desktop`). Si quedó un MP3 sin transcribir (corte de luz, cierre brusco), al volver lo transcribe y avisa con una notificación de GNOME. Log en `~/.local/share/graba-reunion/mic-indicator.log`.

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
