"""Regenera el JSON de frases de un MP3 ya grabado."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.commands.record import run_record_flow
from graba_reunion.config import load_settings


def cmd_phrases(output_dir: Path, mp3: Path) -> int:
    resolved = resolve_audio(output_dir, mp3)
    if resolved is None:
        print(f"No existe el MP3: {mp3}", file=sys.stderr)
        return 1
    settings = load_settings()
    return run_record_flow(
        output_dir=output_dir,
        mic=settings.graba_mic,
        mon=settings.graba_mon,
        language=settings.whisperx_language,
        model=settings.whisperx_model,
        device=None,
        transcribe_only=resolved,
        enrich_only=None,
        no_diarize=False,
        skip_transcribe=False,
        skip_groq=True,
        min_mp3_bytes=256,
        groq_model=settings.groq_model,
    )


def resolve_audio(output_dir: Path, given: Path) -> Path | None:
    expanded = given.expanduser()
    if expanded.is_file():
        return expanded.resolve()
    candidate = (output_dir / given.name).resolve()
    if candidate.is_file():
        return candidate
    return None
