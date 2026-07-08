"""Utilidades SRT."""
from __future__ import annotations

import re
from pathlib import Path


def srt_to_plaintext(srt_path: Path) -> str:
    """Convierte SRT a un solo párrafo (respeta bloques y líneas de texto)."""
    raw = srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    chunks: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        index = 0
        if lines[0].isdigit():
            index = 1
        if index < len(lines) and "-->" in lines[index]:
            index += 1
        text = " ".join(lines[index:])
        if text:
            chunks.append(text)
    return " ".join(chunks)


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[tuple[float, float, str]]) -> str:
    blocks: list[str] = []
    for index, (start, end, text) in enumerate(segments, start=1):
        cleaned = text.strip()
        if not cleaned:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_timestamp(start)} --> {format_timestamp(end)}",
                    cleaned,
                    "",
                ]
            )
        )
    return "\n".join(blocks)
