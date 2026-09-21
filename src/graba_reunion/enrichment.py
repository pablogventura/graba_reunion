"""Generación de minuta y persistencia."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.db import insert_meeting, parse_session_timestamp
from graba_reunion.groq_summary import summarize_transcript


def enrich_and_store(
    *,
    session_base: str,
    mp3: Path,
    txt: Path,
    db_path: Path,
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

    print("\nGenerando título y minuta con Groq…")
    try:
        summary = summarize_transcript(transcript, model=groq_model, language=language)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error al llamar a Groq: {error}", file=sys.stderr)
        return 1

    try:
        stored = insert_meeting(
            db_path,
            session_base=session_base,
            recorded_at=parse_session_timestamp(session_base),
            mp3_path=mp3,
            txt_path=txt,
            transcript=transcript,
            title=summary.title,
            minutes=summary.minutes,
            groq_model=summary.model,
        )
    except OSError as error:
        print(f"No se pudo escribir en SQLite: {error}", file=sys.stderr)
        return 1

    minutes_path = txt.with_name(f"{session_base}_minuta.md")
    try:
        minutes_path.write_text(summary.minutes, encoding="utf-8")
    except OSError as error:
        print(f"No se pudo escribir la minuta: {error}", file=sys.stderr)
        return 1

    print("Guardado en SQLite:")
    print(f"  #{stored.rank}  {stored.title}")
    print(f"  db: {db_path}")
    print(f"  minuta: {minutes_path}")
    print(f"  ver: graba-reunion show {stored.rank}")
    return 0
