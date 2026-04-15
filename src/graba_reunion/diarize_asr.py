"""Transcripción con etiquetas de hablante (pyannote + faster-whisper)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def _mono_16k_wav(src: Path) -> Path:
    """Audio mono 16 kHz como espera el pipeline de pyannote."""
    fd, path_str = tempfile.mkstemp(suffix=".wav", prefix="graba_reunion_")
    os.close(fd)
    out = Path(path_str)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        out.unlink(missing_ok=True)
        err = (e.stderr or e.stdout or "").strip()
        raise SystemExit(f"ffmpeg no pudo convertir el audio para diarización.{os.linesep}{err}") from e
    return out


def _check_extra_imports() -> None:
    missing: list[str] = []
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        missing.append("faster-whisper")
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        missing.append("pyannote.audio")
    if missing:
        pkgs = ", ".join(missing)
        raise SystemExit(
            "Faltan dependencias para la diarización/transcripción: "
            f"{pkgs}. Reinstalá el paquete (p. ej. pipx install graba-reunion o pip install -e .)."
        )


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _speaker_for_interval(start: float, end: float, diarization) -> str:
    best = "SPEAKER_UNKNOWN"
    best_ov = 0.0
    if end <= start:
        return best
    for turn, _track, label in diarization.itertracks(yield_label=True):
        ov_start = max(start, turn.start)
        ov_end = min(end, turn.end)
        ov = max(0.0, ov_end - ov_start)
        if ov > best_ov:
            best_ov = ov
            best = str(label)
    return best


def _write_srt(blocks: list[tuple[float, float, str, str]], path: Path) -> None:
    lines: list[str] = []
    for i, (start, end, speaker, text) in enumerate(blocks, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(f"[{speaker}] {text}")
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_txt_merged(blocks: list[tuple[float, float, str, str]], path: Path) -> None:
    """Une líneas consecutivas del mismo hablante en un solo párrafo."""
    out_lines: list[str] = []
    cur_spk: str | None = None
    buf: list[str] = []
    for _s, _e, speaker, text in blocks:
        if not text:
            continue
        if speaker == cur_spk:
            buf.append(text)
        else:
            if cur_spk is not None and buf:
                out_lines.append(f"[{cur_spk}] " + " ".join(buf))
            cur_spk, buf = speaker, [text]
    if cur_spk is not None and buf:
        out_lines.append(f"[{cur_spk}] " + " ".join(buf))
    path.write_text("\n".join(out_lines).strip() + "\n", encoding="utf-8")


def transcribe_with_diarization(
    audio_path: str | Path,
    language: str,
    model_size: str,
    srt_path: str | Path,
    txt_path: str | Path,
    hf_token: str | None,
    device: str | None = None,
    compute_type: str | None = None,
) -> None:
    _check_extra_imports()

    import torch
    from faster_whisper import WhisperModel
    from pyannote.audio import Pipeline

    audio_path = Path(audio_path)
    srt_path = Path(srt_path)
    txt_path = Path(txt_path)

    if not hf_token:
        raise SystemExit(
            "Hace falta un token de Hugging Face para los modelos de pyannote. "
            "Creá uno en https://huggingface.co/settings/tokens y aceptá las condiciones de "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 y "
            "https://huggingface.co/pyannote/segmentation-3.0 — "
            "luego exportá HF_TOKEN=... o pasá --hf-token."
        )

    print("Cargando pipeline de diarización...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("Pediste --device cuda pero no hay GPU CUDA disponible.")

    use_cuda = device == "cuda" or (device is None and torch.cuda.is_available())
    if use_cuda:
        pipeline.to(torch.device("cuda"))

    wav_tmp: Path | None = None
    blocks: list[tuple[float, float, str, str]] = []
    try:
        print("Preparando audio (mono 16 kHz) para diarización y ASR...")
        wav_tmp = _mono_16k_wav(audio_path)

        print("Ejecutando diarización (puede tardar)...")
        diarization = pipeline(str(wav_tmp))

        dev = device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        if compute_type is not None:
            ctype = compute_type
        else:
            ctype = "float16" if dev == "cuda" else "int8"

        print(f"Transcribiendo con faster-whisper (dispositivo={dev}, compute_type={ctype})...")
        model = WhisperModel(model_size, device=dev, compute_type=ctype)
        segments_gen, _info = model.transcribe(str(wav_tmp), language=language)

        blocks = _segments_to_blocks(segments_gen, diarization)
    finally:
        if wav_tmp is not None:
            wav_tmp.unlink(missing_ok=True)

    if not blocks:
        raise SystemExit("No se obtuvo ningún segmento de transcripción.")

    _write_srt(blocks, srt_path)
    _write_txt_merged(blocks, txt_path)
    print(f"Escrito: {srt_path}")
    print(f"Escrito: {txt_path}")


def _segments_to_blocks(
    segments_gen,
    diarization,
) -> list[tuple[float, float, str, str]]:
    blocks: list[tuple[float, float, str, str]] = []
    for seg in segments_gen:
        text = seg.text.strip()
        if not text:
            continue
        spk = _speaker_for_interval(seg.start, seg.end, diarization)
        blocks.append((seg.start, seg.end, spk, text))
    return blocks
