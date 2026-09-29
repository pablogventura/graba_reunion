"""Transcripción con diarización vía WhisperX."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from graba_reunion.config import Settings, load_settings, resolve_whisperx_bin
from graba_reunion.voices import write_named_transcript

WHISPERX_SIDE_EXTENSIONS = (".srt", ".json", ".vtt", ".tsv")


def whisperx_subprocess_cwd() -> str:
    """CWD neutro para WhisperX/NLTK.

    NLTK 3.10+ bloquea imports cuyo origen esté bajo el CWD (anti-hijacking).
    Si el proceso corre desde $HOME y Python vive en ~/.local, el stdlib
    (p. ej. optparse) cae en ese filtro y falla. Un temp dir evita el falso
    positivo; las rutas del comando ya son absolutas.
    """
    return tempfile.gettempdir()


def cleanup_whisperx_side_artifacts(output_dir: Path, base: str) -> None:
    for ext in WHISPERX_SIDE_EXTENSIONS:
        side = output_dir / f"{base}{ext}"
        if side.is_file():
            side.unlink()


def validate_diarization_prereqs() -> str | None:
    settings = load_settings()
    if not settings.hf_token:
        return (
            "HF_TOKEN no configurado. Exportalo, definilo en la config "
            "(~/.config/graba-reunion/.env) o ejecutá: graba-reunion setup"
        )
    if resolve_whisperx_bin() is None:
        return (
            "No se encontró whisperx. Ejecutá: graba-reunion setup --install-deps "
            "o bash scripts/pipx-install.sh"
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
            "No se encontró whisperx. Ejecutá: graba-reunion setup --install-deps "
            "o bash scripts/pipx-install.sh"
        )

    subprocess.run(
        [
            str(whisperx),
            str(mp3.resolve()),
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
            str(output_dir.resolve()),
            "--output_format",
            "json",
            "--speaker_embeddings",
        ],
        check=True,
        cwd=whisperx_subprocess_cwd(),
        env={**os.environ, "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "true"},
    )
    json_path = output_dir.resolve() / f"{mp3.stem}.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"WhisperX no escribió {json_path.name}")
    write_named_transcript(json_path, output_dir.resolve() / f"{mp3.stem}.txt")
