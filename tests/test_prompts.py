from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from graba_reunion.viewer import _handler
from graba_reunion.viewer.prompts import build_prompt

TRANSCRIPT = """[13:09:32] [Pablo]: hola Mica
[13:09:40] [SPEAKER_00]: dale, lo vemos
[13:09:48] [SPEAKER_00]: mañana lo cierro
[13:09:55] [SPEAKER_00]: con el laboratorio
[13:10:02] [SPEAKER_00]: esta sobra
"""


def test_minutes_prompt_asks_for_actions_and_keeps_existing_minutes() -> None:
    text = build_prompt(
        "minutes",
        TRANSCRIPT,
        "Acta",
        "2026-09-29 13:09:20",
        minutes="# Vieja\n\n- un punto",
    )
    assert "Puntos de acción" in text
    assert "- [ ] tarea" in text
    assert "Corregila" in text
    assert "un punto" in text
    assert "hola Mica" in text


def test_cursor_prompt_asks_for_a_prompt_only() -> None:
    text = build_prompt("cursor", TRANSCRIPT, "Acta", "")
    assert "Cursor" in text
    assert "No implementes nada" in text
    assert "hola Mica" in text


def test_speakers_prompt_lists_a_few_lines_of_each_unknown_voice() -> None:
    text = build_prompt("speakers", TRANSCRIPT, "Acta", "")
    assert "SPEAKER_00" in text
    assert "dale, lo vemos" in text
    assert "con el laboratorio" in text
    assert "esta sobra" not in text.split("Transcripción:")[0]
    assert "esta sobra" in text.split("Transcripción:")[1]


def test_speakers_prompt_without_labels_asks_to_review_names() -> None:
    text = build_prompt("speakers", "[13:00:00] [Pablo]: hola\n", "Acta", "")
    assert "No hay etiquetas" in text
    assert "nombre propio" in text


def test_long_transcript_is_cut() -> None:
    text = build_prompt("cursor", "a" * 120_001, "Acta", "")
    assert "transcripción truncada" in text


def test_prompt_endpoint_returns_plain_text(tmp_path: Path) -> None:
    stem = "reunion_2026-09-29_13-09-20"
    (tmp_path / f"{stem}.txt").write_text(TRANSCRIPT, encoding="utf-8")
    (tmp_path / f"{stem}_minuta.md").write_text("# Vieja\n\n- un punto\n", encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}/api/meetings/{stem}/prompts"
    try:
        with urlopen(f"{base}/minutes") as response:
            body = response.read().decode("utf-8")
            assert response.headers.get_content_type() == "text/plain"
        assert "Puntos de acción" in body
        assert "un punto" in body
        assert "hola Mica" in body
        try:
            urlopen(f"{base}/nope")
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("un prompt desconocido tendría que responder 404")
    finally:
        httpd.shutdown()
