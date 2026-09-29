"""Generación de minuta en un archivo .md junto al .txt."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.groq_summary import summarize_transcript


def enrich_and_store(
    *,
    session_base: str,
    mp3: Path,
    txt: Path,
    groq_model: str,
    language: str | None = None,
) -> int:
    try:
        transcript = txt.read_text(encoding="utf-8").strip()
    except OSError as error:
        print(f"No se pudo leer la transcripción: {error}", file=sys.stderr)
        return 1

    if not transcript:
        print(f"La transcripción está vacía: {txt}", file=sys.stderr)
        return 1

    print("\nGenerando título y minuta con Groq...")
    try:
        summary = summarize_transcript(transcript, model=groq_model, language=language)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error al llamar a Groq: {error}", file=sys.stderr)
        return 1

    minutes_path = txt.with_name(f"{session_base}_minuta.md")
    body = f"# {summary.title}\n\n{summary.minutes}"
    try:
        minutes_path.write_text(body, encoding="utf-8")
    except OSError as error:
        print(f"No se pudo escribir la minuta: {error}", file=sys.stderr)
        return 1

    print("Minuta:")
    print(f"  {summary.title}")
    print(f"  {minutes_path}")
    print(f"  audio: {mp3}")
    return 0
