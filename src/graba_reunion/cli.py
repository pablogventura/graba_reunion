"""
Graba micrófono + monitor PulseAudio, mezcla a MP3 y transcribe con diarización (WhisperX).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# WhisperX + pyannote (valores de ../diarizacion/run_whisperx.sh)
WHISPERX_BIN = (
    Path(__file__).resolve().parents[2].parent / "diarizacion" / ".venv" / "bin" / "whisperx"
)
WHISPERX_MODEL = "large-v3"
WHISPERX_LANGUAGE = "es"
WHISPERX_DEVICE = "cuda"
WHISPERX_COMPUTE_TYPE = "float16"
WHISPERX_BATCH_SIZE = 16
WHISPERX_SIDE_EXTENSIONS = (".srt", ".json", ".vtt", ".tsv")

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


def _diarizacion_dir() -> Path:
    return Path(__file__).resolve().parents[2].parent / "diarizacion"


def load_hf_token() -> str:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    env_file = _diarizacion_dir() / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("HF_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def resolve_whisperx_bin() -> Path | None:
    if WHISPERX_BIN.is_file():
        return WHISPERX_BIN
    found = shutil.which("whisperx")
    return Path(found) if found else None


def validate_diarization_prereqs() -> str | None:
    if not load_hf_token():
        return (
            "HF_TOKEN no configurado. Exportalo o definilo en ../diarizacion/.env "
            "(acceso a pyannote/speaker-diarization-community-1)."
        )
    if resolve_whisperx_bin() is None:
        return (
            "No se encontró whisperx. Instalá WhisperX en ../diarizacion (ver README) "
            "o agregá whisperx al PATH."
        )
    return None


def validate_faster_whisper_prereqs() -> str | None:
    if shutil.which("faster-whisper") is None:
        return "No se encontró faster-whisper en PATH (requerido con --no-diarize)."
    return None


def cleanup_whisperx_side_artifacts(output_dir: Path, base: str) -> None:
    for ext in WHISPERX_SIDE_EXTENSIONS:
        side = output_dir / f"{base}{ext}"
        if side.is_file():
            side.unlink()


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


def transcribe_faster_whisper(
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


def transcribe_with_diarization(mp3: Path, *, output_dir: Path) -> None:
    whisperx = resolve_whisperx_bin()
    if whisperx is None:
        raise FileNotFoundError(
            "No se encontró whisperx. Instalá WhisperX (ver README) o verificá WHISPERX_BIN en cli.py."
        )

    subprocess.run(
        [
            str(whisperx),
            str(mp3),
            "--model",
            WHISPERX_MODEL,
            "--language",
            WHISPERX_LANGUAGE,
            "--diarize",
            "--hf_token",
            load_hf_token(),
            "--device",
            WHISPERX_DEVICE,
            "--compute_type",
            WHISPERX_COMPUTE_TYPE,
            "--batch_size",
            str(WHISPERX_BATCH_SIZE),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "txt",
        ],
        check=True,
        env={**os.environ, "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "true"},
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Graba reunión (mic + monitor) y transcribe a TXT (con diarización por defecto)."
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
        help="Idioma para faster-whisper con --no-diarize (por defecto es).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("GRABA_MODEL", "large-v3"),
        dest="model_size_or_path",
        help="Modelo faster-whisper con --no-diarize (por defecto large-v3 o GRABA_MODEL).",
    )
    p.add_argument(
        "--transcribe-only",
        type=Path,
        metavar="MP3",
        help="Transcribir un MP3 existente sin grabar.",
    )
    p.add_argument(
        "--no-diarize",
        action="store_true",
        help="Transcribir con faster-whisper (TXT plano, sin etiquetas de hablante).",
    )
    p.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Solo grabar; no transcribir al terminar.",
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
    base: str,
    diarize: bool,
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

    if diarize:
        print("\nTranscribiendo con diarización…")
        try:
            transcribe_with_diarization(mp3, output_dir=mp3.parent)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as e:
            print(f"Error en whisperx (código {e.returncode}).", file=sys.stderr)
            return 1

        if not txt.is_file():
            print(f"No se generó el TXT esperado: {txt}", file=sys.stderr)
            return 1

        cleanup_whisperx_side_artifacts(mp3.parent, base)

        print("Listo:")
        print(mp3)
        print(txt)
        return 0

    print("\nTranscribiendo…")
    try:
        transcribe_faster_whisper(
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

    if args.transcribe_only is not None:
        mp3 = args.transcribe_only.expanduser().resolve()
        if not mp3.is_file():
            print(f"No existe el MP3: {mp3}", file=sys.stderr)
            return 1

        if args.no_diarize:
            err = validate_faster_whisper_prereqs()
        else:
            err = validate_diarization_prereqs()
        if err:
            print(err, file=sys.stderr)
            return 1

        return transcribe_and_write_txt(
            mp3,
            mp3.with_suffix(".srt"),
            mp3.with_suffix(".txt"),
            base=mp3.stem,
            diarize=not args.no_diarize,
            language=args.language,
            model=args.model_size_or_path,
            min_mp3_bytes=args.min_mp3_bytes,
        )

    paths = session_paths(args.output_dir)
    mp3, srt, txt = paths.mp3, paths.srt, paths.txt

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_transcribe:
        if args.no_diarize:
            err = validate_faster_whisper_prereqs()
        else:
            err = validate_diarization_prereqs()
        if err:
            print(err, file=sys.stderr)
            return 1

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
        base=paths.base,
        diarize=not args.no_diarize,
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
