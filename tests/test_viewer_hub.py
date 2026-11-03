from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from graba_reunion.viewer import _handler, viewer_url
from graba_reunion.viewer.speakers import rename_meeting_speakers, unidentified_speakers


def _meeting(tmp_path: Path) -> str:
    stem = "reunion_2026-09-29_13-09-20"
    (tmp_path / f"{stem}.txt").write_text(
        "[13:09:32] [SPEAKER_00]: hola\n[13:09:40] [SPEAKER_01]: chau\n",
        encoding="utf-8",
    )
    (tmp_path / f"{stem}.mp3").write_bytes(b"audio-bytes")
    (tmp_path / f"{stem}.phrases.json").write_text(
        json.dumps(
            {
                "phrases": [
                    {"index": 0, "speaker": "SPEAKER_00", "text": "hola", "start": 1.0},
                    {"index": 1, "speaker": "SPEAKER_01", "text": "chau", "start": 2.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    return stem


def _server(tmp_path: Path) -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(httpd.server_address[1])


def test_viewer_url_includes_tab() -> None:
    assert viewer_url(8765, tab="voices") == "http://127.0.0.1:8765/?tab=voices"
    assert "tab=search" in viewer_url(8765, "reunion_a", 1.5, tab="search")


def test_hub_page_has_navigation(tmp_path: Path) -> None:
    httpd, port = _server(tmp_path)
    try:
        with urlopen(f"http://127.0.0.1:{port}/") as response:
            page = response.read().decode("utf-8")
        assert 'data-hub="conversations"' in page
        assert 'data-hub="search"' in page
        assert 'data-hub="voices"' in page
        assert 'data-hub="transcribe"' in page
        assert "Copiar charla" in page
    finally:
        httpd.shutdown()


def test_search_api_word(tmp_path: Path) -> None:
    _meeting(tmp_path)
    httpd, port = _server(tmp_path)
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/search?q=hola&word=1") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["hits"]
        assert payload["hits"][0]["id"] == "reunion_2026-09-29_13-09-20"
    finally:
        httpd.shutdown()


def test_put_minutes_and_download(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    httpd, port = _server(tmp_path)
    try:
        body = json.dumps({"markdown": "# Acta\n\n- punto\n"}).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{port}/api/meetings/{stem}/minutes",
            data=body,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert (tmp_path / f"{stem}_minuta.md").read_text(encoding="utf-8").startswith("# Acta")
        with urlopen(f"http://127.0.0.1:{port}/api/meetings/{stem}/files/minutes") as response:
            assert response.read().decode("utf-8").startswith("# Acta")
        with urlopen(f"http://127.0.0.1:{port}/api/meetings/{stem}/files/txt") as response:
            assert "SPEAKER_00" in response.read().decode("utf-8")
    finally:
        httpd.shutdown()


def test_rename_speakers_updates_txt_and_phrases(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    txt = tmp_path / f"{stem}.txt"
    result = rename_meeting_speakers(txt, {"SPEAKER_00": "Ana"})
    assert result["ok"] is True
    text = txt.read_text(encoding="utf-8")
    assert "[Ana]:" in text
    assert "SPEAKER_00" not in text
    phrases = json.loads((tmp_path / f"{stem}.phrases.json").read_text(encoding="utf-8"))
    assert phrases["phrases"][0]["speaker"] == "Ana"
    assert unidentified_speakers(text) == ["SPEAKER_01"]


def test_post_speakers(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    httpd, port = _server(tmp_path)
    try:
        body = json.dumps({"names": {"SPEAKER_00": "Ana"}}).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{port}/api/meetings/{stem}/speakers",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert "[Ana]:" in (tmp_path / f"{stem}.txt").read_text(encoding="utf-8")
    finally:
        httpd.shutdown()


def test_groq_minutes_endpoint(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    httpd, port = _server(tmp_path)

    def fake_enrich(**kwargs):
        path = kwargs["txt"].with_name(f"{kwargs['session_base']}_minuta.md")
        path.write_text("# Título\n\n# Minuta de reunión\n\n- ok\n", encoding="utf-8")
        return 0

    try:
        with patch("graba_reunion.viewer.hub_api.enrich_and_store", side_effect=fake_enrich):
            request = Request(
                f"http://127.0.0.1:{port}/api/meetings/{stem}/minutes/groq",
                data=b"",
                method="POST",
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert "Título" in payload["minutes"]
    finally:
        httpd.shutdown()


def test_phrases_endpoint_mocked(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    httpd, port = _server(tmp_path)
    try:
        with patch("graba_reunion.viewer.hub_api.cmd_phrases", return_value=0) as mocked:
            request = Request(
                f"http://127.0.0.1:{port}/api/meetings/{stem}/phrases",
                data=b"",
                method="POST",
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        mocked.assert_called_once()
    finally:
        httpd.shutdown()


def test_transcribe_upload_mocked(tmp_path: Path) -> None:
    httpd, port = _server(tmp_path)
    boundary = "----bound"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="nota.ogg"\r\n'
        "Content-Type: audio/ogg\r\n\r\n"
        "ogg-bytes\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    def fake_transcribe(paths, open_viewer=True):
        for path in paths:
            path.with_suffix(".txt").write_text("[SPEAKER_00]: hola\n", encoding="utf-8")
        return 0

    try:
        with patch("graba_reunion.viewer.hub_api.cmd_transcribe", side_effect=fake_transcribe):
            request = Request(
                f"http://127.0.0.1:{port}/api/transcribe",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["ids"] == ["nota"]
        assert (tmp_path / "nota.ogg").is_file()
    finally:
        httpd.shutdown()


def test_voices_status_without_review(tmp_path: Path) -> None:
    httpd, port = _server(tmp_path)
    try:
        with patch(
            "graba_reunion.viewer.hub_api.load_review",
            side_effect=OSError("no review"),
        ):
            with urlopen(f"http://127.0.0.1:{port}/api/voices/status") as response:
                payload = json.loads(response.read().decode("utf-8"))
        assert payload["ready"] is False
        assert "review.json" in payload["message"]
    finally:
        httpd.shutdown()


def test_meeting_detail_lists_speakers(tmp_path: Path) -> None:
    stem = _meeting(tmp_path)
    httpd, port = _server(tmp_path)
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/meetings/{stem}") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    finally:
        httpd.shutdown()
