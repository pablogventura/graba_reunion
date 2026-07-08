from __future__ import annotations

from graba_reunion.commands.check_deps import cmd_check_deps


def test_check_deps_reports_missing(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr("graba_reunion.config.project_root", lambda: tmp_path)
    code = cmd_check_deps()
    assert code == 1
    captured = capsys.readouterr()
    assert "FALTA" in captured.out
