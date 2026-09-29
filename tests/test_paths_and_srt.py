from __future__ import annotations

from pathlib import Path

from graba_reunion import config
from graba_reunion.paths import default_output_dir, session_paths
from graba_reunion.recording import build_ffmpeg_cmd
from graba_reunion.transcription.srt import srt_to_plaintext


def test_session_paths_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    config.clear_settings_cache()
    paths = session_paths(tmp_path)
    assert paths.mp3.name.startswith("reunion_")
    assert paths.txt.suffix == ".txt"


def test_session_paths_custom_prefix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    preferred = config.preferred_env_path()
    preferred.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_text("GRABA_SESSION_PREFIX=meet\n", encoding="utf-8")
    config.clear_settings_cache()
    paths = session_paths(tmp_path)
    assert paths.mp3.name.startswith("meet_")


def test_default_output_dir_xdg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    config.clear_settings_cache()
    assert default_output_dir() == (tmp_path / "data" / "graba-reunion" / "recordings").resolve()


def test_build_ffmpeg_cmd_pulse_and_alsa(tmp_path: Path) -> None:
    mp3 = tmp_path / "out.mp3"
    pulse = build_ffmpeg_cmd("mic", "mon", mp3, backend="pulse")
    assert pulse[pulse.index("-f") + 1] == "pulse"
    alsa = build_ffmpeg_cmd("hw:0", "hw:1", mp3, backend="alsa")
    assert alsa.count("alsa") == 2


def test_srt_to_plaintext() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.srt"
    text = srt_to_plaintext(fixture)
    assert "Hola, probando audio." in text
    assert "Segunda línea de prueba." in text
