"""Helpers HTTP del hub: búsqueda, minuta, frases, transcripción y voces."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs

from graba_reunion.commands.phrases_cmd import cmd_phrases
from graba_reunion.commands.transcribe_cmd import cmd_transcribe
from graba_reunion.commands.voice_wizard import (
    merge_voice_pair,
    save_submitted_names,
    similar_payload,
    voice_payload,
)
from graba_reunion.config import DEFAULT_GROQ_MODEL, load_settings
from graba_reunion.enrichment import enrich_and_store
from graba_reunion.media import MEDIA_SUFFIXES
from graba_reunion.phrases import start_for_clock
from graba_reunion.search import cache_path, embed_texts, search_transcripts
from graba_reunion.voice_enroll import load_review
from graba_reunion.voices import load_voice_bank

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_JSON_BYTES = 2_000_000


def search_hits(directory: Path, query: str, *, word: bool, participant: str) -> list[dict]:
    use_embed = not word and not (participant and not query.strip())
    hits = search_transcripts(
        directory,
        query,
        word=word,
        participant=participant,
        embed_texts=embed_texts if use_embed else None,
        cache_path=cache_path() if use_embed else None,
    )
    rows: list[dict] = []
    for hit in hits:
        path = Path(hit.path)
        start = start_for_clock(path, hit.spoken_at) if hit.spoken_at else None
        rows.append(
            {
                "id": path.stem,
                "path": path.name,
                "speaker": hit.speaker,
                "snippet": hit.snippet,
                "score": hit.score,
                "spoken_at": hit.spoken_at,
                "t": start,
            }
        )
    return rows


def write_minutes(txt: Path, markdown: str) -> Path:
    destination = txt.with_name(f"{txt.stem}_minuta.md")
    destination.write_text(markdown, encoding="utf-8")
    return destination


def generate_minutes(txt: Path, media: Path | None) -> Path:
    settings = load_settings()
    audio = media if media is not None else txt
    code = enrich_and_store(
        session_base=txt.stem,
        mp3=audio,
        txt=txt,
        groq_model=settings.groq_model or DEFAULT_GROQ_MODEL,
        language=settings.whisperx_language,
    )
    if code != 0:
        raise RuntimeError("No se pudo generar la minuta con Groq.")
    return txt.with_name(f"{txt.stem}_minuta.md")


def regenerate_phrases(directory: Path, media: Path) -> None:
    code = cmd_phrases(directory, media)
    if code != 0:
        raise RuntimeError("No se pudieron regenerar las frases.")


def transcribe_uploads(directory: Path, files: list[tuple[str, bytes]]) -> list[str]:
    if not files:
        raise ValueError("No llegó ningún archivo.")
    saved: list[Path] = []
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in files:
        safe = _safe_upload_name(name)
        if safe is None:
            raise ValueError(f"Extensión no soportada: {name}")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("El archivo supera el límite de 500 MiB.")
        target = _unique_path(directory / safe)
        target.write_bytes(payload)
        saved.append(target)
    code = cmd_transcribe(saved, open_viewer=False)
    if code != 0:
        raise RuntimeError("Falló la transcripción.")
    return [path.stem for path in saved if path.with_suffix(".txt").is_file()]


def load_voice_clusters():
    try:
        return load_review()
    except OSError:
        return []


def voices_status() -> dict:
    clusters = load_voice_clusters()
    bank = load_voice_bank()
    return {
        "ready": bool(clusters),
        "cluster_count": len(clusters),
        "profile_count": len(bank.profiles),
        "message": (
            ""
            if clusters
            else "No hay review.json. Corré: graba-reunion voices (prepare) o voices --web."
        ),
    }


def voices_get() -> dict:
    clusters = load_voice_clusters()
    if not clusters:
        return {"known_names": [], "voices": [], "ready": False, **voices_status()}
    payload = voice_payload(clusters)
    payload["ready"] = True
    return payload


def similar_get() -> dict:
    clusters = load_voice_clusters()
    if not clusters:
        return {"threshold": 0, "pairs": [], "voices": [], "ready": False, **voices_status()}
    payload = similar_payload(clusters)
    payload["ready"] = True
    return payload


def voices_save(raw_names: dict) -> dict:
    clusters = load_voice_clusters()
    if not clusters:
        raise RuntimeError(voices_status()["message"])
    return save_submitted_names(clusters, raw_names)


def voices_merge(left_id: int, right_id: int, name: str) -> dict:
    clusters = load_voice_clusters()
    if not clusters:
        raise RuntimeError(voices_status()["message"])
    return merge_voice_pair(clusters, left_id, right_id, name)


def parse_query_bool(values: list[str]) -> bool:
    if not values:
        return False
    return values[0].lower() in {"1", "true", "yes", "on"}


def parse_search_query(query: str) -> tuple[str, bool, str]:
    params = parse_qs(query, keep_blank_values=True)
    q = (params.get("q") or [""])[0]
    participant = (params.get("participant") or [""])[0]
    word = parse_query_bool(params.get("word") or [])
    return q, word, participant


def parse_json_body(raw: bytes) -> dict:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Cuerpo demasiado grande.")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("El pedido no es un objeto JSON.")
    return payload


def extract_multipart_files(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    match = re.search(r"boundary=([^;]+)", content_type or "", flags=re.I)
    if not match:
        raise ValueError("Falta boundary multipart.")
    boundary = match.group(1).strip().strip('"').encode("utf-8")
    if not boundary:
        raise ValueError("Boundary vacío.")
    delimiter = b"--" + boundary
    parts = body.split(delimiter)
    files: list[tuple[str, bytes]] = []
    for part in parts:
        chunk = part
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk in {b"", b"--", b"--\r\n", b"\r\n"}:
            continue
        if chunk.startswith(b"--"):
            continue
        header_blob, separator, payload = chunk.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        if "filename=" not in headers.lower():
            continue
        name_match = re.search(r'filename="([^"]*)"', headers, flags=re.I)
        if name_match is None:
            name_match = re.search(r"filename=([^;\r\n]+)", headers, flags=re.I)
        filename = (name_match.group(1).strip() if name_match else "upload.bin")
        data = payload
        if data.endswith(b"\r\n"):
            data = data[:-2]
        if data.endswith(b"--"):
            data = data[:-2]
            if data.endswith(b"\r\n"):
                data = data[:-2]
        files.append((filename, data))
    return files


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _safe_upload_name(name: str) -> str | None:
    base = Path(name).name
    if not base or base in {".", ".."} or "/" in base or "\\" in base:
        return None
    suffix = Path(base).suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        return None
    stem = Path(base).stem.strip() or "upload"
    stem = re.sub(r"[^\w.\- ]+", "_", stem, flags=re.UNICODE)[:80]
    return f"{stem}{suffix}"
