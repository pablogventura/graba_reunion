"""Arma clips y grupos de voz a partir de MP3 ya grabados."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from graba_reunion.voices import (
    CLIP_SECONDS,
    MATCH_SIMILARITY,
    SpeakerTrack,
    VoiceCluster,
    cluster_tracks,
    playback_window,
    representative_track,
    voices_dir,
)

CACHE_VERSION = 1


def prepare_review(mp3_paths: list[Path], *, device: str, token: str) -> list[VoiceCluster]:
    """Diariza cada MP3 (con caché), agrupa voces parecidas y deja un clip por grupo."""
    pending = [mp3 for mp3 in mp3_paths if _read_cache(mp3) is None]
    pipeline = _load_pipeline(token=token, device=device) if pending else None
    tracks: list[SpeakerTrack] = []
    total = len(mp3_paths)
    for index, mp3 in enumerate(mp3_paths, start=1):
        print(f"Voces {index}/{total}: {mp3.name}", flush=True)
        try:
            tracks.extend(_tracks_for_file(pipeline, mp3))
        except Exception as error:
            print(f"  no se pudo diarizar: {error}", flush=True)
    clusters = cluster_tracks(tracks, threshold=MATCH_SIMILARITY)
    clips_dir = voices_dir() / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    with_clips: list[VoiceCluster] = []
    for cluster in clusters:
        track = representative_track(cluster)
        clip_start, clip_end = playback_window(track.clip_start, track.clip_end)
        clip_path = clips_dir / f"{cluster.cluster_id:02d}.wav"
        try:
            _extract_clip(Path(track.mp3_path), clip_start, clip_end, clip_path)
            saved_clip: str | None = str(clip_path)
        except Exception as error:
            print(f"  sin clip {cluster.cluster_id}: {error}", flush=True)
            saved_clip = None
        with_clips.append(
            VoiceCluster(
                cluster_id=cluster.cluster_id,
                tracks=cluster.tracks,
                clip_path=saved_clip,
            )
        )
    review_path = voices_dir() / "review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(_review_payload(with_clips)), encoding="utf-8")
    return with_clips


def load_review(path: Path | None = None) -> list[VoiceCluster]:
    review_path = path or (voices_dir() / "review.json")
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    clusters: list[VoiceCluster] = []
    for item in payload.get("clusters") or []:
        tracks = tuple(
            SpeakerTrack(
                source_name=str(track["source_name"]),
                mp3_path=str(track["mp3_path"]),
                label=str(track["label"]),
                embedding=tuple(float(value) for value in track["embedding"]),
                speech_seconds=float(track["speech_seconds"]),
                clip_start=float(track["clip_start"]),
                clip_end=float(track["clip_end"]),
            )
            for track in item.get("tracks") or []
        )
        if not tracks:
            continue
        clusters.append(
            VoiceCluster(
                cluster_id=int(item["cluster_id"]),
                tracks=tracks,
                clip_path=item.get("clip_path"),
            )
        )
    return clusters


def _review_payload(clusters: list[VoiceCluster]) -> dict:
    return {
        "version": CACHE_VERSION,
        "clusters": [
            {
                "cluster_id": cluster.cluster_id,
                "clip_path": cluster.clip_path,
                "tracks": [
                    {
                        "source_name": track.source_name,
                        "mp3_path": track.mp3_path,
                        "label": track.label,
                        "embedding": list(track.embedding),
                        "speech_seconds": track.speech_seconds,
                        "clip_start": track.clip_start,
                        "clip_end": track.clip_end,
                    }
                    for track in cluster.tracks
                ],
            }
            for cluster in clusters
        ],
    }


def _tracks_for_file(pipeline: object | None, mp3: Path) -> list[SpeakerTrack]:
    cached = _read_cache(mp3)
    if cached is not None:
        print(f"  caché {len(cached)} voces", flush=True)
        return cached
    if pipeline is None:
        raise RuntimeError(f"No hay diarización en caché para {mp3.name}")
    output = pipeline(_waveform(mp3))
    tracks = _tracks_from_output(mp3, output)
    _write_cache(mp3, tracks)
    print(f"  {len(tracks)} voces", flush=True)
    return tracks


def _tracks_from_output(mp3: Path, output: object) -> list[SpeakerTrack]:
    annotation = getattr(output, "speaker_diarization", None)
    matrix = getattr(output, "speaker_embeddings", None)
    if annotation is None or matrix is None:
        raise RuntimeError(f"pyannote no devolvió embeddings para {mp3.name}")
    exclusive = getattr(output, "exclusive_speaker_diarization", None) or annotation
    labels = list(annotation.labels())
    turns: dict[str, list[tuple[float, float]]] = {label: [] for label in labels}
    speech: dict[str, float] = {label: 0.0 for label in labels}
    for segment, _, speaker in exclusive.itertracks(yield_label=True):
        if speaker not in turns:
            continue
        start = float(segment.start)
        end = float(segment.end)
        turns[speaker].append((start, end))
        speech[speaker] += max(0.0, end - start)
    tracks: list[SpeakerTrack] = []
    for index, label in enumerate(labels):
        if index >= len(matrix) or not turns[label]:
            continue
        clip_start, clip_end = _best_window(turns[label])
        vector = tuple(float(value) for value in matrix[index])
        tracks.append(
            SpeakerTrack(
                source_name=mp3.name,
                mp3_path=str(mp3.resolve()),
                label=str(label),
                embedding=vector,
                speech_seconds=speech[label],
                clip_start=clip_start,
                clip_end=clip_end,
            )
        )
    return tracks


def _best_window(segments: list[tuple[float, float]]) -> tuple[float, float]:
    long_enough = [segment for segment in segments if segment[1] - segment[0] >= 2.0]
    start, end = max(long_enough or segments, key=lambda segment: segment[1] - segment[0])
    if end - start > CLIP_SECONDS:
        end = start + CLIP_SECONDS
    return start, end


def _cache_path(mp3: Path) -> Path:
    return voices_dir() / "cache" / f"{mp3.stem}.json"


def _signature(mp3: Path) -> dict[str, int]:
    stat = mp3.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _read_cache(mp3: Path) -> list[SpeakerTrack] | None:
    path = _cache_path(mp3)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("signature") != _signature(mp3):
        return None
    return _tracks_from_cache(mp3, payload.get("tracks") or [])


def _tracks_from_cache(mp3: Path, raw_tracks: list[dict]) -> list[SpeakerTrack]:
    return [
        SpeakerTrack(
            source_name=mp3.name,
            mp3_path=str(mp3.resolve()),
            label=str(item["label"]),
            embedding=tuple(float(value) for value in item["embedding"]),
            speech_seconds=float(item["speech_seconds"]),
            clip_start=float(item["clip_start"]),
            clip_end=float(item["clip_end"]),
        )
        for item in raw_tracks
    ]


def _write_cache(mp3: Path, tracks: list[SpeakerTrack]) -> None:
    path = _cache_path(mp3)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "signature": _signature(mp3),
        "tracks": [
            {
                "label": track.label,
                "embedding": list(track.embedding),
                "speech_seconds": track.speech_seconds,
                "clip_start": track.clip_start,
                "clip_end": track.clip_end,
            }
            for track in tracks
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _waveform(mp3: Path) -> dict:
    """Audio en memoria. pyannote no puede leer el MP3: torchcodec no está instalado."""
    import numpy as np
    import torch

    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(mp3),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "pipe:1",
        ],
    )
    samples = np.frombuffer(raw, dtype="<f4").copy()
    return {"waveform": torch.from_numpy(samples).unsqueeze(0), "sample_rate": 16000}


def _extract_clip(mp3: Path, start: float, end: float, dest: Path) -> None:
    duration = max(0.3, end - start)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(mp3),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _load_pipeline(token: str, device: str) -> object:
    import torch
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1",
        token=token,
    )
    if pipeline is None:
        raise RuntimeError("No se pudo cargar pyannote/speaker-diarization-community-1")
    pipeline.to(torch.device(device))
    return pipeline
