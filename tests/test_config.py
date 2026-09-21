from __future__ import annotations

from pathlib import Path

import pytest

from graba_reunion import config


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("GRABA_CONFIG", raising=False)
    for key in config.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config.clear_settings_cache()


def test_env_overrides_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preferred = config.preferred_env_path()
    preferred.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_text("GROQ_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    config.clear_settings_cache()
    settings = config.load_settings()
    assert settings.groq_api_key == "from-env"


def test_defaults_are_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    config.clear_settings_cache()
    settings = config.load_settings()
    assert settings.whisperx_device == "cpu"
    assert settings.whisperx_compute_type == "int8"
    assert settings.audio_backend == "pulse"
    assert settings.session_prefix == "reunion"


def test_language_model_aliases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    preferred = config.preferred_env_path()
    preferred.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_text("GRABA_MODEL=tiny\nGRABA_LANGUAGE=en\n", encoding="utf-8")
    config.clear_settings_cache()
    settings = config.load_settings()
    assert settings.whisperx_model == "tiny"
    assert settings.whisperx_language == "en"
    assert settings.faster_whisper_model == "tiny"


def test_whisperx_keys_win_over_aliases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preferred = config.preferred_env_path()
    preferred.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_text(
        "GRABA_MODEL=tiny\nGRABA_WHISPERX_MODEL=large-v3\n"
        "GRABA_LANGUAGE=en\nGRABA_WHISPERX_LANGUAGE=es\n",
        encoding="utf-8",
    )
    config.clear_settings_cache()
    settings = config.load_settings()
    assert settings.whisperx_model == "large-v3"
    assert settings.whisperx_language == "es"


def test_graba_config_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom" / "my.env"
    custom.parent.mkdir(parents=True)
    custom.write_text("GRABA_MIC=mic.x\n", encoding="utf-8")
    monkeypatch.setenv("GRABA_CONFIG", str(custom))
    config.clear_settings_cache()
    assert config.env_file_path() == custom
    assert config.load_settings().graba_mic == "mic.x"


def test_fallback_reads_project_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project_env = tmp_path / "repo" / ".env"
    project_env.write_text("HF_TOKEN=from-repo\n", encoding="utf-8")
    config.clear_settings_cache()
    assert config.env_file_path() == project_env
    assert config.load_settings().hf_token == "from-repo"


def test_write_env_migrates_from_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_env = tmp_path / "repo" / ".env"
    project_env.write_text("HF_TOKEN=old\nGRABA_MIC=mic1\n", encoding="utf-8")
    target = config.write_env({"HF_TOKEN": "new"})
    assert target == config.preferred_env_path()
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "HF_TOKEN=new" in text
    assert "GRABA_MIC=mic1" in text


def test_missing_required_fields_record() -> None:
    settings = config.load_settings()
    assert settings.graba_mic == ""
    assert "GRABA_MIC" in config.missing_required_fields("record")


def test_write_env_creates_keys(tmp_path: Path) -> None:
    target = config.write_env({"GROQ_API_KEY": "abc", "HF_TOKEN": "hf"})
    text = target.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=abc" in text
    assert "HF_TOKEN=hf" in text
    config.clear_settings_cache()
    assert config.load_settings().groq_api_key == "abc"


def test_settings_with_overrides() -> None:
    base = config.load_settings()
    updated = config.settings_with_overrides(base, language="en", model="tiny", device="cuda")
    assert updated.whisperx_language == "en"
    assert updated.faster_whisper_language == "en"
    assert updated.whisperx_model == "tiny"
    assert updated.whisperx_device == "cuda"
    assert updated.whisperx_compute_type == "float16"
