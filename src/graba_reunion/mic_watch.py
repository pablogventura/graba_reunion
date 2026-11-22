"""Detección de micrófono en uso y decisión de autograbación.

Una app ajena es un stream de captura de PipeWire hacia un micrófono
(no un monitor de salida). El pid publicado por un Flatpak no se usa para
filtrar: solo se ignoran los pid del proceso de grabación que este programa
lanzó y los de sus hijos.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from graba_reunion.config import data_dir

ARM_SECONDS = 3.0
QUIET_SECONDS = 10.0
MANUAL_SILENCE_SECONDS = 600.0
SILENCE_CHECK_SECONDS = 20.0
SILENCE_WINDOW_SECONDS = 25.0
SILENCE_MAX_DB = -50.0
MIN_KEEP_SECONDS = 60.0
RECENT_TRANSCRIPT_SECONDS = 24 * 60 * 60
_MAX_VOLUME_DB = re.compile(r"max_volume:\s*(-inf|-?\d+(?:\.\d+)?)\s*dB")


@dataclass(frozen=True)
class CaptureClient:
    app: str
    pid: int | None
    device: str
    flatpak: bool


SHARED_HOLD_SECONDS = 2.0
SHARED_COOLDOWN_SECONDS = 60.0
# shared_since tras consumir el flanco de este periodo continuo (>=2 apps).
SHARED_LATCHED = -1.0


@dataclass(frozen=True)
class SharedNotifyState:
    """Último aviso de micrófono compartido (apps + instante)."""

    apps: frozenset[str]
    at: float


def unique_capture_apps(clients: list[CaptureClient]) -> list[str]:
    """Apps distintas en orden estable; dedupe por nombre casefold."""
    seen: set[str] = set()
    apps: list[str] = []
    for client in clients:
        key = client.app.casefold()
        if key in seen:
            continue
        seen.add(key)
        apps.append(client.app)
    return apps


def format_shared_apps(apps: list[str]) -> str:
    """Une nombres para el cuerpo de la notificación."""
    if not apps:
        return ""
    if len(apps) == 1:
        return apps[0]
    if len(apps) == 2:
        return f"{apps[0]} y {apps[1]}"
    return ", ".join(apps[:-1]) + f" y {apps[-1]}"


def shared_mic_transition(
    prev_apps: list[str],
    curr_apps: list[str],
    *,
    now: float,
    shared_since: float | None,
    last_notified: SharedNotifyState | None,
    hold_seconds: float = SHARED_HOLD_SECONDS,
    cooldown_seconds: float = SHARED_COOLDOWN_SECONDS,
) -> tuple[list[str] | None, float | None, SharedNotifyState | None]:
    """Flanco a 2+ apps: hold 2 s y cooldown 60 s para el mismo set.

    Devuelve (apps_a_notificar | None, nuevo_shared_since, nuevo_last_notified).
    Un periodo continuo solo dispara una evaluación; al bajar de 2 se reinicia.
    """
    del prev_apps  # el flanco se modela con shared_since / SHARED_LATCHED
    curr_set = frozenset(a.casefold() for a in curr_apps)
    if len(curr_apps) < 2:
        return None, None, last_notified

    if shared_since is None:
        return None, now, last_notified

    if shared_since == SHARED_LATCHED:
        return None, SHARED_LATCHED, last_notified

    if now - shared_since < hold_seconds:
        return None, shared_since, last_notified

    if (
        last_notified is not None
        and last_notified.apps == curr_set
        and now - last_notified.at < cooldown_seconds
    ):
        return None, SHARED_LATCHED, last_notified

    notified = SharedNotifyState(apps=curr_set, at=now)
    return list(curr_apps), SHARED_LATCHED, notified


@dataclass
class WatchState:
    phase: str = "idle"
    arm_since: float | None = None
    quiet_since: float | None = None


def app_label(stream: dict) -> str:
    """Nombre visible. El binario o el app id; no el pid del sandbox."""
    binary = stream.get("application.process.binary")
    if binary:
        return str(binary)
    app_id = stream.get("pipewire.access.portal.app_id") or ""
    if app_id:
        return app_id.rsplit(".", 1)[-1]
    return str(stream.get("application.name") or stream.get("node.name") or "desconocido")


def _props(obj: dict | None) -> dict:
    if not obj:
        return {}
    return obj.get("info", {}).get("props", {})


def _host_pid(stream: dict) -> int | None:
    if stream.get("pipewire.client.access") == "flatpak":
        return None
    raw = stream.get("application.process.id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_capture_clients(
    data: list[dict],
    *,
    ignore_pids: set[int] | None = None,
) -> list[CaptureClient]:
    """Clientes que capturan un micrófono. `ignore_pids` son la grabación propia."""
    ignored = ignore_pids or set()
    nodes = {obj["id"]: obj for obj in data if obj.get("type") == "PipeWire:Interface:Node"}
    ports = {obj["id"]: obj for obj in data if obj.get("type") == "PipeWire:Interface:Port"}
    seen: set[tuple[str, int | None, str]] = set()
    clients: list[CaptureClient] = []
    for obj in data:
        if obj.get("type") != "PipeWire:Interface:Link":
            continue
        info = obj.get("info", {})
        out_props = _props(ports.get(info.get("output-port-id")))
        in_props = _props(ports.get(info.get("input-port-id")))
        source = _props(nodes.get(out_props.get("node.id")))
        stream = _props(nodes.get(in_props.get("node.id")))
        if source.get("media.class") != "Audio/Source":
            continue
        media_class = stream.get("media.class") or ""
        if not media_class.startswith("Stream/Input"):
            continue
        source_name = source.get("node.name") or ""
        if source_name.endswith(".monitor"):
            continue
        flatpak = stream.get("pipewire.client.access") == "flatpak"
        pid = _host_pid(stream)
        if pid is not None and pid in ignored:
            continue
        app = app_label(stream)
        device = source.get("node.description") or source_name or "micrófono"
        key = (app, pid, device)
        if key in seen:
            continue
        seen.add(key)
        clients.append(CaptureClient(app=app, pid=pid, device=device, flatpak=flatpak))
    return clients


def load_capture_clients(*, ignore_pids: set[int] | None = None) -> list[CaptureClient]:
    try:
        raw = subprocess.check_output(["pw-dump"], text=True, stderr=subprocess.DEVNULL)
        data = json.loads(raw)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return parse_capture_clients(data, ignore_pids=ignore_pids)


def descendant_pids(root: int) -> set[int]:
    """Pid hijos, nietos, etc. de `root`, leídos de /proc."""
    children: dict[int, list[int]] = {}
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        marker = stat.rfind(")")
        if marker < 0:
            continue
        fields = stat[marker + 2 :].split()
        if len(fields) < 2:
            continue
        try:
            pid = int(entry.name)
            parent = int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)
    found: set[int] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child in found:
                continue
            found.add(child)
            stack.append(child)
    return found


def tick(
    state: WatchState,
    *,
    foreign_active: bool,
    now: float,
    stop_requested: bool = False,
    paused: bool = False,
    start_requested: bool = False,
    hold: bool = False,
    arm_seconds: float = ARM_SECONDS,
    quiet_seconds: float = QUIET_SECONDS,
) -> str:
    """Avanza el estado. Devuelve 'none', 'start' o 'stop'."""
    if state.phase == "recording" and stop_requested:
        _reset(state)
        return "stop"
    if start_requested and state.phase != "recording":
        state.phase = "recording"
        state.arm_since = None
        state.quiet_since = None
        return "start"
    if state.phase == "recording" and (paused or hold):
        state.quiet_since = None
        return "none"
    if state.phase == "idle":
        if foreign_active:
            state.phase = "arming"
            state.arm_since = now
        return "none"
    if state.phase == "arming":
        if not foreign_active:
            _reset(state)
            return "none"
        if state.arm_since is not None and now - state.arm_since >= arm_seconds:
            state.phase = "recording"
            state.quiet_since = None
            return "start"
        return "none"
    if state.phase == "recording":
        if foreign_active:
            state.quiet_since = None
            return "none"
        if state.quiet_since is None:
            state.quiet_since = now
            return "none"
        if now - state.quiet_since >= quiet_seconds:
            _reset(state)
            return "stop"
        return "none"
    return "none"


def _reset(state: WatchState) -> None:
    state.phase = "idle"
    state.arm_since = None
    state.quiet_since = None


def advance_manual_silence(
    since: float | None,
    now: float,
    *,
    silent: bool | None,
    limit: float = MANUAL_SILENCE_SECONDS,
) -> tuple[float | None, bool]:
    """Actualiza el inicio del silencio. El segundo valor pide cortar la toma."""
    if silent is None:
        return since, False
    if not silent:
        return None, False
    started = now if since is None else since
    return started, now - started >= limit


def file_trailing_is_silent(
    path: Path,
    *,
    window_seconds: float = SILENCE_WINDOW_SECONDS,
    max_db: float = SILENCE_MAX_DB,
) -> bool | None:
    """True si el final del archivo no supera max_db. None si no se pudo medir."""
    if not path.is_file():
        return None
    duration = _media_duration_seconds(path)
    if duration is None or duration <= 0:
        return None
    start = max(0.0, duration - window_seconds)
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{min(window_seconds, duration):.3f}",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _MAX_VOLUME_DB.search(completed.stderr)
    if match is None:
        return None
    token = match.group(1)
    if token == "-inf":
        return True
    return float(token) <= max_db


def _media_duration_seconds(path: Path) -> float | None:
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return float(output.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None


def recording_decision(duration_seconds: float | None, *, minimum: float = MIN_KEEP_SECONDS) -> str:
    """'transcribe' o 'discard'. Sin duración, transcribe para no borrar una reunión larga."""
    if duration_seconds is None:
        return "transcribe"
    if duration_seconds < minimum:
        return "discard"
    return "transcribe"


# Tras un fallo, no reintentar solo al reiniciar el indicador hasta que pase esto.
FAILED_RETRY_SECONDS = 6 * 60 * 60


def pending_dir() -> Path:
    return data_dir() / "pending"


def _pending_marker(mp3: Path) -> Path:
    return pending_dir() / f"{mp3.stem}.path"


def _failed_marker(mp3: Path) -> Path:
    return pending_dir() / f"{mp3.stem}.failed"


def mark_recording_pending(mp3: Path) -> None:
    """Deja en disco que este MP3 todavía no se transcribió."""
    directory = pending_dir()
    directory.mkdir(parents=True, exist_ok=True)
    clear_transcription_failed(mp3)
    marker = _pending_marker(mp3)
    marker.write_text(str(mp3.resolve()) + "\n", encoding="utf-8")
    fd = marker.open("rb+")
    try:
        fd.flush()
        os.fsync(fd.fileno())
    finally:
        fd.close()


def clear_recording_pending(mp3: Path) -> None:
    _pending_marker(mp3).unlink(missing_ok=True)
    clear_transcription_failed(mp3)


def mark_transcription_failed(mp3: Path, reason: str = "") -> None:
    """Marca un fallo reciente para no spamear reintentos/notificaciones."""
    directory = pending_dir()
    directory.mkdir(parents=True, exist_ok=True)
    cleaned = " ".join(reason.strip().split())
    body = f"{int(time.time())}\n{cleaned}\n"
    _failed_marker(mp3).write_text(body, encoding="utf-8")


def clear_transcription_failed(mp3: Path) -> None:
    _failed_marker(mp3).unlink(missing_ok=True)


def recent_transcription_failure(
    mp3: Path,
    *,
    now: float | None = None,
    within_seconds: float = FAILED_RETRY_SECONDS,
) -> str | None:
    """Motivo del último fallo si sigue en la ventana de enfriamiento; si no, None."""
    marker = _failed_marker(mp3)
    if not marker.is_file():
        return None
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or not lines[0].strip().isdigit():
        return None
    stamp = int(lines[0].strip())
    moment = time.time() if now is None else now
    if moment - stamp > within_seconds:
        return None
    reason = " ".join(lines[1:]).strip()
    return reason or "error desconocido"


def recent_transcripts(
    directory: Path,
    *,
    now: float | None = None,
    within_seconds: float = RECENT_TRANSCRIPT_SECONDS,
) -> list[Path]:
    """Transcripciones (.txt) del directorio, de la más nueva a la más vieja."""
    if not directory.is_dir():
        return []
    moment = time.time() if now is None else now
    found: list[tuple[float, Path]] = []
    for path in directory.glob("*.txt"):
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if moment - modified <= within_seconds:
            found.append((modified, path))
    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in found]


def unfinished_recordings(*, skip_recent_failures: bool = False) -> list[Path]:
    """MP3 marcados que siguen sin transcripción (.txt)."""
    directory = pending_dir()
    if not directory.is_dir():
        return []
    pending: list[Path] = []
    for marker in sorted(directory.glob("*.path")):
        text = marker.read_text(encoding="utf-8").strip()
        if not text:
            marker.unlink(missing_ok=True)
            continue
        mp3 = Path(text)
        if mp3.with_suffix(".txt").is_file():
            clear_recording_pending(mp3)
            continue
        if not mp3.is_file():
            clear_recording_pending(mp3)
            continue
        if skip_recent_failures and recent_transcription_failure(mp3) is not None:
            continue
        pending.append(mp3)
    return pending
