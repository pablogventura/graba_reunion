"""Wizard interactivo de configuración inicial."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from getpass import getpass

from graba_reunion.config import (
    env_file_path,
    is_configured,
    load_settings,
    missing_required_fields,
    write_env,
)
from graba_reunion.deps_installer import detect_missing_deps, install_torch_cuda

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
    hint = f" [{len(current)} chars set]" if current else ""
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


def run_setup_wizard(*, input_fn: InputFn = _default_input) -> int:
    settings = load_settings()
    print("Configuración de graba-reunion")
    print("Dejá Enter para conservar valores existentes.\n")

    groq_key = _prompt_value("GROQ_API_KEY", settings.groq_api_key, secret=True, input_fn=input_fn)
    hf_token = _prompt_value("HF_TOKEN", settings.hf_token, secret=True, input_fn=input_fn)

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

    device = _prompt_value(
        "GRABA_WHISPERX_DEVICE (cuda/cpu)",
        settings.whisperx_device,
        input_fn=input_fn,
    )

    write_env(
        {
            "GROQ_API_KEY": groq_key,
            "HF_TOKEN": hf_token,
            "GRABA_MIC": mic,
            "GRABA_MON": mon,
            "GRABA_WHISPERX_DEVICE": device,
            "GRABA_GROQ_MODEL": settings.groq_model,
            "GRABA_WHISPERX_MODEL": settings.whisperx_model,
            "GRABA_WHISPERX_LANGUAGE": settings.whisperx_language,
            "GRABA_WHISPERX_COMPUTE_TYPE": settings.whisperx_compute_type,
            "GRABA_WHISPERX_BATCH_SIZE": str(settings.whisperx_batch_size),
            "GRABA_MODEL": settings.faster_whisper_model,
            "GRABA_LANGUAGE": settings.faster_whisper_language,
        }
    )
    print(f"\nConfiguración guardada en {env_file_path()}")

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
            print("Ejecutá: scripts/pipx-install.sh o make setup")
            if input_fn("¿Intentar reparar torch CUDA ahora? [s/N] ").lower() in {
                "s",
                "si",
                "sí",
                "y",
                "yes",
            }:
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
