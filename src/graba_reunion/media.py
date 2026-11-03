"""Extensiones de audio y video reconocidas por el CLI y el visor."""
from __future__ import annotations

MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".ogv": "video/ogg",
    ".avi": "video/x-msvideo",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}

MEDIA_SUFFIXES = frozenset(MEDIA_TYPES)
VIDEO_SUFFIXES = frozenset(
    suffix for suffix, mime in MEDIA_TYPES.items() if mime.startswith("video/")
)


def is_media_path(path) -> bool:
    from pathlib import Path

    candidate = Path(path)
    return candidate.suffix.lower() in MEDIA_SUFFIXES
