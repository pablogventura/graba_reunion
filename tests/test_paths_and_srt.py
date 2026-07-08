from __future__ import annotations

from pathlib import Path

from graba_reunion.paths import resolve_db_path, session_paths
from graba_reunion.transcription.srt import srt_to_plaintext


def test_session_paths_names(tmp_path: Path) -> None:
    paths = session_paths(tmp_path)
    assert paths.mp3.name.startswith("reunion_")
    assert paths.txt.suffix == ".txt"


def test_resolve_db_path_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.db"
    assert resolve_db_path(tmp_path, explicit) == explicit.resolve()


def test_srt_to_plaintext() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sample.srt"
    text = srt_to_plaintext(fixture)
    assert "Hola, probando audio." in text
    assert "Segunda línea de prueba." in text
