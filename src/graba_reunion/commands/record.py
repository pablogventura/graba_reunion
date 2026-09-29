"""Flujo de grabación y transcripción."""
from __future__ import annotations

import sys
from pathlib import Path

from graba_reunion.config import load_settings, settings_with_overrides
from graba_reunion.enrichment import enrich_and_store
from graba_reunion.paths import SessionPaths, session_paths
from graba_reunion.phrases import phrases_path
from graba_reunion.recording import record_until_signal
from graba_reunion.setup_wizard import ensure_configured
from graba_reunion.transcription.faster_whisper import (
    transcribe_to_srt,
    validate_faster_whisper_prereqs,
)
from graba_reunion.transcription.srt import srt_to_plaintext
from graba_reunion.transcription.whisperx import (
    cleanup_whisperx_side_artifacts,
    transcribe_with_diarization,
    validate_diarization_prereqs,
)


def transcribe_and_write_txt(
    mp3: Path,
    srt: Path,
    txt: Path,
    *,
    base: str,
    diarize: bool,
    language: str,
    model: str,
    device: str | None,
    min_mp3_bytes: int,
    skip_groq: bool,
    groq_model: str,
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

    settings = settings_with_overrides(
        load_settings(),
        language=language,
        model=model,
        device=device,
    )

    if diarize:
        print("\nTranscribiendo con diarización…")
        try:
            transcribe_with_diarization(mp3, output_dir=mp3.parent, settings=settings)
        except FileNotFoundError as error:
            print(str(error), file=sys.stderr)
            return 1
        except Exception as error:
            print(f"Error en whisperx: {error}", file=sys.stderr)
            return 1

        if not txt.is_file():
            print(f"No se generó el TXT esperado: {txt}", file=sys.stderr)
            return 1

        cleanup_whisperx_side_artifacts(mp3.parent, base)
        print("Listo:")
        print(mp3)
        print(txt)
        phrase_file = phrases_path(mp3)
        if phrase_file.is_file():
            print(phrase_file)
        if skip_groq:
            return 0
        return enrich_and_store(
            session_base=base,
            mp3=mp3,
            txt=txt,
            groq_model=groq_model,
            language=settings.whisperx_language,
        )

    print("\nTranscribiendo…")
    try:
        transcribe_to_srt(
            mp3,
            srt_out=srt,
            language=settings.whisperx_language,
            model=settings.whisperx_model,
            settings=settings,
        )
    except Exception as error:
        print(f"Error en faster-whisper: {error}", file=sys.stderr)
        return 1

    try:
        plain = srt_to_plaintext(srt)
    except OSError as error:
        print(f"No se pudo leer el SRT: {error}", file=sys.stderr)
        return 1

    txt.write_text(plain, encoding="utf-8")
    print("Listo:")
    print(mp3)
    print(srt)
    print(txt)
    if skip_groq:
        return 0
    return enrich_and_store(
        session_base=base,
        mp3=mp3,
        txt=txt,
        groq_model=groq_model,
        language=settings.whisperx_language,
    )


def run_record_flow(
    *,
    output_dir: Path,
    mic: str,
    mon: str,
    language: str,
    model: str,
    device: str | None = None,
    transcribe_only: Path | None,
    enrich_only: Path | None,
    no_diarize: bool,
    skip_transcribe: bool,
    skip_groq: bool,
    min_mp3_bytes: int,
    groq_model: str,
) -> int:
    flows: list[str] = []
    if enrich_only is not None:
        if not skip_groq:
            flows.append("groq")
    elif transcribe_only is not None:
        flows.append("fast" if no_diarize else "diarize")
        if not skip_groq:
            flows.append("groq")
    else:
        flows.append("record")
        if not skip_transcribe:
            flows.append("fast" if no_diarize else "diarize")
            if not skip_groq:
                flows.append("groq")

    configured = ensure_configured(flows)
    if configured != 0:
        return configured

    settings = load_settings()

    if enrich_only is not None:
        txt = enrich_only.expanduser().resolve()
        if not txt.is_file():
            print(f"No existe el TXT: {txt}", file=sys.stderr)
            return 1
        mp3 = txt.with_suffix(".mp3")
        if not mp3.is_file():
            mp3 = txt
        return enrich_and_store(
            session_base=txt.stem,
            mp3=mp3,
        txt=txt,
        groq_model=groq_model,
        language=language or settings.whisperx_language,
    )

    if transcribe_only is not None:
        mp3 = transcribe_only.expanduser().resolve()
        if not mp3.is_file():
            print(f"No existe el MP3: {mp3}", file=sys.stderr)
            return 1
        if no_diarize:
            error = validate_faster_whisper_prereqs()
        else:
            error = validate_diarization_prereqs()
        if error:
            print(error, file=sys.stderr)
            return 1
        return transcribe_and_write_txt(
            mp3,
            mp3.with_suffix(".srt"),
            mp3.with_suffix(".txt"),
            base=mp3.stem,
            diarize=not no_diarize,
            language=language,
            model=model,
            device=device,
            min_mp3_bytes=min_mp3_bytes,
            skip_groq=skip_groq,
            groq_model=groq_model,
        )

    paths: SessionPaths = session_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not skip_transcribe:
        if no_diarize:
            error = validate_faster_whisper_prereqs()
        else:
            error = validate_diarization_prereqs()
        if error:
            print(error, file=sys.stderr)
            return 1

    active_mic = mic or settings.graba_mic
    active_mon = mon or settings.graba_mon
    if not active_mic or not active_mon:
        print("GRABA_MIC y GRABA_MON son obligatorios.", file=sys.stderr)
        return 1

    record_code = record_until_signal(
        active_mic,
        active_mon,
        paths.mp3,
        backend=settings.audio_backend,
    )
    if skip_transcribe:
        print("\nGrabación finalizada (sin transcripción).")
        print(paths.mp3)
        return record_code

    tx_code = transcribe_and_write_txt(
        paths.mp3,
        paths.srt,
        paths.txt,
        base=paths.base,
        diarize=not no_diarize,
        language=language,
        model=model,
        device=device,
        min_mp3_bytes=min_mp3_bytes,
        skip_groq=skip_groq,
        groq_model=groq_model,
    )
    if record_code != 0:
        return record_code
    return tx_code
