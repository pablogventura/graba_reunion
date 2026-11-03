from __future__ import annotations

from pathlib import Path

from graba_reunion.cli import rewrite_media_argv


def test_rewrite_single_media_file(tmp_path: Path) -> None:
    audio = tmp_path / "nota.ogg"
    audio.write_bytes(b"x")
    assert rewrite_media_argv([str(audio)]) == ["transcribe", "--", str(audio)]


def test_rewrite_several_media_files(tmp_path: Path) -> None:
    first = tmp_path / "a.mp3"
    second = tmp_path / "b.mp4"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    assert rewrite_media_argv([str(first), str(second)]) == [
        "transcribe",
        "--",
        str(first),
        str(second),
    ]


def test_keeps_explicit_subcommand(tmp_path: Path) -> None:
    audio = tmp_path / "nota.ogg"
    audio.write_bytes(b"x")
    assert rewrite_media_argv(["show", "1"]) == ["show", "1"]
    assert rewrite_media_argv(["transcribe", str(audio)]) == ["transcribe", str(audio)]


def test_keeps_record_flags(tmp_path: Path) -> None:
    audio = tmp_path / "nota.ogg"
    audio.write_bytes(b"x")
    assert rewrite_media_argv(["--groq", str(audio)]) == ["--groq", str(audio)]
    assert rewrite_media_argv([str(audio), "--no-diarize"]) == [str(audio), "--no-diarize"]


def test_skips_output_dir_and_rewrites(tmp_path: Path) -> None:
    audio = tmp_path / "nota.opus"
    audio.write_bytes(b"x")
    assert rewrite_media_argv(["-d", str(tmp_path), str(audio)]) == [
        "transcribe",
        "--",
        str(audio),
    ]


def test_ignores_missing_or_non_media(tmp_path: Path) -> None:
    missing = tmp_path / "no.ogg"
    text = tmp_path / "nota.txt"
    text.write_text("hola", encoding="utf-8")
    assert rewrite_media_argv([str(missing)]) == [str(missing)]
    assert rewrite_media_argv([str(text)]) == [str(text)]
