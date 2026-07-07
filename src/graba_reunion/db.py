"""Persistencia SQLite de reuniones transcritas."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_base TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    mp3_path TEXT NOT NULL,
    txt_path TEXT NOT NULL,
    transcript TEXT NOT NULL,
    title TEXT NOT NULL,
    minutes TEXT NOT NULL,
    groq_model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class StoredMeeting:
    id: int
    session_base: str
    title: str
    rank: int


@dataclass(frozen=True)
class MeetingListEntry:
    rank: int
    recorded_at: str
    title: str
    session_base: str


@dataclass(frozen=True)
class MeetingDetail:
    rank: int
    db_id: int
    session_base: str
    recorded_at: str
    mp3_path: str
    txt_path: str
    title: str
    transcript: str
    minutes: str
    groq_model: str
    created_at: str


MEETINGS_ORDER = "ORDER BY recorded_at DESC, id DESC"


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def insert_meeting(
    db_path: Path,
    *,
    session_base: str,
    recorded_at: datetime,
    mp3_path: Path,
    txt_path: Path,
    transcript: str,
    title: str,
    minutes: str,
    groq_model: str,
) -> StoredMeeting:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO meetings (
                session_base, recorded_at, mp3_path, txt_path,
                transcript, title, minutes, groq_model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_base) DO UPDATE SET
                recorded_at = excluded.recorded_at,
                mp3_path = excluded.mp3_path,
                txt_path = excluded.txt_path,
                transcript = excluded.transcript,
                title = excluded.title,
                minutes = excluded.minutes,
                groq_model = excluded.groq_model,
                created_at = excluded.created_at
            """,
            (
                session_base,
                recorded_at.isoformat(),
                str(mp3_path.resolve()),
                str(txt_path.resolve()),
                transcript,
                title,
                minutes,
                groq_model,
                created_at,
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
        if row_id is None or row_id == 0:
            row = conn.execute(
                "SELECT id FROM meetings WHERE session_base = ?",
                (session_base,),
            ).fetchone()
            if row is None:
                raise RuntimeError("No se pudo obtener el id de la reunión guardada.")
            row_id = row[0]
    rank = get_meeting_rank(db_path, session_base=session_base)
    if rank is None:
        raise RuntimeError("No se pudo obtener el número de la reunión guardada.")
    return StoredMeeting(id=row_id, session_base=session_base, title=title, rank=rank)


def list_meetings(db_path: Path) -> list[MeetingListEntry]:
    if not db_path.is_file():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT recorded_at, title, session_base
            FROM meetings
            {MEETINGS_ORDER}
            """
        ).fetchall()
    return [
        MeetingListEntry(rank=index, recorded_at=row[0], title=row[1], session_base=row[2])
        for index, row in enumerate(rows, start=1)
    ]


def get_meeting_by_rank(db_path: Path, rank: int) -> MeetingDetail | None:
    if rank < 1 or not db_path.is_file():
        return None
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT id, session_base, recorded_at, mp3_path, txt_path,
                   title, transcript, minutes, groq_model, created_at
            FROM meetings
            {MEETINGS_ORDER}
            LIMIT 1 OFFSET ?
            """,
            (rank - 1,),
        ).fetchone()
    if row is None:
        return None
    return MeetingDetail(
        rank=rank,
        db_id=row[0],
        session_base=row[1],
        recorded_at=row[2],
        mp3_path=row[3],
        txt_path=row[4],
        title=row[5],
        transcript=row[6],
        minutes=row[7],
        groq_model=row[8],
        created_at=row[9],
    )


def get_meeting_rank(db_path: Path, *, session_base: str) -> int | None:
    meetings = list_meetings(db_path)
    for meeting in meetings:
        if meeting.session_base == session_base:
            return meeting.rank
    return None


def parse_session_timestamp(session_base: str) -> datetime:
    """Convierte reunion_YYYY-MM-DD_HH-MM-SS a datetime (UTC naive)."""
    prefix = "reunion_"
    if not session_base.startswith(prefix):
        return datetime.now(timezone.utc).replace(tzinfo=None)
    raw = session_base[len(prefix) :]
    try:
        return datetime.strptime(raw, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)
