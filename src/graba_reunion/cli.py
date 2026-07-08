"""CLI principal de graba-reunion."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graba_reunion.commands.check_deps import cmd_check_deps
from graba_reunion.commands.list_show import cmd_list, cmd_show
from graba_reunion.commands.record import run_record_flow
from graba_reunion.commands.setup_cmd import cmd_setup
from graba_reunion.config import DEFAULT_GROQ_MODEL, load_settings
from graba_reunion.paths import resolve_db_path

SUBCOMMANDS = {"list", "show", "record", "setup", "check-deps"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Graba reunión (mic + monitor), transcribe, genera minuta y guarda en SQLite."
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directorio de salida (por defecto el actual).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="PATH",
        help="Ruta SQLite (por defecto <output-dir>/reunions.db o GRABA_DB).",
    )

    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="Listar reuniones (1 = más reciente).")
    _add_db_args(list_parser)
    list_parser.set_defaults(command="list")

    show_parser = subparsers.add_parser("show", help="Mostrar reunión por número.")
    _add_db_args(show_parser)
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

    record_parser = subparsers.add_parser("record", help="Grabar reunión.")
    _add_db_args(record_parser)
    _add_record_args(record_parser)
    record_parser.set_defaults(command="record")

    if len(sys.argv) <= 1 or sys.argv[1] not in SUBCOMMANDS.union({"-h", "--help"}):
        _add_record_args(parser)

    return parser.parse_args()


def _add_db_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-d", "--output-dir", type=Path, default=Path("."))
    parser.add_argument("--db", type=Path, default=None, metavar="PATH")


def _add_record_args(parser: argparse.ArgumentParser) -> None:
    settings = load_settings()
    parser.add_argument(
        "--mic",
        default=settings.graba_mic,
        help="Fuente PulseAudio del micrófono.",
    )
    parser.add_argument("--mon", default=settings.graba_mon, help="Monitor PulseAudio de salida.")
    parser.add_argument("--language", default=settings.faster_whisper_language)
    parser.add_argument(
        "--model",
        default=settings.faster_whisper_model,
        dest="model_size_or_path",
    )
    parser.add_argument("--transcribe-only", type=Path, metavar="MP3")
    parser.add_argument("--no-diarize", action="store_true")
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument("--min-mp3-bytes", type=int, default=256, metavar="N")
    parser.add_argument("--skip-groq", action="store_true")
    parser.add_argument("--groq-model", default=settings.groq_model)
    parser.add_argument("--enrich-only", type=Path, metavar="TXT")


def main() -> int:
    args = parse_args()
    command = getattr(args, "command", None)
    db_path = resolve_db_path(args.output_dir, args.db)

    if command == "list":
        return cmd_list(db_path)
    if command == "show":
        return cmd_show(
            db_path,
            args.rank,
            show_transcript=args.transcript,
            show_all=args.all,
        )
    if command == "setup":
        return cmd_setup(install_deps=args.install_deps, yes=args.y)
    if command == "check-deps":
        return cmd_check_deps()

    return run_record_flow(
        output_dir=args.output_dir,
        mic=getattr(args, "mic", ""),
        mon=getattr(args, "mon", ""),
        language=getattr(args, "language", "es"),
        model=getattr(args, "model_size_or_path", "large-v3"),
        transcribe_only=getattr(args, "transcribe_only", None),
        enrich_only=getattr(args, "enrich_only", None),
        no_diarize=getattr(args, "no_diarize", False),
        skip_transcribe=getattr(args, "skip_transcribe", False),
        skip_groq=getattr(args, "skip_groq", False),
        min_mp3_bytes=getattr(args, "min_mp3_bytes", 256),
        db_path=db_path,
        groq_model=getattr(args, "groq_model", DEFAULT_GROQ_MODEL),
    )


def entrypoint() -> None:
    sys.exit(main())
