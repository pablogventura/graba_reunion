"""Unir varios archivos de audio/video en un solo MP3 para transcribirlos juntos."""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def joined_output_path(directory: Path, sources: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if len(sources) == 1:
        stem = sources[0].stem
    else:
        stem = f"{sources[0].stem}_y_{len(sources) - 1}_mas"
    base = f"{stem}_junto_{stamp}.mp3"
    return _unique(directory / base)


def join_media_files(sources: list[Path], destination: Path) -> Path:
    """Concatena pistas de audio con ffmpeg (reencode a MP3)."""
    if not sources:
        raise ValueError("No hay archivos para unir.")
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"No existe: {missing[0]}")
    if len(sources) == 1:
        if destination.resolve() == sources[0].resolve():
            return sources[0]
        shutil.copy2(sources[0], destination)
        return destination

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Hace falta ffmpeg para unir audios.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for path in sources:
        command.extend(["-i", str(path)])
    labels = "".join(f"[{index}:a]" for index in range(len(sources)))
    filter_complex = f"{labels}concat=n={len(sources)}:v=0:a=1[out]"
    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(destination),
        ]
    )
    print(f"Uniendo {len(sources)} archivos -> {destination.name}", flush=True)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as error:
        raise RuntimeError(f"No se pudo ejecutar ffmpeg: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        message = "ffmpeg no pudo unir los archivos."
        if detail:
            message = f"{message} {detail}"
        raise RuntimeError(message)
    if not destination.is_file() or destination.stat().st_size <= 0:
        raise RuntimeError("El MP3 unido quedó vacío.")
    return destination


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
