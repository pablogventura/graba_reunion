from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from graba_reunion.commands.transcribe_cmd import cmd_transcribe


def test_transcribe_skips_missing_and_runs_existing(monkeypatch, tmp_path: Path) -> None:
    seen: list[Path] = []
    opened: list[list[str]] = []

    def fake_flow(**kwargs: object) -> int:
        media = kwargs["transcribe_only"]
        assert isinstance(media, Path)
        seen.append(media)
        media.with_suffix(".txt").write_text("hola\n", encoding="utf-8")
        return 0

    def fake_popen(command: list[str], **_kwargs: object) -> object:
        opened.append(command)
        return object()

    monkeypatch.setattr("graba_reunion.commands.transcribe_cmd.run_record_flow", fake_flow)
    monkeypatch.setattr("graba_reunion.commands.transcribe_cmd.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "graba_reunion.commands.transcribe_cmd.load_settings",
        lambda: SimpleNamespace(
            graba_mic="",
            graba_mon="",
            whisperx_language="es",
            whisperx_model="tiny",
            groq_model="llama",
        ),
    )
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")
    missing = tmp_path / "no-esta.wav"
    code = cmd_transcribe([media, missing])
    assert code == 1
    assert seen == [media.resolve()]
    assert len(opened) == 1
    assert opened[0][1:5] == ["view", "-d", str(media.parent), "--id"]
    assert opened[0][5] == "clip"


def test_transcribe_join_builds_one_media(monkeypatch, tmp_path: Path) -> None:
    seen: list[Path] = []

    def fake_join(sources: list[Path], destination: Path) -> Path:
        destination.write_bytes(b"joined")
        return destination

    def fake_flow(**kwargs: object) -> int:
        media = kwargs["transcribe_only"]
        assert isinstance(media, Path)
        seen.append(media)
        media.with_suffix(".txt").write_text("hola\n", encoding="utf-8")
        return 0

    monkeypatch.setattr("graba_reunion.commands.transcribe_cmd.join_media_files", fake_join)
    monkeypatch.setattr("graba_reunion.commands.transcribe_cmd.run_record_flow", fake_flow)
    monkeypatch.setattr(
        "graba_reunion.commands.transcribe_cmd.load_settings",
        lambda: SimpleNamespace(
            graba_mic="",
            graba_mon="",
            whisperx_language="es",
            whisperx_model="tiny",
            groq_model="llama",
        ),
    )
    monkeypatch.setattr("graba_reunion.commands.transcribe_cmd.subprocess.Popen", lambda *a, **k: object())
    first = tmp_path / "a.ogg"
    second = tmp_path / "b.ogg"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    code = cmd_transcribe([first, second], join=True, open_viewer=False)
    assert code == 0
    assert len(seen) == 1
    assert "_junto_" in seen[0].name
    assert seen[0].suffix == ".mp3"
