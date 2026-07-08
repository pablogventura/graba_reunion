"""Rutas de sesión y base de datos."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from graba_reunion.config import load_settings


@dataclass(frozen=True)
class SessionPaths:
    base: str
    mp3: Path
    srt: Path
    txt: Path


def session_paths(output_dir: Path) -> SessionPaths:
    base = f"reunion_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    directory = output_dir.resolve()
    return SessionPaths(
        base=base,
        mp3=directory / f"{base}.mp3",
        srt=directory / f"{base}.srt",
        txt=directory / f"{base}.txt",
    )


def resolve_db_path(output_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    settings = load_settings()
    if settings.graba_db:
        return Path(settings.graba_db).expanduser().resolve()
    env_db = os.environ.get("GRABA_DB", "").strip()
    if env_db:
        return Path(env_db).expanduser().resolve()
    return output_dir.resolve() / "reunions.db"
