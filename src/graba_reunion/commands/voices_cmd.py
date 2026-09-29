"""CLI para nombrar voces a partir de grabaciones ya hechas."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.config import load_settings
from graba_reunion.transcription.whisperx import validate_diarization_prereqs
from graba_reunion.voice_enroll import load_review, prepare_review
from graba_reunion.voices import (
    bank_from_names,
    format_duration,
    names_path,
    parse_names_file,
    render_names_file,
    save_voice_bank,
)


def cmd_voices(output_dir: Path, *, prepare_only: bool, apply_only: bool) -> int:
    if apply_only:
        return _apply_names()
    error = validate_diarization_prereqs()
    if error:
        print(error, file=sys.stderr)
        return 1
    mp3_paths = sorted(path for path in output_dir.glob("*.mp3") if path.is_file())
    if not mp3_paths:
        print(f"No hay MP3 en {output_dir}", file=sys.stderr)
        return 1
    settings = load_settings()
    clusters = prepare_review(
        mp3_paths,
        device=settings.whisperx_device or "cpu",
        token=settings.hf_token,
    )
    destination = names_path()
    if not destination.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_names_file(clusters), encoding="utf-8")
    print(f"Clips y lista: {destination}")
    if prepare_only or not sys.stdin.isatty():
        print("Completá el nombre en cada línea `N=` y después: graba-reunion voices --apply")
        return 0
    names = _prompt_names(clusters)
    bank = bank_from_names(clusters, names)
    if not bank.profiles:
        print("No se guardó ninguna voz.", file=sys.stderr)
        return 1
    path = save_voice_bank(bank)
    _print_saved(bank, path)
    return 0


def _apply_names() -> int:
    try:
        clusters = load_review()
    except OSError as error:
        print(f"No hay voces preparadas ({error}). Corré: graba-reunion voices", file=sys.stderr)
        return 1
    try:
        text = names_path().read_text(encoding="utf-8")
    except OSError as error:
        print(f"No se pudo leer {names_path()}: {error}", file=sys.stderr)
        return 1
    bank = bank_from_names(clusters, parse_names_file(text))
    if not bank.profiles:
        print(f"No hay nombres en {names_path()}", file=sys.stderr)
        return 1
    path = save_voice_bank(bank)
    _print_saved(bank, path)
    return 0


def _prompt_names(clusters: list) -> dict[int, str]:
    names: dict[int, str] = {}
    for cluster in clusters:
        speech = sum(track.speech_seconds for track in cluster.tracks)
        sources = ", ".join(sorted({track.source_name for track in cluster.tracks}))
        print(f"\n{cluster.cluster_id}  {format_duration(speech)}  {sources}")
        if cluster.clip_path:
            print(f"clip: {cluster.clip_path}")
        try:
            entered = input("Nombre (vacío = omitir): ")
        except EOFError:
            entered = ""
        names[cluster.cluster_id] = " ".join(entered.strip().split())
    return names


def _print_saved(bank, path: Path) -> None:
    saved = ", ".join(profile.name for profile in bank.profiles)
    print(f"Perfiles guardados en {path}: {saved}")
    print("Las próximas transcripciones usan estos nombres cuando la voz coincide.")
