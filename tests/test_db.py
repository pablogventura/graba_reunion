from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from graba_reunion.db import get_meeting_by_rank, insert_meeting, list_meetings


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "reunions.db"
    insert_meeting(
        db_path,
        session_base="reunion_2026-04-20_10-00-00",
        recorded_at=datetime(2026, 4, 20, 10, 0, 0),
        mp3_path=tmp_path / "old.mp3",
        txt_path=tmp_path / "old.txt",
        transcript="vieja",
        title="Reunión vieja",
        minutes="# Vieja",
        groq_model="llama-3.3-70b-versatile",
    )
    insert_meeting(
        db_path,
        session_base="reunion_2026-04-25_09-00-00",
        recorded_at=datetime(2026, 4, 25, 9, 0, 0),
        mp3_path=tmp_path / "new.mp3",
        txt_path=tmp_path / "new.txt",
        transcript="nueva",
        title="Última reunión",
        minutes="# Nueva",
        groq_model="llama-3.3-70b-versatile",
    )
    return db_path


def test_list_meetings_newest_is_rank_one(sample_db: Path) -> None:
    meetings = list_meetings(sample_db)
    assert meetings[0].rank == 1
    assert meetings[0].title == "Última reunión"
    assert meetings[1].rank == 2


def test_get_meeting_by_rank(sample_db: Path) -> None:
    meeting = get_meeting_by_rank(sample_db, 1)
    assert meeting is not None
    assert meeting.transcript == "nueva"


def test_upsert_updates_existing(tmp_path: Path) -> None:
    db_path = tmp_path / "reunions.db"
    insert_meeting(
        db_path,
        session_base="reunion_2026-04-25_09-00-00",
        recorded_at=datetime(2026, 4, 25, 9, 0, 0),
        mp3_path=tmp_path / "a.mp3",
        txt_path=tmp_path / "a.txt",
        transcript="v1",
        title="T1",
        minutes="m1",
        groq_model="llama-3.3-70b-versatile",
    )
    stored = insert_meeting(
        db_path,
        session_base="reunion_2026-04-25_09-00-00",
        recorded_at=datetime(2026, 4, 25, 9, 0, 0),
        mp3_path=tmp_path / "a.mp3",
        txt_path=tmp_path / "a.txt",
        transcript="v2",
        title="T2",
        minutes="m2",
        groq_model="llama-3.3-70b-versatile",
    )
    meeting = get_meeting_by_rank(db_path, 1)
    assert stored.rank == 1
    assert meeting is not None
    assert meeting.title == "T2"
