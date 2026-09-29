from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from graba_reunion.phrases import build_phrase_document, start_for_clock, write_phrases
from graba_reunion.timing import Pause, RecordingTiming, _write
from graba_reunion.voices import VoiceBank, VoiceProfile, write_named_transcript


def _audio(tmp_path: Path) -> Path:
    audio = tmp_path / "reunion_2026-09-29_13-00-00.mp3"
    audio.write_bytes(b"x")
    _write(
        audio,
        RecordingTiming(
            started_at=datetime(2026, 9, 29, 13, 0, 0),
            duration_seconds=120,
            pauses=(Pause(at_seconds=60, paused_seconds=120),),
        ),
    )
    return audio


def test_phrase_document_keeps_audio_offset_and_clock(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    bank = VoiceBank(
        threshold=0.7,
        profiles=(VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),),
    )
    document = build_phrase_document(
        {
            "speaker_embeddings": {"SPEAKER_00": [1.0, 0.0]},
            "segments": [
                {"speaker": "SPEAKER_00", "text": "hola", "start": 90, "end": 95.2},
            ],
        },
        bank,
        audio,
    )
    assert document["id"] == audio.stem
    assert document["audio"] == audio.name
    assert document["started_at"] == "2026-09-29T13:00:00"
    assert document["pauses"] == [{"at_seconds": 60, "paused_seconds": 120}]
    phrase = document["phrases"][0]
    assert phrase["speaker"] == "Pablo"
    assert phrase["start"] == 90
    assert phrase["end"] == 95.2
    assert phrase["clock"] == "13:03:30"
    assert phrase["index"] == 0


def test_start_for_clock_reads_phrases_file(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    write_phrases(
        {"segments": [{"speaker": "SPEAKER_00", "text": "hola", "start": 90, "end": 95}]},
        VoiceBank(threshold=0.7, profiles=()),
        audio,
    )
    assert start_for_clock(audio, "13:03:30") == 90
    assert start_for_clock(audio.with_suffix(".txt"), "13:03:30") == 90
    assert start_for_clock(audio, "13:00:00") is None


def test_named_transcript_writes_phrases_json(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    json_path = audio.with_suffix(".json")
    json_path.write_text(
        json.dumps({"segments": [{"speaker": "SPEAKER_00", "text": "hola", "start": 90}]}),
        encoding="utf-8",
    )
    txt_path = audio.with_suffix(".txt")
    write_named_transcript(json_path, txt_path, VoiceBank(threshold=0.7, profiles=()))
    assert txt_path.read_text(encoding="utf-8") == "[13:03:30] [SPEAKER_00]: hola\n"
    stored = json.loads(audio.with_name(f"{audio.stem}.phrases.json").read_text(encoding="utf-8"))
    assert stored["phrases"][0]["start"] == 90
    assert stored["phrases"][0]["clock"] == "13:03:30"
