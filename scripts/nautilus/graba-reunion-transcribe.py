"""Ítem Transcribir en el menú contextual de Nautilus."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Nautilus", "4.1")

from gi.repository import GObject, Nautilus  # noqa: E402


def media_paths(files: list) -> list[str] | None:
    """Rutas locales si todos los archivos elegidos son audio o video."""
    paths: list[str] = []
    for info in files:
        if info.is_directory():
            return None
        mime = info.get_mime_type() or ""
        if not (mime.startswith("audio/") or mime.startswith("video/")):
            return None
        uri = info.get_uri() or ""
        if not uri.startswith("file:"):
            return None
        paths.append(unquote(urlparse(uri).path))
    if not paths:
        return None
    return paths


def transcribe_command(paths: list[str]) -> list[str]:
    binary = shutil.which("graba-reunion") or str(Path.home() / ".local/bin/graba-reunion")
    return ["x-terminal-emulator", "--", binary, "transcribe", "--", *paths]


class TranscribeProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files):
        paths = media_paths(list(files or []))
        if paths is None:
            return []
        item = Nautilus.MenuItem.new(
            "GrabaReunion::transcribe",
            "Transcribir",
            "Transcribe el audio y deja el texto al lado del archivo",
            "audio-x-generic",
        )
        item.connect("activate", self._on_activate, paths)
        return [item]

    def _on_activate(self, _item: Nautilus.MenuItem, paths: list[str]) -> None:
        subprocess.Popen(transcribe_command(paths), start_new_session=True)
