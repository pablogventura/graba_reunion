"""Perfiles de voz para poner nombres en la diarización."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from graba_reunion.config import data_dir
from graba_reunion.timing import (
    RecordingTiming,
    format_clock,
    load_recording_timing,
    wall_clock,
)

MATCH_SIMILARITY = 0.70
CLIP_SECONDS = 12.0
# El borde del turno suele mezclar al hablante anterior.
CLIP_LEAD_IN_SECONDS = 3.0
CLIP_MIN_SECONDS = 4.0


@dataclass(frozen=True)
class SpeakerTrack:
    source_name: str
    mp3_path: str
    label: str
    embedding: tuple[float, ...]
    speech_seconds: float
    clip_start: float
    clip_end: float


@dataclass(frozen=True)
class VoiceCluster:
    cluster_id: int
    tracks: tuple[SpeakerTrack, ...]
    clip_path: str | None = None


@dataclass(frozen=True)
class VoiceProfile:
    name: str
    embeddings: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class VoiceBank:
    threshold: float
    profiles: tuple[VoiceProfile, ...]
    rejected: tuple[tuple[float, ...], ...] = ()

    def match(self, embedding: list[float] | tuple[float, ...]) -> str | None:
        best_name: str | None = None
        best_score = self.threshold
        found = False
        for profile in self.profiles:
            for stored in profile.embeddings:
                score = cosine_similarity(embedding, stored)
                if score >= best_score and (not found or score > best_score):
                    best_score = score
                    best_name = profile.name
                    found = True
        if not found:
            return None
        for stored in self.rejected:
            if cosine_similarity(embedding, stored) >= best_score:
                return None
        return best_name


def voices_dir() -> Path:
    return data_dir() / "voices"


def profiles_path() -> Path:
    return voices_dir() / "profiles.json"


def names_path() -> Path:
    return voices_dir() / "nombres.txt"


def normalize(vector: list[float] | tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(float(value) for value in vector)
    return tuple(float(value) / norm for value in vector)


def cosine_similarity(
    left: list[float] | tuple[float, ...],
    right: list[float] | tuple[float, ...],
) -> float:
    a_values = normalize(left)
    b_values = normalize(right)
    length = min(len(a_values), len(b_values))
    return sum(a_values[index] * b_values[index] for index in range(length))


def cluster_tracks(
    tracks: list[SpeakerTrack],
    *,
    threshold: float = MATCH_SIMILARITY,
) -> list[VoiceCluster]:
    """Agrupa hablantes parecidos. El mismo umbral se usa después para nombrar."""
    groups: list[list[SpeakerTrack]] = [[track] for track in tracks]
    while True:
        best_score: float | None = None
        best_pair: tuple[int, int] | None = None
        for left_index in range(len(groups)):
            for right_index in range(left_index + 1, len(groups)):
                score = _average_similarity(groups[left_index], groups[right_index])
                if score < threshold:
                    continue
                if best_score is None or score > best_score:
                    best_score = score
                    best_pair = (left_index, right_index)
        if best_pair is None:
            break
        left_index, right_index = best_pair
        groups[left_index].extend(groups[right_index])
        del groups[right_index]
    groups.sort(key=_speech_seconds, reverse=True)
    return [
        VoiceCluster(cluster_id=index, tracks=tuple(group))
        for index, group in enumerate(groups, start=1)
    ]


def representative_track(cluster: VoiceCluster) -> SpeakerTrack:
    return max(cluster.tracks, key=lambda track: track.clip_end - track.clip_start)


def playback_window(start: float, end: float) -> tuple[float, float]:
    """Recorta el inicio del turno para no arrastrar la voz anterior."""
    if end - start - CLIP_LEAD_IN_SECONDS >= CLIP_MIN_SECONDS:
        start += CLIP_LEAD_IN_SECONDS
    if end - start > CLIP_SECONDS:
        end = start + CLIP_SECONDS
    return start, end


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min"
    return f"{secs} s"


def render_names_file(clusters: list[VoiceCluster]) -> str:
    lines = [
        "# Escuchá cada clip y completá el nombre después del =.",
        "# Si es la misma persona, usá el mismo nombre.",
        "# Dejá vacío para no guardar esa voz.",
        "# Usá - para ignorarla (música u otro ruido).",
        "",
    ]
    for cluster in clusters:
        speech = _speech_seconds(list(cluster.tracks))
        sources = ", ".join(sorted({track.source_name for track in cluster.tracks}))
        lines.append(f"# {cluster.cluster_id}  {format_duration(speech)}  {sources}")
        if cluster.clip_path:
            lines.append(f"# clip: {cluster.clip_path}")
        lines.append(f"{cluster.cluster_id}=")
        lines.append("")
    return "\n".join(lines)


def parse_names_file(text: str) -> dict[int, str]:
    names: dict[int, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        cluster_id_text, _, name = line.partition("=")
        if not cluster_id_text.strip().isdigit():
            continue
        cleaned = " ".join(name.strip().split())
        if "]" in cleaned or "[" in cleaned:
            continue
        names[int(cluster_id_text.strip())] = cleaned
    return names


def bank_from_names(
    clusters: list[VoiceCluster],
    names: dict[int, str],
    *,
    threshold: float = MATCH_SIMILARITY,
) -> VoiceBank:
    grouped: dict[str, list[tuple[float, ...]]] = {}
    rejected: list[tuple[float, ...]] = []
    for cluster in clusters:
        name = names.get(cluster.cluster_id, "").strip()
        if not name:
            continue
        vectors = [track.embedding for track in cluster.tracks]
        if name == "-":
            rejected.extend(vectors)
            continue
        grouped.setdefault(name, []).extend(vectors)
    profiles = tuple(
        VoiceProfile(name=name, embeddings=tuple(vectors))
        for name, vectors in sorted(grouped.items())
    )
    return VoiceBank(threshold=threshold, profiles=profiles, rejected=tuple(rejected))


def load_voice_bank(path: Path | None = None) -> VoiceBank:
    bank_path = path or profiles_path()
    if not bank_path.is_file():
        return VoiceBank(threshold=MATCH_SIMILARITY, profiles=())
    payload = json.loads(bank_path.read_text(encoding="utf-8"))
    profiles: list[VoiceProfile] = []
    for item in payload.get("profiles") or []:
        name = str(item.get("name") or "").strip()
        raw_vectors = item.get("embeddings") or []
        vectors = tuple(tuple(float(value) for value in vector) for vector in raw_vectors)
        if name and vectors:
            profiles.append(VoiceProfile(name=name, embeddings=vectors))
    raw_rejected = payload.get("rejected") or []
    rejected = tuple(tuple(float(value) for value in vector) for vector in raw_rejected)
    threshold = float(payload.get("threshold") or MATCH_SIMILARITY)
    return VoiceBank(threshold=threshold, profiles=tuple(profiles), rejected=rejected)


def save_voice_bank(bank: VoiceBank, path: Path | None = None) -> Path:
    bank_path = path or profiles_path()
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "threshold": bank.threshold,
        "profiles": [
            {"name": profile.name, "embeddings": [list(vector) for vector in profile.embeddings]}
            for profile in bank.profiles
        ],
        "rejected": [list(vector) for vector in bank.rejected],
    }
    bank_path.write_text(json.dumps(payload), encoding="utf-8")
    return bank_path


def speaker_names(payload: dict, bank: VoiceBank) -> dict[str, str]:
    embeddings = payload.get("speaker_embeddings") or {}
    mapping: dict[str, str] = {}
    for label, vector in embeddings.items():
        if not isinstance(vector, list):
            continue
        name = bank.match(vector)
        if name:
            mapping[str(label)] = name
    return mapping


def transcript_from_whisperx(payload: dict, bank: VoiceBank, *, audio: Path | None = None) -> str:
    mapping = speaker_names(payload, bank)
    timing = load_recording_timing(audio)
    lines: list[str] = []
    for segment in payload.get("segments") or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        clock = _segment_clock(segment.get("start"), timing)
        prefix = f"[{clock}] " if clock else ""
        speaker = segment.get("speaker")
        if speaker:
            shown = mapping.get(str(speaker), str(speaker))
            lines.append(f"{prefix}[{shown}]: {text}")
        else:
            lines.append(f"{prefix}{text}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _segment_clock(start: object, timing: RecordingTiming | None) -> str:
    if timing is None or not isinstance(start, (int, float)):
        return ""
    return format_clock(wall_clock(timing.started_at, float(start), timing.pauses))


def write_named_transcript(json_path: Path, txt_path: Path, bank: VoiceBank | None = None) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    active = bank if bank is not None else load_voice_bank()
    audio = txt_path.with_suffix(".mp3")
    txt_path.write_text(
        transcript_from_whisperx(payload, active, audio=audio),
        encoding="utf-8",
    )
    from graba_reunion.phrases import write_phrases

    write_phrases(payload, active, audio)


def _average_similarity(left: list[SpeakerTrack], right: list[SpeakerTrack]) -> float:
    scores = [
        cosine_similarity(left_track.embedding, right_track.embedding)
        for left_track in left
        for right_track in right
    ]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _speech_seconds(tracks: list[SpeakerTrack]) -> float:
    return sum(track.speech_seconds for track in tracks)
