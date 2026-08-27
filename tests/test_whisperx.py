from __future__ import annotations

from pathlib import Path

import pytest

from graba_reunion.config import Settings
from graba_reunion.transcription.whisperx import (
    transcribe_with_diarization,
    whisperx_subprocess_cwd,
)


def _settings() -> Settings:
    return Settings(
        groq_api_key="",
        hf_token="hf_test",
        graba_mic="",
        graba_mon="",
        groq_model="llama-3.3-70b-versatile",
        whisperx_model="large-v3",
        whisperx_language="es",
        whisperx_device="cuda",
        whisperx_compute_type="float16",
        whisperx_batch_size=16,
        faster_whisper_model="large-v3",
        faster_whisper_language="es",
        graba_db="",
    )


def test_whisperx_subprocess_cwd_is_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graba_reunion.transcription.whisperx.tempfile.gettempdir",
        lambda: "/neutral-tmp",
    )
    assert whisperx_subprocess_cwd() == "/neutral-tmp"


def test_transcribe_with_diarization_uses_neutral_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    fake_bin = tmp_path / "whisperx"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    mp3 = tmp_path / "reunion.mp3"
    mp3.write_bytes(b"x")

    def fake_run(cmd, check=False, cwd=None, env=None):
        captured["cmd"] = list(cmd)
        captured["cwd"] = cwd
        captured["env"] = env
        return None

    monkeypatch.setattr(
        "graba_reunion.transcription.whisperx.resolve_whisperx_bin",
        lambda: fake_bin,
    )
    monkeypatch.setattr(
        "graba_reunion.transcription.whisperx.whisperx_subprocess_cwd",
        lambda: "/neutral-tmp",
    )
    monkeypatch.setattr(
        "graba_reunion.transcription.whisperx.subprocess.run",
        fake_run,
    )

    transcribe_with_diarization(mp3, output_dir=tmp_path, settings=_settings())

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert captured["cwd"] == "/neutral-tmp"
    assert Path(cmd[1]).is_absolute()
    out_idx = cmd.index("--output_dir") + 1
    assert Path(cmd[out_idx]).is_absolute()
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] == "true"
