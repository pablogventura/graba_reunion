"""
Graba micrófono + monitor PulseAudio, mezcla a MP3 y transcribe con faster-whisper.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_MIC = (
    "alsa_input.usb-Kingston_Technology_Company_HyperX_Cloud_Flight_Wireless-00.mono-fallback"
)
DEFAULT_MON = (
    "alsa_output.usb-Kingston_Technology_Company_HyperX_Cloud_Flight_Wireless-00.analog-stereo.monitor"
)


@dataclass(frozen=True)
class SessionPaths:
    base: str
    mp3: Path
    srt: Path
    txt: Path


def session_paths(output_dir: Path) -> SessionPaths:
    base = f"reunion_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    d = output_dir.resolve()
    return SessionPaths(
        base=base,
        mp3=d / f"{base}.mp3",
        srt=d / f"{base}.srt",
        txt=d / f"{base}.txt",
    )


def srt_to_plaintext(srt_path: Path) -> str:
    """Convierte SRT a un solo párrafo (respeta bloques y líneas de texto)."""
    raw = srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    chunks: list[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        i = 0
        if lines[0].isdigit():
            i = 1
        if i < len(lines) and "-->" in lines[i]:
            i += 1
        text = " ".join(lines[i:])
        if text:
            chunks.append(text)
    return " ".join(chunks)


def build_ffmpeg_cmd(mic: str, mon: str, mp3: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-f",
        "pulse",
        "-i",
        mic,
        "-f",
        "pulse",
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


def transcribe(
    mp3: Path,
    *,
    language: str,
    model: str,
    srt_out: Path,
) -> None:
    subprocess.run(
        [
            "faster-whisper",
            str(mp3),
            "-o",
            str(srt_out),
            "--language",
            language,
            "--model_size_or_path",
            model,
        ],
        check=True,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Graba reunión (mic + monitor) y transcribe a SRT/TXT."
    )
    p.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directorio de salida (por defecto el actual).",
    )
    p.add_argument(
        "--mic",
        default=os.environ.get("GRABA_MIC", DEFAULT_MIC),
        help="Fuente PulseAudio del micrófono (o variable GRABA_MIC).",
    )
    p.add_argument(
        "--mon",
        default=os.environ.get("GRABA_MON", DEFAULT_MON),
        help="Monitor del auricular/salida (o variable GRABA_MON).",
    )
    p.add_argument(
        "--language",
        default="es",
        help="Idioma para faster-whisper (por defecto es).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("GRABA_MODEL", "large-v3"),
        dest="model_size_or_path",
        help="Modelo faster-whisper (por defecto large-v3 o GRABA_MODEL).",
    )
    p.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Solo grabar; no ejecutar faster-whisper al terminar.",
    )
    p.add_argument(
        "--min-mp3-bytes",
        type=int,
        default=256,
        metavar="N",
        help="No transcribir si el MP3 es más pequeño que N bytes.",
    )
    return p.parse_args()


def transcribe_and_write_txt(
    mp3: Path,
    srt: Path,
    txt: Path,
    *,
    language: str,
    model: str,
    min_mp3_bytes: int,
) -> int:
    if not mp3.is_file() or mp3.stat().st_size < min_mp3_bytes:
        print(
            f"\nNo hay MP3 usable (falta archivo o < {min_mp3_bytes} bytes); "
            "se omite la transcripción.",
            file=sys.stderr,
        )
        if mp3.is_file():
            print(mp3, file=sys.stderr)
        return 1

    print("\nTranscribiendo…")
    try:
        transcribe(
            mp3,
            language=language,
            model=model,
            srt_out=srt,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error en faster-whisper (código {e.returncode}).", file=sys.stderr)
        return 1

    try:
        plain = srt_to_plaintext(srt)
    except OSError as e:
        print(f"No se pudo leer el SRT: {e}", file=sys.stderr)
        return 1

    txt.write_text(plain, encoding="utf-8")
    print("Listo:")
    print(mp3)
    print(srt)
    print(txt)
    return 0


def main() -> int:
    args = parse_args()
    paths = session_paths(args.output_dir)
    mp3, srt, txt = paths.mp3, paths.srt, paths.txt

    args.output_dir.mkdir(parents=True, exist_ok=True)

    proc_holder: dict[str, subprocess.Popen | None] = {"p": None}

    def on_signal(_signum: int, _frame: object | None) -> None:
        p = proc_holder["p"]
        if p is not None and p.poll() is None:
            p.terminate()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    cmd = build_ffmpeg_cmd(args.mic, args.mon, mp3)
    print(f"Grabando en {mp3}")
    print("Para detener y transcribir: Ctrl+C o SIGTERM a este proceso.")
    print(f"Mic: {args.mic}")
    print(f"Monitor: {args.mon}")

    proc = subprocess.Popen(cmd)
    proc_holder["p"] = proc
    ret = -1
    try:
        ret = proc.wait()
    finally:
        proc_holder["p"] = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    if args.skip_transcribe:
        print("\nGrabación finalizada (sin transcripción).")
        print(mp3)
        exit_ffmpeg = 0 if ret == 0 else min(max(ret, 1), 255)
        return exit_ffmpeg

    tx = transcribe_and_write_txt(
        mp3,
        srt,
        txt,
        language=args.language,
        model=args.model_size_or_path,
        min_mp3_bytes=args.min_mp3_bytes,
    )

    if ret != 0:
        print(f"ffmpeg terminó con código {ret}.", file=sys.stderr)
        return min(max(ret, 1), 255)
    return tx


def entrypoint() -> None:
    """Punto de entrada para console_scripts (pip / pipx)."""
    sys.exit(main())
