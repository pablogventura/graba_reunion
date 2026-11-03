"""Transcribe uno o más archivos de audio o video ya existentes."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from graba_reunion.commands.record import run_record_flow
from graba_reunion.config import load_settings


def cmd_transcribe(paths: list[Path], *, open_viewer: bool = True) -> int:
    settings = load_settings()
    exit_code = 0
    done: list[Path] = []
    for given in paths:
        resolved = given.expanduser()
        if not resolved.is_file():
            print(f"No existe el archivo: {given}", file=sys.stderr)
            exit_code = 1
            continue
        media = resolved.resolve()
        result = run_record_flow(
            output_dir=media.parent,
            mic=settings.graba_mic,
            mon=settings.graba_mon,
            language=settings.whisperx_language,
            model=settings.whisperx_model,
            device=None,
            transcribe_only=media,
            enrich_only=None,
            no_diarize=False,
            skip_transcribe=False,
            skip_groq=True,
            min_mp3_bytes=256,
            groq_model=settings.groq_model,
        )
        if result != 0:
            exit_code = result
            continue
        if media.with_suffix(".txt").is_file():
            done.append(media)
    if open_viewer:
        _open_finished(done)
    return exit_code


def _open_finished(media_files: list[Path]) -> None:
    """Abre el visor una vez por carpeta, en el primer archivo que salió bien."""
    opened: set[Path] = set()
    for media in media_files:
        directory = media.parent
        if directory in opened:
            continue
        opened.add(directory)
        _open_viewer(directory, media.stem)


def _open_viewer(directory: Path, meeting_id: str) -> None:
    binary = shutil.which("graba-reunion") or sys.argv[0]
    subprocess.Popen(
        [binary, "view", "-d", str(directory), "--id", meeting_id],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
