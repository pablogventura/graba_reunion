"""Transcripción con diarización vía WhisperX."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from graba_reunion.config import Settings, load_settings, resolve_whisperx_bin

WHISPERX_SIDE_EXTENSIONS = (".srt", ".json", ".vtt", ".tsv")


def cleanup_whisperx_side_artifacts(output_dir: Path, base: str) -> None:
    for ext in WHISPERX_SIDE_EXTENSIONS:
        side = output_dir / f"{base}{ext}"
        if side.is_file():
            side.unlink()


def validate_diarization_prereqs() -> str | None:
    settings = load_settings()
    if not settings.hf_token:
        return (
            "HF_TOKEN no configurado. Exportalo, definilo en .env o ejecutá: graba-reunion setup"
        )
    if resolve_whisperx_bin() is None:
        return (
            "No se encontró whisperx. Ejecutá: scripts/pipx-install.sh o make setup"
        )
    return None


def transcribe_with_diarization(
    mp3: Path,
    *,
    output_dir: Path,
    settings: Settings | None = None,
) -> None:
    active = settings or load_settings()
    whisperx = resolve_whisperx_bin()
    if whisperx is None:
        raise FileNotFoundError(
            "No se encontró whisperx. Ejecutá: scripts/pipx-install.sh o make setup"
        )

    subprocess.run(
        [
            str(whisperx),
            str(mp3),
            "--model",
            active.whisperx_model,
            "--language",
            active.whisperx_language,
            "--diarize",
            "--hf_token",
            active.hf_token,
            "--device",
            active.whisperx_device,
            "--compute_type",
            active.whisperx_compute_type,
            "--batch_size",
            str(active.whisperx_batch_size),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "txt",
        ],
        check=True,
        env={**os.environ, "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "true"},
    )
