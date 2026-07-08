from __future__ import annotations

from datetime import datetime
from pathlib import Path

from graba_reunion.commands.list_show import cmd_list, cmd_show
from graba_reunion.db import insert_meeting


def _seed(tmp_path: Path) -> Path:
    db_path = tmp_path / "reunions.db"
    insert_meeting(
        db_path,
        session_base="reunion_2026-04-25_09-00-00",
        recorded_at=datetime(2026, 4, 25, 9, 0, 0),
        mp3_path=tmp_path / "a.mp3",
        txt_path=tmp_path / "a.txt",
        transcript="texto",
        title="Última",
        minutes="# Minuta",
        groq_model="llama-3.3-70b-versatile",
    )
    return db_path


def test_cmd_list_empty(tmp_path: Path, capsys) -> None:
    code = cmd_list(tmp_path / "missing.db")
    assert code == 1


def test_cmd_show_transcript(tmp_path: Path, capsys) -> None:
    db_path = _seed(tmp_path)
    code = cmd_show(db_path, 1, show_transcript=True, show_all=False)
    assert code == 0
    captured = capsys.readouterr()
    assert "texto" in captured.out
