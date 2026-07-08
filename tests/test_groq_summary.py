from __future__ import annotations

import json
from pathlib import Path

import pytest

from graba_reunion.groq_summary import (
    _extract_json_object,
    _format_minutes,
    summarize_transcript,
    truncate_transcript,
)


def test_truncate_transcript() -> None:
    body, truncated = truncate_transcript("a" * 200, max_chars=100)
    assert truncated is True
    assert "truncada" in body


def test_format_minutes_from_fixture() -> None:
    raw = (Path(__file__).parent / "fixtures" / "groq_response.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    minutes = _format_minutes(data)
    assert "# Minuta de reunión" in minutes
    assert "verificar mic" in minutes


def test_extract_json_object_with_fence() -> None:
    data = _extract_json_object('```json\n{"title":"x"}\n```')
    assert data["title"] == "x"


def test_summarize_transcript_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMessage:
        content = json.dumps(
            {
                "title": "T",
                "summary": "S",
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": "",
            }
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            return FakeCompletion()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("groq.Groq", lambda api_key: FakeClient())
    result = summarize_transcript("hola", api_key="test-key")
    assert result.title == "T"
