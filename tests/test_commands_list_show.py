from __future__ import annotations

from pathlib import Path

from graba_reunion.commands.list_show import cmd_list, cmd_show


def _seed(directory: Path) -> None:
    older = directory / "reunion_2026-04-25_09-00-00.txt"
    newer = directory / "reunion_2026-04-26_10-00-00.txt"
    older.write_text("[Pablo]: texto viejo\n", encoding="utf-8")
    newer.write_text("[Pablo]: texto nuevo\n", encoding="utf-8")
    (directory / "reunion_2026-04-26_10-00-00_minuta.md").write_text(
        "# Minuta de reunión\n\n# Entrega del laboratorio\n",
        encoding="utf-8",
    )


def test_cmd_list_empty(tmp_path: Path, capsys) -> None:
    code = cmd_list(tmp_path / "missing")
    assert code == 0
    assert "No hay reuniones" in capsys.readouterr().out


def test_cmd_list_uses_minutes_title(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.commands.list_show._prefix", lambda: "reunion")
    _seed(tmp_path)
    code = cmd_list(tmp_path)
    assert code == 0
    output = capsys.readouterr().out
    assert "Entrega del laboratorio" in output
    assert output.index("2026-04-26") < output.index("2026-04-25")


def test_cmd_show_transcript(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.commands.list_show._prefix", lambda: "reunion")
    _seed(tmp_path)
    code = cmd_show(tmp_path, 1, show_transcript=True, show_all=False)
    assert code == 0
    assert "texto nuevo" in capsys.readouterr().out


def test_cmd_show_minutes_by_default(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.commands.list_show._prefix", lambda: "reunion")
    _seed(tmp_path)
    code = cmd_show(tmp_path, 1, show_transcript=False, show_all=False)
    assert code == 0
    assert "Entrega del laboratorio" in capsys.readouterr().out
