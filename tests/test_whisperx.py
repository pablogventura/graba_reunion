from __future__ import annotations

from pathlib import Path

import pytest

from graba_reunion.config import Settings
from graba_reunion.transcription.whisperx import (
    transcribe_with_diarization,
    whisperx_subprocess_cwd,
)


def _settings(**overrides: object) -> Settings:
    base = dict(
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
        output_dir="",
        session_prefix="reunion",
        audio_backend="pulse",
        torch_index="https://download.pytorch.org/whl/cu124",
        groq_max_chars=120_000,
        groq_temperature=0.2,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


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
        out_dir = Path(cmd[cmd.index("--output_dir") + 1])
        stem = Path(cmd[1]).stem
        (out_dir / f"{stem}.json").write_text(
            '{"segments": [{"speaker": "SPEAKER_00", "text": "hola"}]}',
            encoding="utf-8",
        )
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

    transcribe_with_diarization(
        mp3,
        output_dir=tmp_path,
        settings=_settings(whisperx_language="en", whisperx_model="tiny"),
    )

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert captured["cwd"] == "/neutral-tmp"
    assert Path(cmd[1]).is_absolute()
    assert cmd[cmd.index("--language") + 1] == "en"
    assert cmd[cmd.index("--model") + 1] == "tiny"
    out_idx = cmd.index("--output_dir") + 1
    assert Path(cmd[out_idx]).is_absolute()
    assert cmd[cmd.index("--output_format") + 1] == "json"
    assert "--speaker_embeddings" in cmd
    assert (tmp_path / "reunion.txt").read_text(encoding="utf-8") == "[SPEAKER_00]: hola\n"
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] == "true"
