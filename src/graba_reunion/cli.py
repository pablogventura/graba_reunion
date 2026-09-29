"""CLI principal de graba-reunion."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graba_reunion.commands.check_deps import cmd_check_deps
from graba_reunion.commands.list_show import cmd_list, cmd_show
from graba_reunion.commands.record import run_record_flow
from graba_reunion.commands.search_cmd import cmd_search
from graba_reunion.commands.setup_cmd import cmd_setup
from graba_reunion.commands.voices_cmd import cmd_voices
from graba_reunion.config import DEFAULT_GROQ_MODEL, load_settings
from graba_reunion.paths import default_output_dir

SUBCOMMANDS = {"list", "show", "record", "setup", "check-deps", "voices", "search"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Graba reunión (mic + monitor) y transcribe. "
            "Con --groq genera una minuta en markdown."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
ejemplos:
  graba-reunion
      Grabar y transcribir (sin minuta Groq).
  graba-reunion --groq
      Grabar, transcribir y minuta Groq.
  graba-reunion -d .
      Grabar en el directorio actual (en vez del data dir).
  graba-reunion --transcribe-only reunion.mp3
      Transcribir un MP3 existente (sin grabar).
  graba-reunion --transcribe-only reunion.mp3 --no-diarize
      Solo transcripción, sin diarización.
  graba-reunion record
      Igual que sin subcomando; las mismas opciones aplican.
  graba-reunion list
      Listar reuniones (1 = más reciente).
  graba-reunion show 1 --transcript
      Ver transcripción de la reunión más reciente.
  graba-reunion search "entrega del laboratorio"
      Buscar por tema. --word busca la frase literal. --participant filtra el hablante.

Las opciones de grabación/transcripción funcionan con o sin el subcomando record.""",
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directorio de salida (default: GRABA_OUTPUT_DIR o "
            "$XDG_DATA_HOME/graba-reunion/recordings)."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="Listar reuniones (1 = más reciente).")
    _add_output_args(list_parser)
    list_parser.set_defaults(command="list")

    show_parser = subparsers.add_parser("show", help="Mostrar reunión por número.")
    _add_output_args(show_parser)
    show_parser.add_argument("rank", type=int, metavar="N")
    show_parser.add_argument("--transcript", action="store_true")
    show_parser.add_argument("--all", action="store_true")
    show_parser.set_defaults(command="show")

    setup_parser = subparsers.add_parser("setup", help="Wizard de configuración (.env).")
    setup_parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Instalar/reparar dependencias Python (torch CUDA).",
    )
    setup_parser.add_argument(
        "-y",
        action="store_true",
        help="Sin confirmación (con --install-deps).",
    )
    setup_parser.set_defaults(command="setup")

    check_parser = subparsers.add_parser("check-deps", help="Verificar dependencias.")
    check_parser.set_defaults(command="check-deps")

    voices_parser = subparsers.add_parser(
        "voices",
        help="Nombrar voces con las grabaciones existentes.",
    )
    _add_output_args(voices_parser)
    voices_parser.add_argument(
        "--prepare",
        action="store_true",
        help="Solo extraer clips y escribir nombres.txt.",
    )
    voices_parser.add_argument(
        "--apply",
        action="store_true",
        help="Guardar los nombres de nombres.txt como perfiles.",
    )
    voices_parser.set_defaults(command="voices")

    search_parser = subparsers.add_parser("search", help="Buscar en las transcripciones.")
    _add_output_args(search_parser)
    search_parser.add_argument("query", nargs="?", default="", help="Tema o palabras.")
    search_parser.add_argument(
        "--word",
        action="store_true",
        help="Coincidencia literal, sin distinguir mayúsculas.",
    )
    search_parser.add_argument(
        "--participant",
        default="",
        help="Limitar a un hablante. Sin consulta, lista sus intervenciones.",
    )
    search_parser.add_argument(
        "--json",
        action="store_true",
        help="Imprimir los resultados en JSON.",
    )
    search_parser.set_defaults(command="search")

    record_parser = subparsers.add_parser("record", help="Grabar reunión.")
    _add_output_args(record_parser)
    _add_record_args(record_parser)
    record_parser.set_defaults(command="record")

    if len(sys.argv) <= 1 or sys.argv[1] not in SUBCOMMANDS:
        _add_record_args(parser)

    return parser.parse_args()


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directorio de salida (default: GRABA_OUTPUT_DIR o "
            "$XDG_DATA_HOME/graba-reunion/recordings)."
        ),
    )


def _add_record_args(parser: argparse.ArgumentParser) -> None:
    settings = load_settings()
    parser.add_argument(
        "--mic",
        default=settings.graba_mic,
        help="Fuente de micrófono (Pulse o ALSA según GRABA_AUDIO_BACKEND).",
    )
    parser.add_argument(
        "--mon",
        default=settings.graba_mon,
        help="Monitor/mezcla de salida (Pulse o ALSA).",
    )
    parser.add_argument(
        "--language",
        default=settings.whisperx_language,
        help="Idioma para Whisper/WhisperX (código ISO, p. ej. es).",
    )
    parser.add_argument(
        "--model",
        default=settings.whisperx_model,
        dest="model_size_or_path",
        help="Modelo Whisper/WhisperX (p. ej. large-v3).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Dispositivo de inferencia (cuda/cpu). Default: GRABA_WHISPERX_DEVICE.",
    )
    parser.add_argument(
        "--transcribe-only",
        type=Path,
        metavar="MP3",
        help="Solo transcribir un MP3 existente (sin grabar).",
    )
    parser.add_argument(
        "--no-diarize",
        action="store_true",
        help="Desactivar diarización de hablantes.",
    )
    parser.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Grabar audio sin transcribir.",
    )
    parser.add_argument(
        "--min-mp3-bytes",
        type=int,
        default=256,
        metavar="N",
        help="Tamaño mínimo del MP3 (bytes) para intentar transcribir.",
    )
    parser.add_argument(
        "--groq",
        action="store_true",
        help="Generar título y minuta con Groq.",
    )
    parser.add_argument(
        "--skip-groq",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--groq-model",
        default=settings.groq_model,
        help="Modelo Groq para título y minuta (requiere --groq).",
    )
    parser.add_argument(
        "--enrich-only",
        type=Path,
        metavar="TXT",
        help="Solo enriquecer un TXT existente con Groq (título + minuta).",
    )


def main() -> int:
    args = parse_args()
    command = getattr(args, "command", None)
    output_dir = args.output_dir if args.output_dir is not None else default_output_dir()

    if command == "list":
        return cmd_list(output_dir)
    if command == "show":
        return cmd_show(
            output_dir,
            args.rank,
            show_transcript=args.transcript,
            show_all=args.all,
        )
    if command == "setup":
        return cmd_setup(install_deps=args.install_deps, yes=args.y)
    if command == "check-deps":
        return cmd_check_deps()
    if command == "voices":
        return cmd_voices(
            output_dir,
            prepare_only=bool(getattr(args, "prepare", False)),
            apply_only=bool(getattr(args, "apply", False)),
        )
    if command == "search":
        return cmd_search(
            output_dir,
            getattr(args, "query", ""),
            word=bool(getattr(args, "word", False)),
            participant=getattr(args, "participant", ""),
            as_json=bool(getattr(args, "json", False)),
        )

    enrich_only = getattr(args, "enrich_only", None)
    use_groq = bool(getattr(args, "groq", False))
    if getattr(args, "skip_groq", False):
        use_groq = False
    if enrich_only is not None:
        use_groq = True

    return run_record_flow(
        output_dir=output_dir,
        mic=getattr(args, "mic", ""),
        mon=getattr(args, "mon", ""),
        language=getattr(args, "language", "es"),
        model=getattr(args, "model_size_or_path", "large-v3"),
        device=getattr(args, "device", None),
        transcribe_only=getattr(args, "transcribe_only", None),
        enrich_only=enrich_only,
        no_diarize=getattr(args, "no_diarize", False),
        skip_transcribe=getattr(args, "skip_transcribe", False),
        skip_groq=not use_groq,
        min_mp3_bytes=getattr(args, "min_mp3_bytes", 256),
        groq_model=getattr(args, "groq_model", DEFAULT_GROQ_MODEL),
    )


def entrypoint() -> None:
    sys.exit(main())
