from __future__ import annotations

from datetime import datetime
from pathlib import Path

from graba_reunion.timing import (
    Pause,
    add_pause,
    mark_duration,
    mark_started,
    read_timing,
    started_from_stem,
    wall_clock,
)


def test_wall_clock_adds_pauses_before_the_phrase() -> None:
    started = datetime(2026, 9, 29, 13, 0, 0)
    pauses = (Pause(at_seconds=60, paused_seconds=120),)
    assert wall_clock(started, 30, pauses) == datetime(2026, 9, 29, 13, 0, 30)
    assert wall_clock(started, 90, pauses) == datetime(2026, 9, 29, 13, 3, 30)


def test_timing_file_keeps_start_duration_and_pause(tmp_path: Path) -> None:
    audio = tmp_path / "reunion_2026-09-29_13-09-20.mp3"
    audio.write_bytes(b"x")
    mark_started(audio, datetime(2026, 9, 29, 13, 9, 20))
    add_pause(audio, 40, 15)
    mark_duration(audio, 90)
    stored = read_timing(audio)
    assert stored is not None
    assert stored.started_at == datetime(2026, 9, 29, 13, 9, 20)
    assert stored.duration_seconds == 90
    assert stored.pauses == (Pause(at_seconds=40, paused_seconds=15),)
    assert started_from_stem(audio.stem) == datetime(2026, 9, 29, 13, 9, 20)
