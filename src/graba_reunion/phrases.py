"""JSON estable de frases: segundos del MP3 y hora de reloj."""
from __future__ import annotations

import json
from pathlib import Path

from graba_reunion.timing import format_clock, load_recording_timing, wall_clock
from graba_reunion.voices import VoiceBank, speaker_names


def phrases_path(audio: Path) -> Path:
    return audio.with_name(f"{audio.stem}.phrases.json")


def write_phrases(payload: dict, bank: VoiceBank, audio: Path) -> Path:
    document = build_phrase_document(payload, bank, audio)
    path = phrases_path(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def build_phrase_document(payload: dict, bank: VoiceBank, audio: Path) -> dict:
    mapping = speaker_names(payload, bank)
    timing = load_recording_timing(audio)
    phrases: list[dict] = []
    for segment in payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _seconds(segment.get("start"))
        end = _seconds(segment.get("end"))
        speaker = segment.get("speaker")
        shown = mapping.get(str(speaker), str(speaker)) if speaker else ""
        clock = ""
        if timing is not None and start is not None:
            clock = format_clock(wall_clock(timing.started_at, start, timing.pauses))
        phrases.append(
            {
                "index": len(phrases),
                "speaker": shown,
                "text": text,
                "start": start,
                "end": end,
                "clock": clock,
            }
        )
    started_at = None
    duration_seconds = None
    pauses: list[dict] = []
    if timing is not None:
        started_at = timing.started_at.isoformat(timespec="seconds")
        duration_seconds = timing.duration_seconds
        pauses = [
            {"at_seconds": pause.at_seconds, "paused_seconds": pause.paused_seconds}
            for pause in timing.pauses
        ]
    return {
        "id": audio.stem,
        "audio": audio.name,
        "started_at": started_at,
        "duration_seconds": duration_seconds,
        "pauses": pauses,
        "phrases": phrases,
    }


def start_for_clock(source: Path, clock: str) -> float | None:
    """Segundo del MP3 cuya hora de reloj coincide con un resultado de búsqueda."""
    cleaned = clock.strip()
    if not cleaned:
        return None
    path = phrases_path(source)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for phrase in payload.get("phrases") or []:
        if not isinstance(phrase, dict) or phrase.get("clock") != cleaned:
            continue
        start = _seconds(phrase.get("start"))
        if start is not None:
            return start
    return None


def _seconds(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 3)
