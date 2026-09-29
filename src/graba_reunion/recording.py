"""Grabación de audio con ffmpeg."""
from __future__ import annotations

import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from graba_reunion.timing import mark_duration, mark_started, probe_duration_seconds


def build_ffmpeg_cmd(
    mic: str,
    mon: str,
    mp3: Path,
    *,
    backend: str = "pulse",
) -> list[str]:
    fmt = "alsa" if backend == "alsa" else "pulse"
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-f",
        fmt,
        "-i",
        mic,
        "-f",
        fmt,
        "-i",
        mon,
        "-filter_complex",
        "amix=inputs=2:duration=longest:normalize=0",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        "-y",
        str(mp3),
    ]


def record_until_signal(
    mic: str,
    mon: str,
    mp3: Path,
    *,
    backend: str = "pulse",
) -> int:
    proc_holder: dict[str, subprocess.Popen | None] = {"process": None}

    def on_signal(_signum: int, _frame: object | None) -> None:
        process = proc_holder["process"]
        if process is not None and process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    command = build_ffmpeg_cmd(mic, mon, mp3, backend=backend)
    mark_started(mp3, datetime.now())
    print(f"Grabando en {mp3}")
    print("Para detener y transcribir: Ctrl+C o SIGTERM a este proceso.")
    print(f"Backend: {backend}")
    print(f"Mic: {mic}")
    print(f"Monitor: {mon}")

    process = subprocess.Popen(command)
    proc_holder["process"] = process
    return_code = -1
    try:
        return_code = process.wait()
    finally:
        proc_holder["process"] = None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    duration = probe_duration_seconds(mp3)
    if duration is not None:
        mark_duration(mp3, duration)

    if return_code != 0:
        print(f"ffmpeg terminó con código {return_code}.", file=sys.stderr)
        return min(max(return_code, 1), 255)
    return 0
