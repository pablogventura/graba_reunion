"""Búsqueda de reuniones por tema, palabra o participante."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from graba_reunion.config import data_dir
from graba_reunion.voices import cosine_similarity

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_CHARS = 500
RESULT_LIMIT = 20
TOPIC_MIN_SCORE = 0.40
TOPIC_SCORE_GAP = 0.15
MIN_TOPIC_CHARS = 20
SPEAKER_LINE = re.compile(r"^\[([^\]]+)\]:\s*(.*)$")
TIMED_SPEAKER_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[([^\]]+)\]:\s*(.*)$")

_model: object | None = None


@dataclass(frozen=True)
class Chunk:
    path: str
    speaker: str
    text: str
    spoken_at: str = ""
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class SearchHit:
    path: str
    speaker: str
    snippet: str
    score: float | None
    spoken_at: str = ""


def parse_chunks(path: Path, text: str) -> list[Chunk]:
    turns: list[tuple[str, str, str]] = []
    speaker = ""
    spoken_at = ""
    parts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        timed = TIMED_SPEAKER_LINE.match(stripped)
        match = SPEAKER_LINE.match(stripped)
        if timed or match:
            if parts:
                turns.append((speaker, " ".join(parts), spoken_at))
            if timed:
                spoken_at = timed.group(1)
                speaker = timed.group(2).strip()
                spoken = timed.group(3).strip()
            else:
                spoken_at = ""
                speaker = match.group(1).strip() if match else ""
                spoken = match.group(2).strip() if match else ""
            parts = [spoken] if spoken else []
            continue
        spoken = stripped
        if spoken:
            parts.append(spoken)
    if parts:
        turns.append((speaker, " ".join(parts), spoken_at))

    chunks: list[Chunk] = []
    buffer_speaker = ""
    buffer_text = ""
    buffer_at = ""
    for turn_speaker, turn_text, turn_at in turns:
        if buffer_text and (turn_speaker != buffer_speaker or len(buffer_text) >= CHUNK_CHARS):
            chunks.append(
                Chunk(path=str(path), speaker=buffer_speaker, text=buffer_text, spoken_at=buffer_at)
            )
            buffer_text = ""
            buffer_at = ""
        if not buffer_text:
            buffer_at = turn_at
        buffer_speaker = turn_speaker
        buffer_text = f"{buffer_text} {turn_text}".strip()
    if buffer_text:
        chunks.append(
            Chunk(path=str(path), speaker=buffer_speaker, text=buffer_text, spoken_at=buffer_at)
        )
    return chunks


def search_transcripts(
    directory: Path,
    query: str,
    *,
    word: bool = False,
    participant: str = "",
    embed_texts=None,
    cache_path: Path | None = None,
) -> list[SearchHit]:
    files = sorted(path for path in directory.glob("*.txt") if path.is_file())
    cleaned = query.strip()
    if word or (participant and not cleaned):
        return _literal_hits(files, cleaned, participant=participant)[:RESULT_LIMIT]
    chunks = _chunks_with_embeddings(files, embed_texts=embed_texts, cache_path=cache_path)
    ranked = _topic_hits(chunks, cleaned, participant=participant, embed_texts=embed_texts)
    return ranked[:RESULT_LIMIT]


def search_command(
    binary: str,
    query: str,
    *,
    word: bool,
    participant: str,
    output_dir: Path | None = None,
) -> list[str]:
    command = [binary, "search", "--json"]
    if output_dir is not None:
        command.extend(["-d", str(output_dir)])
    if word:
        command.append("--word")
    cleaned_participant = participant.strip()
    if cleaned_participant:
        command.extend(["--participant", cleaned_participant])
    cleaned_query = query.strip()
    if cleaned_query:
        command.append(cleaned_query)
    return command


def hits_as_json(hits: list[SearchHit]) -> str:
    payload = [
        {
            "path": hit.path,
            "speaker": hit.speaker,
            "spoken_at": hit.spoken_at,
            "snippet": hit.snippet,
            "score": hit.score,
        }
        for hit in hits
    ]
    return json.dumps(payload, ensure_ascii=False)


def _literal_hits(files: list[Path], query: str, *, participant: str) -> list[SearchHit]:
    needle = query.casefold().strip()
    who = participant.casefold().strip()
    hits: list[SearchHit] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for chunk in parse_chunks(path, text):
            if who and who not in chunk.speaker.casefold():
                continue
            if needle and needle not in chunk.text.casefold():
                continue
            if not needle and not who:
                continue
            hits.append(
                SearchHit(
                    path=str(path),
                    speaker=chunk.speaker,
                    snippet=_snippet(chunk.text, needle),
                    score=None,
                    spoken_at=chunk.spoken_at,
                )
            )
    return hits


def _topic_hits(
    chunks: list[Chunk],
    query: str,
    *,
    participant: str,
    embed_texts,
) -> list[SearchHit]:
    who = participant.casefold().strip()
    selected = [chunk for chunk in chunks if not who or who in chunk.speaker.casefold()]
    vectors = [
        chunk
        for chunk in selected
        if chunk.embedding and len(chunk.text.strip()) >= MIN_TOPIC_CHARS
    ]
    if not vectors or embed_texts is None:
        return []
    query_vector = embed_texts([query])[0]
    ranked: list[SearchHit] = []
    for chunk in vectors:
        score = cosine_similarity(query_vector, chunk.embedding or ())
        if score < TOPIC_MIN_SCORE:
            continue
        ranked.append(
            SearchHit(
                path=chunk.path,
                speaker=chunk.speaker,
                snippet=_snippet(chunk.text, ""),
                score=round(score, 3),
                spoken_at=chunk.spoken_at,
            )
        )
    ranked.sort(key=lambda hit: hit.score or 0.0, reverse=True)
    if not ranked:
        return ranked
    best = ranked[0].score or 0.0
    floor = max(TOPIC_MIN_SCORE, best - TOPIC_SCORE_GAP)
    return [hit for hit in ranked if (hit.score or 0.0) >= floor]


def _chunks_with_embeddings(
    files: list[Path],
    *,
    embed_texts,
    cache_path: Path | None,
) -> list[Chunk]:
    cache = _load_cache(cache_path)
    rebuilt: dict[str, dict] = {}
    fresh: list[Chunk] = []
    pending: list[Chunk] = []
    order: list[str] = []
    for path in files:
        key = str(path.resolve())
        signature = path.stat().st_mtime_ns
        cached = cache.get(key)
        if cached and cached.get("mtime_ns") == signature and _cache_has_vectors(cached):
            rebuilt[key] = cached
            fresh.extend(_chunks_from_cache(key, cached))
            continue
        parsed = parse_chunks(path, path.read_text(encoding="utf-8", errors="replace"))
        pending.extend(parsed)
        order.append(key)
        rebuilt[key] = {
            "mtime_ns": signature,
            "chunks": [
                {"speaker": chunk.speaker, "text": chunk.text, "spoken_at": chunk.spoken_at}
                for chunk in parsed
            ],
        }
    if pending and embed_texts is not None:
        vectors = embed_texts([chunk.text for chunk in pending])
        cursor = 0
        embedded: list[Chunk] = []
        for key in order:
            for item in rebuilt[key]["chunks"]:
                vector = list(vectors[cursor])
                item["embedding"] = vector
                source = pending[cursor]
                embedded.append(
                    Chunk(
                        path=key,
                        speaker=source.speaker,
                        text=source.text,
                        spoken_at=source.spoken_at,
                        embedding=tuple(float(value) for value in vector),
                    )
                )
                cursor += 1
        pending = embedded
    if cache_path is not None and rebuilt != cache:
        _save_cache(cache_path, rebuilt)
    return fresh + pending


def _cache_has_vectors(payload: dict) -> bool:
    chunks = payload.get("chunks") or []
    return bool(chunks) and all(item.get("embedding") for item in chunks)


def _chunks_from_cache(key: str, payload: dict) -> list[Chunk]:
    chunks: list[Chunk] = []
    for item in payload.get("chunks") or []:
        vector = item.get("embedding")
        chunks.append(
            Chunk(
                path=key,
                speaker=str(item.get("speaker") or ""),
                text=str(item.get("text") or ""),
                spoken_at=str(item.get("spoken_at") or ""),
                embedding=tuple(float(value) for value in vector) if vector else None,
            )
        )
    return chunks


def cache_path() -> Path:
    return data_dir() / "search-cache.json"


def embed_texts(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    vectors = _model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
    return [vector.tolist() for vector in vectors]


def _load_cache(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    files = payload.get("files")
    return files if isinstance(files, dict) else {}


def _save_cache(path: Path, files: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"files": files}), encoding="utf-8")


def _snippet(text: str, needle: str) -> str:
    compact = " ".join(text.split())
    if not needle:
        return compact[:180]
    index = compact.casefold().find(needle)
    if index < 0:
        return compact[:180]
    start = max(0, index - 40)
    end = min(len(compact), index + len(needle) + 80)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return prefix + compact[start:end] + suffix
