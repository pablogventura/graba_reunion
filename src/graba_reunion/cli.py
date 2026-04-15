#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path


# === Configuración ===
MIC_SOURCE = "alsa_input.usb-Kingston_Technology_Company_HyperX_Cloud_Flight_Wireless-00.mono-fallback"
MONITOR_SOURCE = "alsa_output.usb-Kingston_Technology_Company_HyperX_Cloud_Flight_Wireless-00.analog-stereo.monitor"

OUTPUT_BASENAME = "grabacion"
AUDIO_FILE = f"{OUTPUT_BASENAME}.mp3"
SRT_FILE = f"{OUTPUT_BASENAME}.srt"
TXT_FILE = f"{OUTPUT_BASENAME}.txt"

LANGUAGE = "es"
MODEL = "large"   # podés cambiarlo por medium, small, etc.


def check_command(cmd: str) -> None:
    if subprocess.run(["which", cmd], capture_output=True, text=True).returncode != 0:
        print(f"Error: no encontré el comando '{cmd}' en el sistema.", file=sys.stderr)
        sys.exit(1)


def record_audio() -> None:
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "pulse",
        "-i", MIC_SOURCE,
        "-f", "pulse",
        "-i", MONITOR_SOURCE,
        "-filter_complex", "amix=inputs=2:duration=longest",
        "-c:a", "libmp3lame",
        "-q:a", "2",
        AUDIO_FILE,
    ]

    print(f"Grabando en {AUDIO_FILE}...")
    print("Apretá Enter para detener la grabación.\n")

    proc = subprocess.Popen(ffmpeg_cmd)

    try:
        input()
    except KeyboardInterrupt:
        pass

    print("Deteniendo grabación...")
    proc.send_signal(subprocess.signal.SIGINT)
    proc.wait()

    if proc.returncode not in (0, 255):
        print(f"ffmpeg terminó con código {proc.returncode}", file=sys.stderr)
        sys.exit(proc.returncode)


def transcribe() -> None:
    cmd = [
        "faster-whisper",
        AUDIO_FILE,
        "--language", LANGUAGE,
        "--model", MODEL,
    ]

    print("Transcribiendo con faster-whisper...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Error al ejecutar faster-whisper.", file=sys.stderr)
        sys.exit(result.returncode)

    if not Path(SRT_FILE).exists():
        print(f"No se generó {SRT_FILE}", file=sys.stderr)
        sys.exit(1)


def clean_srt_to_txt() -> None:
    print(f"Limpiando {SRT_FILE} -> {TXT_FILE}...")

    lines_out = []
    with open(SRT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()

            # eliminar líneas vacías
            if not stripped:
                continue

            # eliminar numeración de subtítulos
            if stripped.isdigit():
                continue

            # eliminar timestamps
            if "-->" in stripped:
                continue

            lines_out.append(stripped)

    text = "\n".join(lines_out).strip() + "\n"

    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Graba mic + monitor PulseAudio, transcribe y por defecto diariza (faster-whisper + pyannote).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Por defecto se usa diarización (pyannote + faster-whisper por API): "
            "HF_TOKEN (o --hf-token) y aceptar las "
            "condiciones en Hugging Face de pyannote/speaker-diarization-3.1 y "
            "pyannote/segmentation-3.0. Con --no-diarize solo hace falta el comando faster-whisper."
        ),
    )
    parser.add_argument(
        "--no-diarize",
        action="store_true",
        help="Transcribir solo con el ejecutable faster-whisper (sin pyannote ni etiquetas de hablante).",
    )
    parser.add_argument(
        "--hf-token",
        default=None,
        help="Token de Hugging Face (por defecto: variable HF_TOKEN; solo modo con diarización).",
    )
    parser.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default=None,
        help="Dispositivo para pyannote y faster-whisper (solo con diarización, que es el predeterminado).",
    )
    parser.add_argument(
        "--compute-type",
        default=None,
        metavar="TIPO",
        help="p. ej. float16, int8_float32 (solo con diarización; por defecto float16 en CUDA, int8 en CPU).",
    )
    args = parser.parse_args()

    use_diarize = not args.no_diarize

    check_command("ffmpeg")
    if not use_diarize:
        check_command("faster-whisper")

    record_audio()

    if use_diarize:
        from graba_reunion.diarize_asr import transcribe_with_diarization

        token = args.hf_token or os.environ.get("HF_TOKEN")
        transcribe_with_diarization(
            AUDIO_FILE,
            LANGUAGE,
            MODEL,
            SRT_FILE,
            TXT_FILE,
            hf_token=token,
            device=args.device,
            compute_type=args.compute_type,
        )
    else:
        transcribe()
        clean_srt_to_txt()

    print("\nListo.")
    print(f"Audio:         {AUDIO_FILE}")
    print(f"Subtítulos:    {SRT_FILE}")
    print(f"Transcripción: {TXT_FILE}")


if __name__ == "__main__":
    main()
