"""Renombrar SPEAKER_XX en el .txt y el JSON de frases de una reunión."""
from __future__ import annotations

import json
import re
from pathlib import Path

from graba_reunion.phrases import phrases_path
from graba_reunion.voice_enroll import load_review
from graba_reunion.voices import bank_from_names, load_voice_bank, merge_voice_banks, save_voice_bank

SPEAKER_TOKEN = re.compile(r"SPEAKER_\d+")
BRACKETED = re.compile(r"\[(SPEAKER_\d+)\]")


def rename_meeting_speakers(txt: Path, mapping: dict[str, str]) -> dict:
    cleaned = _clean_mapping(mapping)
    if not cleaned:
        return {"ok": True, "message": "No había nombres para aplicar.", "renamed": {}}
    text = txt.read_text(encoding="utf-8", errors="replace")
    new_text = _replace_brackets(text, cleaned)
    txt.write_text(new_text, encoding="utf-8")
    phrases = phrases_path(txt)
    if phrases.is_file():
        _rename_phrases(phrases, cleaned)
    enrolled = _enroll_from_review(txt, cleaned)
    names = ", ".join(f"{old} -> {new}" for old, new in cleaned.items())
    parts = [f"Renombrado: {names}."]
    if enrolled:
        parts.append(f"Perfiles: {', '.join(enrolled)}.")
    return {"ok": True, "message": " ".join(parts), "renamed": cleaned}


def unidentified_speakers(text: str) -> list[str]:
    found = sorted(set(SPEAKER_TOKEN.findall(text)), key=lambda label: int(label.split("_")[1]))
    return found


def _clean_mapping(mapping: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in mapping.items():
        key = str(raw_key).strip()
        if not SPEAKER_TOKEN.fullmatch(key):
            continue
        value = " ".join(str(raw_value).strip().split())
        if not value or value == "-" or "[" in value or "]" in value:
            continue
        cleaned[key] = value
    return cleaned


def _replace_brackets(text: str, mapping: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        return f"[{mapping.get(label, label)}]"

    return BRACKETED.sub(replace, text)


def _rename_phrases(path: Path, mapping: dict[str, str]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    phrases = payload.get("phrases")
    if not isinstance(phrases, list):
        return
    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        speaker = str(phrase.get("speaker") or "")
        if speaker in mapping:
            phrase["speaker"] = mapping[speaker]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _enroll_from_review(txt: Path, mapping: dict[str, str]) -> list[str]:
    try:
        clusters = load_review()
    except OSError:
        return []
    media_stems = {txt.stem}
    for suffix in (".mp3", ".wav", ".ogg", ".opus", ".m4a", ".mp4", ".mkv", ".webm"):
        candidate = txt.with_suffix(suffix)
        if candidate.is_file():
            media_stems.add(candidate.name)
            media_stems.add(candidate.stem)
    names: dict[int, str] = {}
    for cluster in clusters:
        for track in cluster.tracks:
            if track.label not in mapping:
                continue
            if track.source_name not in media_stems and Path(track.source_name).stem not in {
                txt.stem
            }:
                continue
            names[cluster.cluster_id] = mapping[track.label]
            break
    if not names:
        # Sin clip de review: crear perfiles vacíos no sirve; solo nombres con embedding.
        return _enroll_orphan_labels(mapping)
    current = load_voice_bank()
    added = bank_from_names(
        [cluster for cluster in clusters if cluster.cluster_id in names],
        names,
        threshold=current.threshold,
    )
    if not added.profiles and not added.rejected:
        return []
    save_voice_bank(merge_voice_banks(current, added))
    return [profile.name for profile in added.profiles]


def _enroll_orphan_labels(mapping: dict[str, str]) -> list[str]:
    """Si no hay review, no se puede guardar embedding; no inventar perfiles vacíos."""
    del mapping
    return []
