from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from graba_reunion import config
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


def test_truncate_transcript_en() -> None:
    body, truncated = truncate_transcript("a" * 200, max_chars=100, language="en")
    assert truncated is True
    assert "truncated" in body


def test_format_minutes_from_fixture() -> None:
    raw = (Path(__file__).parent / "fixtures" / "groq_response.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    minutes = _format_minutes(data)
    assert "# Minuta de reunión" in minutes
    assert "verificar mic" in minutes


def test_format_minutes_en() -> None:
    minutes = _format_minutes(
        {
            "summary": "Hello",
            "topics": ["A"],
            "decisions": [],
            "action_items": [],
            "notes": "",
        },
        language="en",
    )
    assert "# Meeting minutes" in minutes
    assert "## Summary" in minutes


def test_extract_json_object_with_fence() -> None:
    data = _extract_json_object('```json\n{"title":"x"}\n```')
    assert data["title"] == "x"


def test_summarize_transcript_mock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    config.clear_settings_cache()

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
        def create(**kwargs):
            assert kwargs["temperature"] == 0.2
            return FakeCompletion()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    fake_groq = ModuleType("groq")
    fake_groq.Groq = lambda api_key: FakeClient()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    result = summarize_transcript("hola", api_key="test-key", language="es")
    assert result.title == "T"
