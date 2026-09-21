from __future__ import annotations

from graba_reunion import config
from graba_reunion.setup_wizard import ensure_configured, run_setup_wizard


def test_run_setup_wizard_writes_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("GRABA_CONFIG", raising=False)
    config.clear_settings_cache()

    secrets = iter(["hf-token", "groq-key"])
    # backend, mic, mon, device, language, model, compute, batch,
    # output, prefix, db, groq_model
    prompts = iter(
        ["pulse", "1", "2", "cuda", "", "", "", "", "", "", "", ""]
    )
    monkeypatch.setattr(
        "graba_reunion.setup_wizard.list_pulse_sources",
        lambda: [("0", "mic.test"), ("1", "mon.test")],
    )
    monkeypatch.setattr(
        "graba_reunion.setup_wizard.is_torch_cuda_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "graba_reunion.setup_wizard.detect_missing_deps",
        lambda: [],
    )
    monkeypatch.setattr("graba_reunion.setup_wizard.getpass", lambda _prompt: next(secrets))
    code = run_setup_wizard(input_fn=lambda _prompt: next(prompts))
    assert code == 0
    text = config.preferred_env_path().read_text(encoding="utf-8")
    assert "GROQ_API_KEY=groq-key" in text
    assert "HF_TOKEN=hf-token" in text
    assert "GRABA_MIC=mic.test" in text
    assert "GRABA_WHISPERX_DEVICE=cuda" in text


def test_ensure_configured_declines(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "project_root", lambda: tmp_path / "repo")
    (tmp_path / "repo").mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("GRABA_CONFIG", raising=False)
    config.clear_settings_cache()
    code = ensure_configured(["groq"], input_fn=lambda _prompt: "n")
    assert code == 1
