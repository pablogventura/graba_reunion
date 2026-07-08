"""Comando check-deps."""
from __future__ import annotations

from graba_reunion.config import (
    env_file_path,
    ffmpeg_available,
    is_faster_whisper_importable,
    is_torch_cuda_available,
    load_settings,
    missing_required_fields,
    resolve_whisperx_bin,
)
from graba_reunion.deps_installer import detect_missing_deps


def cmd_check_deps() -> int:
    settings = load_settings()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("ffmpeg", ffmpeg_available(), "sudo apt install ffmpeg"))
    whisperx = resolve_whisperx_bin()
    checks.append(
        (
            "whisperx",
            whisperx is not None,
            "scripts/pipx-install.sh o make setup",
        )
    )
    checks.append(
        (
            "faster-whisper",
            is_faster_whisper_importable(),
            "scripts/pipx-install.sh o make setup",
        )
    )
    checks.append(
        (
            "GROQ_API_KEY",
            bool(settings.groq_api_key),
            "graba-reunion setup",
        )
    )
    checks.append(
        (
            "HF_TOKEN",
            bool(settings.hf_token),
            "graba-reunion setup + aceptar modelos pyannote en HF",
        )
    )
    checks.append(
        (
            "GRABA_MIC",
            bool(settings.graba_mic),
            "graba-reunion setup",
        )
    )
    checks.append(
        (
            "GRABA_MON",
            bool(settings.graba_mon),
            "graba-reunion setup",
        )
    )

    print("Dependencias:")
    essential_ok = True
    for name, ok, hint in checks:
        status = "OK" if ok else "FALTA"
        print(f"  [{status}] {name}")
        if not ok:
            print(f"         -> {hint}")
            if name in {"ffmpeg", "whisperx", "GROQ_API_KEY", "HF_TOKEN"}:
                essential_ok = False

    cuda = is_torch_cuda_available()
    if settings.whisperx_device == "cuda":
        if cuda is True:
            print("  [OK] torch CUDA")
        elif cuda is False:
            print("  [WARN] torch CUDA no disponible (device=cuda)")
            print("         -> scripts/pipx-install.sh")
        else:
            print("  [WARN] torch no importable")
            print("         -> scripts/pipx-install.sh")

    missing_deps = detect_missing_deps()
    if missing_deps:
        print(f"\nPaquetes faltantes: {', '.join(missing_deps)}")
        print("Reparar: graba-reunion setup --install-deps")

    if env_file_path().is_file():
        print(f"\n.env: {env_file_path()}")
    else:
        print("\n.env: no existe (ejecutá graba-reunion setup)")

    for flow in ("record", "diarize", "groq"):
        missing = missing_required_fields(flow)
        if missing:
            print(f"Flujo {flow}: faltan {', '.join(missing)}")

    return 0 if essential_ok else 1
