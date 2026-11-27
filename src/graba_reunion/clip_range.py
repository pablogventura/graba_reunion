"""Ventanas de audio y extracción de clips mientras sigue la grabación."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from graba_reunion.timing import Pause, format_clock, wall_clock

DEFAULT_CLIP_SECONDS = 600.0
MAX_CLIP_SECONDS = 2700.0
MIN_CLIP_SECONDS = 60.0
CLIP_PRESETS_SECONDS = (300.0, 600.0, 1200.0)
CLIP_MARKER = "_clip_"


def resolve_clip_window(
    duration_seconds: float,
    *,
    last_seconds: float | None = DEFAULT_CLIP_SECONDS,
    from_start: bool = False,
) -> tuple[float, float]:
    """Devuelve (start, end) en segundos de audio dentro de [0, duration]."""
    duration = max(0.0, float(duration_seconds))
    if duration <= 0:
        return 0.0, 0.0
    if from_start or last_seconds is None:
        return 0.0, duration
    window = min(max(0.0, float(last_seconds)), MAX_CLIP_SECONDS)
    start = max(0.0, duration - window)
    return start, duration


def clip_is_long_enough(start: float, end: float) -> bool:
    return (end - start) >= MIN_CLIP_SECONDS


def is_clip_path(path: Path) -> bool:
    return CLIP_MARKER in path.stem


def clip_output_path(
    source: Path,
    start: float,
    end: float,
    *,
    started_at: datetime,
    pauses: tuple[Pause, ...] = (),
) -> Path:
    begin = wall_clock(started_at, start, pauses)
    finish = wall_clock(started_at, end, pauses)
    stamp = f"{begin.strftime('%H-%M-%S')}_{finish.strftime('%H-%M-%S')}"
    return source.with_name(f"{source.stem}{CLIP_MARKER}{stamp}.mp3")


def format_clip_preview(
    start: float,
    end: float,
    *,
    started_at: datetime,
    pauses: tuple[Pause, ...] = (),
    clamped_from_start: bool = False,
) -> str:
    length = max(0.0, end - start)
    minutes = int(length // 60)
    seconds = int(round(length - minutes * 60))
    begin = format_clock(wall_clock(started_at, start, pauses))
    finish = format_clock(wall_clock(started_at, end, pauses))
    span = f"{minutes}:{seconds:02d}"
    note = " (desde el inicio; la toma es más corta)" if clamped_from_start else ""
    return f"Se va a transcribir ~{span} (de {begin} a {finish}){note}"


def extract_audio_clip(source: Path, dest: Path, start: float, end: float) -> None:
    """Corta [start, end) del MP3. Prefiere stream copy; si falla, reencodea."""
    length = max(0.0, end - start)
    if length <= 0:
        raise ValueError("el tramo está vacío")
    dest.parent.mkdir(parents=True, exist_ok=True)
    common = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{length:.3f}",
    ]
    copy_cmd = [*common, "-c", "copy", str(dest)]
    try:
        subprocess.run(copy_cmd, check=True, timeout=120)
        if dest.is_file() and dest.stat().st_size > 0:
            return
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        dest.unlink(missing_ok=True)
    reencode = [
        *common,
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(dest),
    ]
    subprocess.run(reencode, check=True, timeout=300)
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise RuntimeError(f"ffmpeg no escribió {dest.name}")
