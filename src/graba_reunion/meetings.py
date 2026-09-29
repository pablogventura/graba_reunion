"""Reuniones leídas desde los .txt del directorio de grabaciones."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from graba_reunion.timing import ensure_timing, format_clock, format_duration

GENERIC_TITLES = {"minuta de reunión", "meeting minutes"}
STAMP = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class MeetingFile:
    rank: int
    path: Path
    recorded_label: str
    title: str
    minutes_path: Path | None
    duration_label: str = ""
    ended_label: str = ""


def list_meetings(directory: Path, *, prefix: str) -> list[MeetingFile]:
    if not directory.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for path in directory.glob(f"{prefix}_*.txt"):
        match = STAMP.search(path.stem)
        if match is None or not path.stem.startswith(f"{prefix}_"):
            continue
        stamp = f"{match.group(1)}_{match.group(2)}"
        found.append((stamp, path))
    found.sort(key=lambda item: item[0], reverse=True)
    meetings: list[MeetingFile] = []
    for rank, (stamp, path) in enumerate(found, start=1):
        date, clock = stamp.split("_", 1)
        minutes = _minutes_path(path)
        duration_label, ended_label = _span(path)
        meetings.append(
            MeetingFile(
                rank=rank,
                path=path,
                recorded_label=f"{date} {clock.replace('-', ':')}",
                title=_title(path, minutes),
                minutes_path=minutes if minutes.is_file() else None,
                duration_label=duration_label,
                ended_label=ended_label,
            )
        )
    return meetings


def meeting_by_rank(directory: Path, rank: int, *, prefix: str) -> MeetingFile | None:
    if rank < 1:
        return None
    meetings = list_meetings(directory, prefix=prefix)
    if rank > len(meetings):
        return None
    return meetings[rank - 1]


def _minutes_path(txt: Path) -> Path:
    return txt.with_name(f"{txt.stem}_minuta.md")


def _span(txt: Path) -> tuple[str, str]:
    timing = ensure_timing(txt.with_suffix(".mp3"))
    if timing is None or timing.duration_seconds is None:
        return "", ""
    ended = timing.ends_at()
    ended_label = format_clock(ended) if ended is not None else ""
    return format_duration(timing.duration_seconds), ended_label


def _title(txt: Path, minutes: Path) -> str:
    if minutes.is_file():
        heading = _first_specific_heading(minutes.read_text(encoding="utf-8", errors="replace"))
        if heading:
            return heading
    return txt.stem


def _first_specific_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip()
        if heading and heading.casefold() not in GENERIC_TITLES:
            return heading
    return None
