from __future__ import annotations

from graba_reunion import config
from graba_reunion.commands.check_deps import cmd_check_deps


def test_check_deps_reports_missing(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("GRABA_CONFIG", raising=False)
    config.clear_settings_cache()
    monkeypatch.setattr("graba_reunion.config.ffmpeg_available", lambda: False)
    monkeypatch.setattr("graba_reunion.config.resolve_whisperx_bin", lambda: None)
    code = cmd_check_deps()
    assert code == 1
    captured = capsys.readouterr()
    assert "FALTA" in captured.out
