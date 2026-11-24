from __future__ import annotations

from pathlib import Path

from graba_reunion.mic_autostart import (
    desktop_entry,
    install_mic_autostart,
    launcher_script,
    package_pythonpath,
)


def test_launcher_and_desktop_content() -> None:
    root = Path("/tmp/fake-site")
    script = launcher_script(pythonpath=root, python_bin="/usr/bin/python3")
    assert 'PYTHONPATH="/tmp/fake-site' in script
    assert "graba_reunion.mic_indicator" in script
    assert script.startswith("#!/bin/sh\n")

    text = desktop_entry(exec_path=Path("/home/me/.local/bin/graba-reunion-mic"))
    assert "Exec=/home/me/.local/bin/graba-reunion-mic" in text
    assert "X-GNOME-Autostart-enabled=true" in text


def test_install_mic_autostart_writes_files(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    auto_dir = tmp_path / "autostart"
    py_path = tmp_path / "site"
    py_path.mkdir()
    launcher, desktop = install_mic_autostart(
        bin_dir=bin_dir,
        autostart_dir=auto_dir,
        pythonpath=py_path,
    )
    assert launcher == bin_dir / "graba-reunion-mic"
    assert desktop == auto_dir / "graba-reunion-mic.desktop"
    assert launcher.is_file()
    assert os_access_executable(launcher)
    body = launcher.read_text(encoding="utf-8")
    assert str(py_path) in body
    desk = desktop.read_text(encoding="utf-8")
    assert f"Exec={launcher.resolve()}" in desk


def test_package_pythonpath_points_at_import_root() -> None:
    root = package_pythonpath()
    assert (root / "graba_reunion").is_dir()


def os_access_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)
