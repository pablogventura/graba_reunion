from __future__ import annotations

from pathlib import Path

from graba_reunion.media_join import join_media_files, joined_output_path


def test_joined_output_path_names_multi_source(tmp_path: Path) -> None:
    first = tmp_path / "parteA.ogg"
    second = tmp_path / "parteB.ogg"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    path = joined_output_path(tmp_path, [first, second])
    assert path.parent == tmp_path
    assert path.name.startswith("parteA_y_1_mas_junto_")
    assert path.suffix == ".mp3"


def test_join_single_copies(tmp_path: Path) -> None:
    source = tmp_path / "solo.wav"
    source.write_bytes(b"wav")
    destination = tmp_path / "out.mp3"
    result = join_media_files([source], destination)
    assert result == destination
    assert destination.read_bytes() == b"wav"


def test_join_calls_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    a = tmp_path / "a.ogg"
    b = tmp_path / "b.ogg"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    destination = tmp_path / "out.mp3"
    seen: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return "/usr/bin/ffmpeg" if name == "ffmpeg" else None

    def fake_run(command, check=False, capture_output=False, text=False):  # noqa: ANN001
        seen.append(list(command))
        destination.write_bytes(b"mp3")
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr("graba_reunion.media_join.shutil.which", fake_which)
    monkeypatch.setattr("graba_reunion.media_join.subprocess.run", fake_run)
    result = join_media_files([a, b], destination)
    assert result == destination
    assert seen
    assert "concat=n=2:v=0:a=1[out]" in " ".join(seen[0])
