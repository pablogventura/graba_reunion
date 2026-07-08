"""Comandos list y show."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.db import get_meeting_by_rank, list_meetings


def cmd_list(db_path: Path) -> int:
    if not db_path.is_file():
        print(f"No existe la base de datos: {db_path}", file=sys.stderr)
        return 1

    meetings = list_meetings(db_path)
    if not meetings:
        print(f"No hay reuniones en {db_path}")
        return 0

    print(f"{'#':>3}  {'grabada':<20}  título")
    for meeting in meetings:
        recorded = meeting.recorded_at.replace("T", " ")[:19]
        print(f"{meeting.rank:>3}  {recorded:<20}  {meeting.title}")
    print(f"\nBase: {db_path}")
    return 0


def cmd_show(db_path: Path, rank: int, *, show_transcript: bool, show_all: bool) -> int:
    if rank < 1:
        print("El número debe ser >= 1 (1 = más reciente).", file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"No existe la base de datos: {db_path}", file=sys.stderr)
        return 1

    meeting = get_meeting_by_rank(db_path, rank)
    if meeting is None:
        total = len(list_meetings(db_path))
        if total == 0:
            print(f"No hay reuniones en {db_path}", file=sys.stderr)
        else:
            print(
                f"No existe la reunión #{rank}. Hay {total} guardada(s); "
                "usá graba-reunion list.",
                file=sys.stderr,
            )
        return 1

    recorded = meeting.recorded_at.replace("T", " ")[:19]
    print(f"#{meeting.rank}  {meeting.title}")
    print(f"Grabada: {recorded}")
    print(f"Archivo: {meeting.txt_path}")
    print(f"Audio:   {meeting.mp3_path}")
    print()

    if show_all:
        print(meeting.minutes)
        print()
        print("--- Transcripción ---")
        print()
        print(meeting.transcript)
    elif show_transcript:
        print(meeting.transcript)
    else:
        print(meeting.minutes)
    return 0
