from __future__ import annotations

from pathlib import Path

import pytest

from graba_reunion import config


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    config.clear_settings_cache()


def test_env_overrides_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GROQ_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    config.clear_settings_cache()
    settings = config.load_settings()
    assert settings.groq_api_key == "from-env"


def test_missing_required_fields_record() -> None:
    settings = config.load_settings()
    assert settings.graba_mic == ""
    assert "GRABA_MIC" in config.missing_required_fields("record")


def test_write_env_creates_keys(tmp_path: Path) -> None:
    config.write_env({"GROQ_API_KEY": "abc", "HF_TOKEN": "hf"})
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=abc" in text
    assert "HF_TOKEN=hf" in text
    config.clear_settings_cache()
    assert config.load_settings().groq_api_key == "abc"
