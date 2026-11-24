"""Instala el lanzador del indicador de mic y el .desktop de autostart."""
from __future__ import annotations

import os
from pathlib import Path

import graba_reunion

LAUNCHER_NAME = "graba-reunion-mic"
DESKTOP_NAME = "graba-reunion-mic.desktop"


def package_pythonpath() -> Path:
    """Directorio que debe ir en PYTHONPATH para importar graba_reunion."""
    # .../graba_reunion/__init__.py -> parent package dir (src/ o site-packages/)
    return Path(graba_reunion.__file__).resolve().parent.parent


def default_bin_dir() -> Path:
    override = os.environ.get("GRABA_BIN_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_BIN_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser()
    return Path.home() / ".local" / "bin"


def default_autostart_dir() -> Path:
    override = os.environ.get("GRABA_AUTOSTART_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "autostart"


def launcher_script(*, pythonpath: Path | None = None, python_bin: str = "/usr/bin/python3") -> str:
    root = pythonpath or package_pythonpath()
    return (
        "#!/bin/sh\n"
        "# Generado por graba-reunion setup. PyGObject del Python del sistema;\n"
        "# el código viene del paquete instalado (pipx/editable).\n"
        f'export PYTHONPATH="{root}${{PYTHONPATH:+:$PYTHONPATH}}"\n'
        f"exec {python_bin} -c 'from graba_reunion.mic_indicator import main; main()'\n"
    )


def desktop_entry(*, exec_path: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=graba-reunion mic\n"
        "Comment=Graba reuniones cuando otra app usa el micrófono\n"
        f"Exec={exec_path}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n"
        "Categories=Audio;Utility;\n"
    )


def install_mic_autostart(
    *,
    bin_dir: Path | None = None,
    autostart_dir: Path | None = None,
    pythonpath: Path | None = None,
    python_bin: str = "/usr/bin/python3",
) -> tuple[Path, Path]:
    """Escribe el lanzador y el .desktop. Devuelve (launcher, desktop)."""
    target_bin = bin_dir or default_bin_dir()
    target_autostart = autostart_dir or default_autostart_dir()
    target_bin.mkdir(parents=True, exist_ok=True)
    target_autostart.mkdir(parents=True, exist_ok=True)

    launcher = target_bin / LAUNCHER_NAME
    launcher.write_text(
        launcher_script(pythonpath=pythonpath, python_bin=python_bin),
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | 0o111)

    desktop = target_autostart / DESKTOP_NAME
    desktop.write_text(desktop_entry(exec_path=launcher.resolve()), encoding="utf-8")
    return launcher, desktop
