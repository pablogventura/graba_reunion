from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from graba_reunion.clip_range import (
    DEFAULT_CLIP_SECONDS,
    MAX_CLIP_SECONDS,
    clip_is_long_enough,
    clip_output_path,
    extract_audio_clip,
    format_clip_preview,
    is_clip_path,
    resolve_clip_window,
)


def test_resolve_last_ten_minutes() -> None:
    start, end = resolve_clip_window(1800.0, last_seconds=DEFAULT_CLIP_SECONDS)
    assert start == 1200.0
    assert end == 1800.0


def test_resolve_clamps_when_shorter_than_window() -> None:
    start, end = resolve_clip_window(400.0, last_seconds=600.0)
    assert start == 0.0
    assert end == 400.0


def test_resolve_from_start_and_cap() -> None:
    start, end = resolve_clip_window(10_000.0, from_start=True)
    assert start == 0.0
    assert end == 10_000.0
    start, end = resolve_clip_window(10_000.0, last_seconds=MAX_CLIP_SECONDS + 100)
    assert end - start == MAX_CLIP_SECONDS


def test_clip_output_path_and_marker() -> None:
    source = Path("/tmp/reunion_2026-11-26_18-00-00.mp3")
    started = datetime(2026, 11, 26, 18, 0, 0)
    dest = clip_output_path(source, 600.0, 1200.0, started_at=started)
    assert dest.name == "reunion_2026-11-26_18-00-00_clip_18-10-00_18-20-00.mp3"
    assert is_clip_path(dest)
    assert clip_is_long_enough(0.0, 60.0)
    assert not clip_is_long_enough(0.0, 59.0)


def test_format_clip_preview_mentions_clamp() -> None:
    started = datetime(2026, 11, 26, 18, 0, 0)
    text = format_clip_preview(
        0.0,
        400.0,
        started_at=started,
        clamped_from_start=True,
    )
    assert "desde el inicio" in text
    assert "18:00:00" in text


def test_extract_audio_clip_with_ffmpeg(tmp_path: Path) -> None:
    source = tmp_path / "source.mp3"
    dest = tmp_path / "clip.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-q:a",
            "9",
            str(source),
        ],
        check=True,
    )
    extract_audio_clip(source, dest, 1.0, 3.0)
    assert dest.is_file()
    assert dest.stat().st_size > 0
