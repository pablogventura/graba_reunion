"""Transcripción sin diarización vía paquete faster-whisper."""
from __future__ import annotations

from pathlib import Path

from graba_reunion.config import Settings, is_faster_whisper_importable, load_settings
from graba_reunion.transcription.srt import segments_to_srt


def validate_faster_whisper_prereqs() -> str | None:
    if not is_faster_whisper_importable():
        return (
            "No se pudo importar faster-whisper. "
            "Ejecutá: graba-reunion setup --install-deps"
        )
    return None


def transcribe_to_srt(
    mp3: Path,
    *,
    srt_out: Path,
    language: str | None = None,
    model: str | None = None,
    settings: Settings | None = None,
) -> None:
    from faster_whisper import WhisperModel

    active = settings or load_settings()
    lang = language or active.faster_whisper_language
    model_size = model or active.faster_whisper_model
    device = active.whisperx_device
    compute_type = active.whisperx_compute_type if device == "cuda" else "int8"

    whisper = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = whisper.transcribe(str(mp3), language=lang)
    rows: list[tuple[float, float, str]] = []
    for segment in segments:
        rows.append((segment.start, segment.end, segment.text))
    srt_out.write_text(segments_to_srt(rows), encoding="utf-8")
