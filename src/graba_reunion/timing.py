"""Inicio, duración y pausas de una grabación, para pasar de offset a hora de reloj."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

STAMP = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$")


@dataclass(frozen=True)
class Pause:
    at_seconds: float
    paused_seconds: float


@dataclass(frozen=True)
class RecordingTiming:
    started_at: datetime
    duration_seconds: float | None
    pauses: tuple[Pause, ...] = ()

    def ends_at(self) -> datetime | None:
        if self.duration_seconds is None:
            return None
        return wall_clock(self.started_at, self.duration_seconds, self.pauses)


def timing_path(audio: Path) -> Path:
    return audio.with_name(f"{audio.stem}.timing.json")


def mark_started(audio: Path, started_at: datetime | None = None) -> RecordingTiming:
    moment = _floor_seconds(started_at or datetime.now())
    current = read_timing(audio)
    pauses = current.pauses if current is not None else ()
    duration = current.duration_seconds if current is not None else None
    stored = RecordingTiming(started_at=moment, duration_seconds=duration, pauses=pauses)
    _write(audio, stored)
    return stored


def mark_duration(audio: Path, duration_seconds: float) -> None:
    current = read_timing(audio)
    started = current.started_at if current is not None else started_from_stem(audio.stem)
    if started is None:
        return
    pauses = current.pauses if current is not None else ()
    _write(
        audio,
        RecordingTiming(
            started_at=started,
            duration_seconds=round(duration_seconds, 3),
            pauses=pauses,
        ),
    )


def add_pause(audio: Path, at_seconds: float, paused_seconds: float) -> None:
    if paused_seconds <= 0:
        return
    current = read_timing(audio)
    started = current.started_at if current is not None else started_from_stem(audio.stem)
    if started is None:
        return
    pauses = list(current.pauses) if current is not None else []
    pauses.append(Pause(at_seconds=round(at_seconds, 3), paused_seconds=round(paused_seconds, 3)))
    duration = current.duration_seconds if current is not None else None
    _write(
        audio,
        RecordingTiming(
            started_at=started,
            duration_seconds=duration,
            pauses=tuple(pauses),
        ),
    )


def load_recording_timing(audio: Path | None) -> RecordingTiming | None:
    """Lee el sidecar, o arma el inicio solo con la marca del nombre del archivo."""
    if audio is None:
        return None
    stored = read_timing(audio)
    if stored is not None:
        return stored
    started = started_from_stem(audio.stem)
    if started is None:
        return None
    return RecordingTiming(started_at=started, duration_seconds=None)


def read_timing(audio: Path) -> RecordingTiming | None:
    path = timing_path(audio)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw_start = payload.get("started_at")
    if not isinstance(raw_start, str):
        return None
    try:
        started = datetime.fromisoformat(raw_start)
    except ValueError:
        return None
    raw_duration = payload.get("duration_seconds")
    duration = float(raw_duration) if isinstance(raw_duration, (int, float)) else None
    pauses: list[Pause] = []
    for item in payload.get("pauses") or []:
        if not isinstance(item, dict):
            continue
        at_seconds = item.get("at_seconds")
        paused = item.get("paused_seconds")
        if isinstance(at_seconds, (int, float)) and isinstance(paused, (int, float)):
            pauses.append(Pause(at_seconds=float(at_seconds), paused_seconds=float(paused)))
    return RecordingTiming(started_at=started, duration_seconds=duration, pauses=tuple(pauses))


def ensure_timing(audio: Path) -> RecordingTiming | None:
    """Completa el sidecar con el nombre del archivo y, si hace falta, ffprobe."""
    current = read_timing(audio)
    started = current.started_at if current is not None else started_from_stem(audio.stem)
    if started is None:
        return None
    duration = current.duration_seconds if current is not None else None
    pauses = current.pauses if current is not None else ()
    if duration is None and audio.is_file():
        duration = probe_duration_seconds(audio)
    stored = RecordingTiming(started_at=started, duration_seconds=duration, pauses=pauses)
    if current != stored and audio.parent.is_dir():
        _write(audio, stored)
    return stored


def started_from_stem(stem: str) -> datetime | None:
    match = STAMP.search(stem)
    if match is None:
        return None
    return datetime.strptime(
        f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4)}",
        "%Y-%m-%d %H:%M:%S",
    )


def wall_clock(
    started_at: datetime,
    offset_seconds: float,
    pauses: tuple[Pause, ...] = (),
) -> datetime:
    extra = sum(pause.paused_seconds for pause in pauses if pause.at_seconds <= offset_seconds)
    return started_at + timedelta(seconds=offset_seconds + extra)


def format_clock(moment: datetime) -> str:
    return moment.strftime("%H:%M:%S")


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min"
    return f"{secs} s"


def probe_duration_seconds(path: Path) -> float | None:
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return float(output.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None


def _floor_seconds(moment: datetime) -> datetime:
    return moment.replace(microsecond=0)


def _write(audio: Path, timing: RecordingTiming) -> None:
    path = timing_path(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "started_at": timing.started_at.isoformat(timespec="seconds"),
        "duration_seconds": timing.duration_seconds,
        "pauses": [
            {"at_seconds": pause.at_seconds, "paused_seconds": pause.paused_seconds}
            for pause in timing.pauses
        ],
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)
