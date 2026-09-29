"""Comando search."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.search import cache_path, embed_texts, hits_as_json, search_transcripts


def cmd_search(
    output_dir: Path,
    query: str,
    *,
    word: bool,
    participant: str,
    as_json: bool,
) -> int:
    try:
        hits = search_transcripts(
            output_dir,
            query,
            word=word,
            participant=participant,
            embed_texts=None if word or (participant and not query.strip()) else embed_texts,
            cache_path=cache_path(),
        )
    except Exception as error:
        print(f"No se pudo buscar: {error}", file=sys.stderr)
        return 1
    if as_json:
        print(hits_as_json(hits))
        return 0
    if not hits:
        print("Sin resultados.")
        return 0
    for hit in hits:
        score = f"  {hit.score:.3f}" if hit.score is not None else ""
        speaker = f"{hit.speaker}: " if hit.speaker else ""
        print(f"{Path(hit.path).name}{score}")
        print(f"  {speaker}{hit.snippet}")
    return 0
