"""Wizard interactivo de configuración inicial."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from getpass import getpass

from graba_reunion.config import (
    env_file_path,
    is_configured,
    is_torch_cuda_available,
    load_settings,
    missing_required_fields,
    write_env,
)
from graba_reunion.deps_installer import detect_missing_deps, install_torch_cuda
from graba_reunion.paths import default_output_dir

InputFn = Callable[[str], str]


def _default_input(prompt: str) -> str:
    return input(prompt).strip()


def _prompt_value(
    label: str,
    current: str,
    *,
    secret: bool = False,
    input_fn: InputFn = _default_input,
) -> str:
    if secret:
        hint = f" [{len(current)} chars set]" if current else ""
    else:
        hint = f" [{current}]" if current else ""
    prompt = f"{label}{hint} (Enter=mantener): "
    if secret:
        entered = getpass(prompt)
    else:
        entered = input_fn(prompt)
    return entered.strip() or current


def list_pulse_sources() -> list[tuple[str, str]]:
    try:
        output = subprocess.check_output(
            ["pactl", "list", "sources", "short"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def _suggested_device() -> tuple[str, str]:
    if is_torch_cuda_available() is True:
        return "cuda", "float16"
    return "cpu", "int8"


def run_setup_wizard(*, input_fn: InputFn = _default_input) -> int:
    settings = load_settings()
    print("Configuración de graba-reunion")
    print(f"Archivo: {env_file_path()}")
    print("Dejá Enter para conservar valores existentes.\n")

    print("HF_TOKEN es obligatorio para diarización (WhisperX).")
    hf_token = _prompt_value("HF_TOKEN", settings.hf_token, secret=True, input_fn=input_fn)
    print("GROQ_API_KEY es opcional (solo con --groq / --enrich-only).")
    groq_key = _prompt_value(
        "GROQ_API_KEY", settings.groq_api_key, secret=True, input_fn=input_fn
    )

    backend = _prompt_value(
        "GRABA_AUDIO_BACKEND (pulse/alsa)",
        settings.audio_backend,
        input_fn=input_fn,
    ).lower()
    if backend not in {"pulse", "alsa"}:
        backend = "pulse"

    if backend == "pulse":
        sources = list_pulse_sources()
        if sources:
            print("\nFuentes PulseAudio:")
            for index, (_id, name) in enumerate(sources, start=1):
                print(f"  {index}. {name}")
            mic_choice = input_fn("Número o nombre para GRABA_MIC: ")
            mon_choice = input_fn("Número o nombre para GRABA_MON: ")
            mic = _resolve_audio_choice(mic_choice, sources) or settings.graba_mic
            mon = _resolve_audio_choice(mon_choice, sources) or settings.graba_mon
        else:
            print("\nNo se pudo listar PulseAudio (pactl). Ingresá nombres manualmente.")
            mic = _prompt_value("GRABA_MIC", settings.graba_mic, input_fn=input_fn)
            mon = _prompt_value("GRABA_MON", settings.graba_mon, input_fn=input_fn)
    else:
        print("\nBackend ALSA: ingresá nombres de dispositivo (ffmpeg -f alsa).")
        mic = _prompt_value("GRABA_MIC", settings.graba_mic, input_fn=input_fn)
        mon = _prompt_value("GRABA_MON", settings.graba_mon, input_fn=input_fn)

    suggested_device, suggested_compute = _suggested_device()
    cuda = is_torch_cuda_available()
    if cuda is True:
        print("\nGPU CUDA detectada; se sugiere device=cuda.")
    elif cuda is False:
        print("\nSin CUDA usable; se sugiere device=cpu.")
    else:
        print("\nNo se pudo importar torch; se sugiere device=cpu.")

    device = _prompt_value(
        "GRABA_WHISPERX_DEVICE (cuda/cpu)",
        suggested_device,
        input_fn=input_fn,
    ).lower()
    if device not in {"cuda", "cpu"}:
        device = suggested_device
    compute_default = suggested_compute if device == suggested_device else (
        "float16" if device == "cuda" else "int8"
    )
    if settings.whisperx_device == device and settings.whisperx_compute_type:
        compute_default = settings.whisperx_compute_type

    language = _prompt_value(
        "GRABA_WHISPERX_LANGUAGE",
        settings.whisperx_language,
        input_fn=input_fn,
    )
    model = _prompt_value(
        "GRABA_WHISPERX_MODEL",
        settings.whisperx_model,
        input_fn=input_fn,
    )
    compute_type = _prompt_value(
        "GRABA_WHISPERX_COMPUTE_TYPE",
        compute_default,
        input_fn=input_fn,
    )
    batch_size = _prompt_value(
        "GRABA_WHISPERX_BATCH_SIZE",
        str(settings.whisperx_batch_size),
        input_fn=input_fn,
    )
    output_dir = _prompt_value(
        "GRABA_OUTPUT_DIR",
        settings.output_dir or str(default_output_dir()),
        input_fn=input_fn,
    )
    session_prefix = _prompt_value(
        "GRABA_SESSION_PREFIX",
        settings.session_prefix,
        input_fn=input_fn,
    )
    groq_model = settings.groq_model
    if groq_key:
        groq_model = _prompt_value(
            "GRABA_GROQ_MODEL",
            settings.groq_model,
            input_fn=input_fn,
        )

    target = write_env(
        {
            "GROQ_API_KEY": groq_key,
            "HF_TOKEN": hf_token,
            "GRABA_MIC": mic,
            "GRABA_MON": mon,
            "GRABA_AUDIO_BACKEND": backend,
            "GRABA_WHISPERX_DEVICE": device,
            "GRABA_WHISPERX_MODEL": model,
            "GRABA_WHISPERX_LANGUAGE": language,
            "GRABA_WHISPERX_COMPUTE_TYPE": compute_type,
            "GRABA_WHISPERX_BATCH_SIZE": batch_size,
            "GRABA_OUTPUT_DIR": output_dir,
            "GRABA_SESSION_PREFIX": session_prefix,
            "GRABA_GROQ_MODEL": groq_model,
            "GRABA_TORCH_INDEX": settings.torch_index,
            "GRABA_GROQ_MAX_CHARS": str(settings.groq_max_chars),
            "GRABA_GROQ_TEMPERATURE": str(settings.groq_temperature),
        }
    )
    print(f"\nConfiguración guardada en {target}")

    missing = detect_missing_deps()
    if "torch-cuda" in missing:
        print("\nTorch CUDA no detectado con device=cuda.")
        if input_fn("¿Reinstalar torch con CUDA? [s/N] ").lower() in {"s", "si", "sí", "y", "yes"}:
            return install_torch_cuda(yes=True)
    return 0


def _resolve_audio_choice(choice: str, sources: list[tuple[str, str]]) -> str:
    choice = choice.strip()
    if not choice:
        return ""
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(sources):
            return sources[index][1]
    for _id, name in sources:
        if choice == name or choice == _id:
            return name
    return choice


def ensure_configured(flows: list[str], *, input_fn: InputFn = _default_input) -> int:
    missing_flows: list[str] = []
    for flow in flows:
        if not is_configured(flow):
            missing_flows.append(flow)

    if not missing_flows:
        missing_deps = detect_missing_deps()
        if missing_deps:
            print("Faltan dependencias:", ", ".join(missing_deps))
            print("Ejecutá: graba-reunion setup --install-deps")
            if "torch-cuda" in missing_deps and input_fn(
                "¿Intentar reparar torch CUDA ahora? [s/N] "
            ).lower() in {"s", "si", "sí", "y", "yes"}:
                return install_torch_cuda(yes=True)
            return 1
        return 0

    fields: list[str] = []
    for flow in missing_flows:
        fields.extend(missing_required_fields(flow))
    unique = sorted(set(fields))
    print("Configuración incompleta. Faltan:", ", ".join(unique))
    answer = input_fn("¿Configurar ahora? [s/N] ")
    if answer.lower() not in {"s", "si", "sí", "y", "yes"}:
        print("Ejecutá: graba-reunion setup", file=sys.stderr)
        return 1
    return run_setup_wizard(input_fn=input_fn)
