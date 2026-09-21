"""Reparación de dependencias Python (torch CUDA)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from graba_reunion.config import (
    is_faster_whisper_importable,
    is_torch_cuda_available,
    load_settings,
    project_root,
    resolve_whisperx_bin,
    torch_cuda_index,
)


def detect_missing_deps() -> list[str]:
    missing: list[str] = []
    if resolve_whisperx_bin() is None:
        missing.append("whisperx")
    if not is_faster_whisper_importable():
        missing.append("faster-whisper")
    cuda = is_torch_cuda_available()
    settings = load_settings()
    if settings.whisperx_device == "cuda" and cuda is False:
        missing.append("torch-cuda")
    return missing


def _pip_executable() -> Path:
    local = project_root() / ".venv" / "bin" / "pip"
    if local.is_file():
        return local
    return Path(sys.executable).parent / "pip"


def install_torch_cuda(*, yes: bool = False) -> int:
    pip = _pip_executable()
    index = torch_cuda_index()
    command = [
        str(pip),
        "install",
        "torch",
        "torchaudio",
        "--index-url",
        index,
    ]
    if not yes:
        answer = input(f"¿Reinstalar torch/torchaudio desde {index}? [s/N] ").strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Instalación cancelada.")
            return 1
    print(f"Instalando torch/torchaudio ({index})…")
    return subprocess.run(command, check=False).returncode


def install_project_deps(*, yes: bool = False) -> int:
    pip = _pip_executable()
    index = torch_cuda_index()
    command = [
        str(pip),
        "install",
        "-e",
        f"{project_root()}[dev]",
        "--extra-index-url",
        index,
    ]
    if not yes:
        answer = input("¿Instalar dependencias del proyecto? [s/N] ").strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Instalación cancelada.")
            return 1
    print("Instalando graba-reunion y dependencias…")
    return subprocess.run(command, check=False).returncode
