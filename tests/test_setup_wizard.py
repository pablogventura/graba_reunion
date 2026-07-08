from __future__ import annotations

from graba_reunion import config
from graba_reunion.setup_wizard import ensure_configured, run_setup_wizard


def test_run_setup_wizard_writes_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    config.clear_settings_cache()
    secrets = iter(["groq-key", "hf-token"])
    prompts = iter(["1", "2", "cuda"])
    monkeypatch.setattr(
        "graba_reunion.setup_wizard.list_pulse_sources",
        lambda: [("0", "mic.test"), ("1", "mon.test")],
    )
    monkeypatch.setattr("graba_reunion.setup_wizard.getpass", lambda _prompt: next(secrets))
    code = run_setup_wizard(input_fn=lambda _prompt: next(prompts))
    assert code == 0
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=groq-key" in text


def test_ensure_configured_declines(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    config.clear_settings_cache()
    code = ensure_configured(["groq"], input_fn=lambda _prompt: "n")
    assert code == 1
