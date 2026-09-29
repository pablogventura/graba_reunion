"""Comandos list y show, a partir de los .txt."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.config import load_settings
from graba_reunion.meetings import list_meetings, meeting_by_rank


def cmd_list(output_dir: Path) -> int:
    meetings = list_meetings(output_dir, prefix=_prefix())
    if not meetings:
        print(f"No hay reuniones en {output_dir}")
        return 0
    print(f"{'#':>3}  {'grabada':<20}  título")
    for meeting in meetings:
        extra = ""
        if meeting.duration_label:
            extra = meeting.duration_label
            if meeting.ended_label:
                extra = f"{extra} hasta {meeting.ended_label}"
            extra = f"{extra}  "
        print(f"{meeting.rank:>3}  {meeting.recorded_label:<20}  {extra}{meeting.title}")
    print(f"\nDirectorio: {output_dir}")
    return 0


def cmd_show(output_dir: Path, rank: int, *, show_transcript: bool, show_all: bool) -> int:
    if rank < 1:
        print("El número debe ser >= 1 (1 = más reciente).", file=sys.stderr)
        return 1
    meetings = list_meetings(output_dir, prefix=_prefix())
    meeting = meeting_by_rank(output_dir, rank, prefix=_prefix())
    if meeting is None:
        if not meetings:
            print(f"No hay reuniones en {output_dir}", file=sys.stderr)
        else:
            print(
                f"No existe la reunión #{rank}. Hay {len(meetings)} guardada(s); "
                "usá graba-reunion list.",
                file=sys.stderr,
            )
        return 1

    print(f"#{meeting.rank}  {meeting.title}")
    print(f"Grabada: {meeting.recorded_label}")
    if meeting.duration_label:
        print(f"Duración: {meeting.duration_label}")
    if meeting.ended_label:
        print(f"Hasta: {meeting.ended_label}")
    print(f"Archivo: {meeting.path}")
    mp3 = meeting.path.with_suffix(".mp3")
    if mp3.is_file():
        print(f"Audio:   {mp3}")
    print()

    transcript = _read(meeting.path)
    minutes = _read(meeting.minutes_path) if meeting.minutes_path else ""
    if show_all:
        if minutes:
            print(minutes)
            print()
        print("--- Transcripción ---")
        print()
        print(transcript)
    elif show_transcript or not minutes:
        print(transcript)
    else:
        print(minutes)
    return 0


def _prefix() -> str:
    return load_settings().session_prefix or "reunion"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        return f"No se pudo leer {path}: {error}\n"
