from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from graba_reunion.transcription.whisperx import cleanup_whisperx_side_artifacts
from graba_reunion.viewer import (
    _handler,
    meeting_catalog,
    meeting_detail,
    parse_byte_range,
    resolve_media,
    view_command,
    viewer_url,
)


def _meeting(tmp_path: Path) -> None:
    stem = "reunion_2026-09-29_13-09-20"
    (tmp_path / f"{stem}.txt").write_text("[13:09:32] [Pablo]: hola\n", encoding="utf-8")
    (tmp_path / f"{stem}_minuta.md").write_text("# Acta\n\n- un punto\n", encoding="utf-8")
    (tmp_path / f"{stem}.mp3").write_bytes(b"audio-bytes")
    (tmp_path / f"{stem}.phrases.json").write_text(
        json.dumps({"phrases": [{"index": 0, "start": 12.4, "clock": "13:09:32"}]}),
        encoding="utf-8",
    )


def test_catalog_lists_audio_text_and_minutes(tmp_path: Path) -> None:
    _meeting(tmp_path)
    catalog = meeting_catalog(tmp_path, prefix="reunion")
    assert len(catalog) == 1
    assert catalog[0]["id"] == "reunion_2026-09-29_13-09-20"
    assert catalog[0]["has_phrases"] is True
    assert catalog[0]["has_minutes"] is True
    assert catalog[0]["has_audio"] is True
    detail = meeting_detail(tmp_path, catalog[0]["id"], prefix="reunion")
    assert detail is not None
    assert detail["audio"] == "/media/reunion_2026-09-29_13-09-20.mp3"
    assert detail["text"].startswith("[13:09:32]")
    assert detail["minutes"].startswith("# Acta")
    assert detail["phrases"]["phrases"][0]["start"] == 12.4


def test_media_path_stays_inside_the_recordings_dir(tmp_path: Path) -> None:
    audio = tmp_path / "reunion.mp3"
    audio.write_bytes(b"x")
    assert resolve_media(tmp_path, "reunion.mp3") == audio.resolve()
    assert resolve_media(tmp_path, "../secreto.mp3") is None
    assert resolve_media(tmp_path, "reunion.txt") is None


def test_view_command_and_url_carry_meeting_and_offset() -> None:
    assert view_command("graba-reunion", meeting_id="reunion_a", start=12.4) == [
        "graba-reunion",
        "view",
        "--id",
        "reunion_a",
        "--t",
        "12.400",
    ]
    assert viewer_url(8765, "reunion_a", 12.4) == "http://127.0.0.1:8765/?id=reunion_a&t=12.400"
    assert viewer_url(8765) == "http://127.0.0.1:8765/"


def test_parse_byte_range() -> None:
    assert parse_byte_range("bytes=0-10", 100) == (0, 10)
    assert parse_byte_range("bytes=90-", 100) == (90, 99)
    assert parse_byte_range("bytes=100-120", 100) is None


def test_server_serves_list_page_and_audio(tmp_path: Path) -> None:
    _meeting(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/meetings") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload[0]["id"] == "reunion_2026-09-29_13-09-20"
        with urlopen(f"http://127.0.0.1:{port}/") as response:
            page = response.read().decode("utf-8")
        assert "Conversación" in page
        with urlopen(f"http://127.0.0.1:{port}/media/reunion_2026-09-29_13-09-20.mp3") as response:
            assert response.read() == b"audio-bytes"
    finally:
        httpd.shutdown()


def test_server_honors_byte_range(tmp_path: Path) -> None:
    _meeting(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        request = Request(
            f"http://127.0.0.1:{port}/media/reunion_2026-09-29_13-09-20.mp3",
            headers={"Range": "bytes=0-4"},
        )
        with urlopen(request) as response:
            assert response.status == 200 or response.status == 206
            assert response.read() == b"audio"
    finally:
        httpd.shutdown()


def test_cleanup_keeps_phrases_json(tmp_path: Path) -> None:
    (tmp_path / "reunion.json").write_text("{}", encoding="utf-8")
    (tmp_path / "reunion.phrases.json").write_text("{}", encoding="utf-8")
    cleanup_whisperx_side_artifacts(tmp_path, "reunion")
    assert not (tmp_path / "reunion.json").exists()
    assert (tmp_path / "reunion.phrases.json").is_file()
