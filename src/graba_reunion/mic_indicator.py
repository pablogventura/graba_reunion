"""Indicador de GNOME que graba cuando otra app usa el micrófono."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Notify", "0.7")

from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import GLib, Gtk, Notify, Pango  # noqa: E402

from graba_reunion.config import data_dir  # noqa: E402
from graba_reunion.mic_watch import (  # noqa: E402
    MANUAL_SILENCE_SECONDS,
    SILENCE_CHECK_SECONDS,
    CaptureClient,
    SharedNotifyState,
    WatchState,
    advance_manual_silence,
    clear_recording_pending,
    descendant_pids,
    file_trailing_is_silent,
    format_shared_apps,
    load_capture_clients,
    mark_recording_pending,
    mark_transcription_failed,
    recent_transcripts,
    recording_decision,
    shared_mic_transition,
    tick,
    unique_capture_apps,
    unfinished_recordings,
)
from graba_reunion.paths import default_output_dir  # noqa: E402
from graba_reunion.phrases import start_for_clock  # noqa: E402
from graba_reunion.search import search_command  # noqa: E402
from graba_reunion.timing import add_pause, probe_duration_seconds  # noqa: E402
from graba_reunion.viewer import view_command  # noqa: E402

POLL_SECONDS = 1
ICON_IDLE = "microphone-disabled-symbolic"
ICON_ACTIVE = "microphone-sensitivity-high-symbolic"
ICON_SHARED = "dialog-warning-symbolic"
_SECRET_RE = re.compile(r"(hf_[A-Za-z0-9]+|sk-[A-Za-z0-9]+)")


def graba_reunion_bin() -> str:
    """El indicador puede correr con el Python del sistema; la CLI vive en pipx."""
    candidates = [
        Path.home() / ".local/share/pipx/venvs/graba-reunion/bin/graba-reunion",
        Path.home() / ".local/bin/graba-reunion",
        Path(sys.executable).parent / "graba-reunion",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("graba-reunion")
    if found:
        return found
    raise FileNotFoundError("No se encontró el comando graba-reunion")


def media_duration_seconds(path: Path) -> float | None:
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
        )
        return float(output.strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def log_line(message: str) -> None:
    path = data_dir() / "mic-indicator.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {_redact_secrets(message)}\n")
    except OSError:
        return


def _redact_secrets(text: str) -> str:
    return _SECRET_RE.sub("***", text)


def _read_transcribe_error(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = _redact_secrets(raw)
    lowered = text.casefold()
    if "out of memory" in lowered or "cuda failed" in lowered:
        return "GPU sin memoria (CUDA OOM)"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Error") or "Error" in line or line.startswith("RuntimeError"):
            return line[:180]
    if not lines:
        return ""
    return lines[-1][:180]


def _append_search_column(
    tree: Gtk.TreeView,
    title: str,
    index: int,
    *,
    expand: bool,
    wrap: bool = False,
) -> None:
    cell = Gtk.CellRendererText()
    cell.set_property("ypad", 4)
    if wrap:
        cell.set_property("wrap-mode", Pango.WrapMode.WORD_CHAR)
        cell.set_property("wrap-width", 460)
    column = Gtk.TreeViewColumn(title, cell, text=index)
    column.set_resizable(True)
    column.set_expand(expand)
    if not expand:
        column.set_min_width(90)
    tree.append_column(column)


def meeting_stamp(path: Path) -> str:
    """Fecha legible a partir de reunion_AAAA-MM-DD_HH-MM-SS."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})", path.stem)
    if match is None:
        return path.stem
    return f"{match.group(1)} {match.group(2)}:{match.group(3)}"


def open_viewer(path: Path | None = None, *, clock: str = "") -> None:
    """Abre el visor de grabaciones. Con path, en esa reunión; con clock, en esa frase."""
    meeting_id = path.stem if path is not None else ""
    start = start_for_clock(path, clock) if path is not None and clock else None
    try:
        command = view_command(
            graba_reunion_bin(),
            meeting_id=meeting_id,
            start=start,
            output_dir=default_output_dir(),
        )
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        log_line(f"no se pudo abrir el visor: {error}")


_live_notes: list[Notify.Notification] = []


def _drop_note(note: Notify.Notification, *_args: object) -> None:
    if note in _live_notes:
        _live_notes.remove(note)


def _on_notify_open(note: Notify.Notification, _action: str, path_text: str) -> None:
    open_viewer(Path(path_text))
    note.close()


def gnome_notify(
    summary: str,
    body: str,
    *,
    open_path: Path | None = None,
    icon: str = "audio-x-generic",
    urgency: int | None = None,
) -> None:
    """Aviso en el escritorio. Si hay open_path, el clic abre el visor en esa reunión."""
    try:
        if not Notify.is_initted():
            Notify.init("graba-reunion")
        note = Notify.Notification.new(summary, body, icon)
        if urgency is not None:
            note.set_urgency(urgency)
        # Sin referencia viva PyGObject puede recolectar el aviso antes de mostrarlo.
        note.connect("closed", _drop_note)
        _live_notes.append(note)
        if open_path is not None:
            note.add_action("default", "Abrir", _on_notify_open, str(open_path))
        note.show()
    except Exception as error:
        log_line(f"no se pudo notificar: {error}")


class MicIndicator:
    def __init__(self) -> None:
        self.indicator = AppIndicator.Indicator.new(
            "graba-reunion-mic",
            ICON_IDLE,
            AppIndicator.IndicatorCategory.HARDWARE,
        )
        self.indicator.set_attention_icon_full(ICON_ACTIVE, "Grabando")
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.menu = Gtk.Menu()
        self.indicator.set_menu(self.menu)
        self.state = WatchState()
        self.clients: list[CaptureClient] = []
        self._prev_shared_apps: list[str] = []
        self._shared_since: float | None = None
        self._shared_last_notified: SharedNotifyState | None = None
        self.record_proc: subprocess.Popen[str] | None = None
        self.transcribe_proc: subprocess.Popen[str] | None = None
        self.transcribe_mp3: Path | None = None
        self.transcribe_err_path: Path | None = None
        self.transcribe_queue: list[Path] = []
        self.mp3: Path | None = None
        self.started_at: float | None = None
        self.stop_requested = False
        self.restart_after_stop = False
        self.quitting = False
        self.paused = False
        self.cancel_requested = False
        self.paused_total = 0.0
        self.pause_started: float | None = None
        self._call_ended_notified = False
        self.manual = False
        self._silence_since: float | None = None
        self._silence_checked_at = 0.0
        self._silence_probe_on = False
        self._cancel_dialog: Gtk.MessageDialog | None = None
        self._pause_wall: datetime | None = None
        self._pause_audio_at: float | None = None
        self._search_dialog: Gtk.Dialog | None = None
        self._status_key: tuple[object, ...] | None = None
        log_line("indicador iniciado")
        self._resume_unfinished()
        self.refresh()
        GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)

    def refresh(self) -> bool:
        self._reap_transcribe()
        self._reap_record()
        self._pump_transcribe_queue()
        had_clients = bool(self.clients)
        ignore = self._own_pids()
        self.clients = load_capture_clients(ignore_pids=ignore)
        self._notify_call_ended_while_paused(had_clients)
        if self.manual and self.clients:
            self.manual = False
            self._silence_since = None
        now = GLib.get_monotonic_time() / 1_000_000
        self._poll_shared_mic(now)
        self._poll_manual_silence(now)
        action = tick(
            self.state,
            foreign_active=bool(self.clients),
            now=now,
            stop_requested=self.stop_requested,
            paused=self.paused,
            hold=self.manual,
        )
        self.stop_requested = False
        if action == "start":
            self._start_recording()
        elif action == "stop":
            self._stop_recording()
        self._paint()
        if self.quitting and not self._record_alive():
            Gtk.main_quit()
            return False
        return True

    def _own_pids(self) -> set[int]:
        proc = self.record_proc
        if proc is None or proc.poll() is not None:
            return set()
        return {proc.pid} | descendant_pids(proc.pid)

    def _record_alive(self) -> bool:
        return self.record_proc is not None and self.record_proc.poll() is None

    def _poll_manual_silence(self, now: float) -> None:
        if not self.manual or self.paused or not self._record_alive() or self.mp3 is None:
            return
        if self._silence_since is not None and now - self._silence_since >= MANUAL_SILENCE_SECONDS:
            log_line("corte por 10 minutos de silencio")
            self.stop_requested = True
            return
        if self._silence_probe_on or now - self._silence_checked_at < SILENCE_CHECK_SECONDS:
            return
        self._silence_checked_at = now
        self._silence_probe_on = True
        path = self.mp3

        def worker() -> None:
            silent = file_trailing_is_silent(path)
            GLib.idle_add(self._apply_manual_silence, silent)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_manual_silence(self, silent: bool | None) -> bool:
        self._silence_probe_on = False
        if not self.manual or self.paused or not self._record_alive():
            return False
        now = GLib.get_monotonic_time() / 1_000_000
        self._silence_since, should_stop = advance_manual_silence(
            self._silence_since,
            now,
            silent=silent,
        )
        if should_stop:
            log_line("corte por 10 minutos de silencio")
            self.stop_requested = True
        return False

    def _start_recording(self) -> None:
        if self._record_alive():
            self.state.phase = "arming"
            self.state.arm_since = GLib.get_monotonic_time() / 1_000_000
            return
        try:
            command = [graba_reunion_bin(), "--skip-transcribe"]
        except FileNotFoundError as error:
            log_line(f"error: {error}")
            self.manual = False
            self.state.phase = "idle"
            self.state.arm_since = None
            self.state.quiet_since = None
            return
        self.mp3 = None
        self.started_at = GLib.get_monotonic_time() / 1_000_000
        self.paused = False
        self.cancel_requested = False
        self.paused_total = 0.0
        self.pause_started = None
        self._call_ended_notified = False
        self._silence_since = None
        self._silence_checked_at = 0.0
        self.record_proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log_line(f"grabación iniciada pid={self.record_proc.pid}")
        thread = threading.Thread(
            target=self._read_record_output,
            args=(self.record_proc,),
            daemon=True,
        )
        thread.start()

    def _read_record_output(self, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            text = line.strip()
            if not text:
                continue
            log_line(f"grabación: {text}")
            if text.startswith("Grabando en "):
                self.mp3 = Path(text.removeprefix("Grabando en ").strip())
                mark_recording_pending(self.mp3)

    def _signal_tree(self, sig: int) -> None:
        proc = self.record_proc
        if proc is None or proc.poll() is not None:
            return
        children = descendant_pids(proc.pid)
        if sig == signal.SIGSTOP:
            targets = list(children) + [proc.pid]
        else:
            targets = [proc.pid, *children]
        for pid in targets:
            try:
                os.kill(pid, sig)
            except OSError:
                continue

    def _close_pause_interval(self) -> None:
        if self.pause_started is None:
            return
        now = GLib.get_monotonic_time() / 1_000_000
        self.paused_total += now - self.pause_started
        self.pause_started = None

    def _stop_recording(self) -> None:
        proc = self.record_proc
        if proc is None or proc.poll() is not None:
            return
        if self.paused:
            self._save_pause()
            self._signal_tree(signal.SIGCONT)
            self._close_pause_interval()
            self.paused = False
        log_line(f"corte pid={proc.pid}")
        proc.send_signal(signal.SIGTERM)

    def _notify_call_ended_while_paused(self, had_clients: bool) -> None:
        if not self.paused or not self._record_alive():
            return
        if had_clients and not self.clients and not self._call_ended_notified:
            self._call_ended_notified = True
            gnome_notify(
                "La llamada terminó",
                "La grabación sigue en pausa. Reanúdala o detenéla desde el icono.",
            )

    def _reap_record(self) -> None:
        proc = self.record_proc
        if proc is None or proc.poll() is None:
            return
        restart = self.restart_after_stop
        self.restart_after_stop = False
        try:
            self._finish_record()
        finally:
            if restart:
                self._start_followup()

    def _finish_record(self) -> None:
        mp3 = self.mp3
        started = self.started_at
        cancelled = self.cancel_requested
        paused_total = self.paused_total
        self.record_proc = None
        self.started_at = None
        self.mp3 = None
        self.paused = False
        self.pause_started = None
        self.paused_total = 0.0
        self.cancel_requested = False
        self._call_ended_notified = False
        self.manual = False
        self._silence_since = None
        if cancelled:
            self._discard_cancelled(mp3)
            return
        if mp3 is None or not mp3.is_file():
            log_line("grabación terminada sin MP3")
            return
        duration = media_duration_seconds(mp3)
        if duration is None and started is not None:
            elapsed = (GLib.get_monotonic_time() / 1_000_000) - started - paused_total
            duration = max(0.0, elapsed)
        decision = recording_decision(duration)
        if decision == "discard":
            self._discard_short(mp3, duration)
            return
        log_line(f"transcribiendo {mp3}")
        self._enqueue_transcribe(mp3)

    def _discard_cancelled(self, mp3: Path | None) -> None:
        name = mp3.name if mp3 is not None else "la grabación"
        if mp3 is not None:
            try:
                mp3.unlink(missing_ok=True)
            except OSError as error:
                log_line(f"no se pudo borrar {mp3}: {error}")
            clear_recording_pending(mp3)
        log_line(f"cancelada {name}")
        gnome_notify("Grabación cancelada", f"Se borró {name}.")

    def _discard_short(self, mp3: Path, duration: float | None) -> None:
        try:
            mp3.unlink(missing_ok=True)
        except OSError as error:
            log_line(f"no se pudo borrar {mp3}: {error}")
            return
        clear_recording_pending(mp3)
        shown = f"{duration:.0f} s" if duration is not None else "poco"
        log_line(f"descartada {mp3.name} ({shown})")
        gnome_notify(
            "Grabación descartada",
            f"{mp3.name} duró {shown}. No se transcribe.",
        )

    def _resume_unfinished(self) -> None:
        pending = [
            path
            for path in unfinished_recordings(skip_recent_failures=True)
            if path != self.mp3 and path not in self.transcribe_queue
        ]
        if not pending:
            return
        names = "\n".join(path.name for path in pending)
        log_line(f"retomando sin transcripción: {names.replace(chr(10), ', ')}")
        gnome_notify(
            "Grabación sin transcribir",
            "Quedó audio de una sesión anterior. Lo transcribo ahora:\n" + names,
        )
        for path in pending:
            self._enqueue_transcribe(path)

    def _enqueue_transcribe(self, mp3: Path) -> None:
        if mp3 == self.transcribe_mp3 or mp3 in self.transcribe_queue:
            return
        self.transcribe_queue.append(mp3)

    def _pump_transcribe_queue(self) -> None:
        while self.transcribe_queue:
            if self.transcribe_proc is not None and self.transcribe_proc.poll() is None:
                return
            mp3 = self.transcribe_queue.pop(0)
            self._begin_transcribe(mp3)
            if self.transcribe_proc is not None and self.transcribe_proc.poll() is None:
                return

    def _begin_transcribe(self, mp3: Path) -> None:
        if mp3.with_suffix(".txt").is_file():
            clear_recording_pending(mp3)
            return
        if not mp3.is_file():
            clear_recording_pending(mp3)
            return
        duration = media_duration_seconds(mp3)
        if recording_decision(duration) == "discard":
            self._discard_short(mp3, duration)
            return
        try:
            command = [graba_reunion_bin(), "--transcribe-only", str(mp3)]
        except FileNotFoundError as error:
            log_line(f"error: {error}")
            gnome_notify("No se pudo transcribir", str(error))
            return
        err_path = data_dir() / "transcribe-stderr.log"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        err_handle = err_path.open("wb")
        self.transcribe_mp3 = mp3
        self.transcribe_err_path = err_path
        self.transcribe_proc = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=err_handle,
        )
        err_handle.close()
        log_line(f"transcribiendo {mp3}")

    def _reap_transcribe(self) -> None:
        proc = self.transcribe_proc
        if proc is None or proc.poll() is None:
            return
        code = proc.returncode
        mp3 = self.transcribe_mp3
        err_path = getattr(self, "transcribe_err_path", None)
        self.transcribe_proc = None
        self.transcribe_mp3 = None
        self.transcribe_err_path = None
        detail = _read_transcribe_error(err_path)
        log_line(f"transcripción terminada code={code}")
        if detail:
            log_line(f"transcripción error: {detail}")
        if mp3 is not None and code == 0 and mp3.with_suffix(".txt").is_file():
            clear_recording_pending(mp3)
            txt = mp3.with_suffix(".txt")
            gnome_notify("Transcripción lista", txt.name, open_path=txt)
            return
        name = mp3.name if mp3 is not None else "la grabación"
        reason = detail or "revisá el log del indicador"
        if mp3 is not None:
            mark_transcription_failed(mp3, reason)
        gnome_notify(
            "No se pudo transcribir",
            f"{name}: {reason}. No reintento solo por un rato (suele ser falta de VRAM).",
        )

    def _poll_shared_mic(self, now: float) -> None:
        curr_apps = unique_capture_apps(self.clients)
        notify_apps, self._shared_since, self._shared_last_notified = shared_mic_transition(
            self._prev_shared_apps,
            curr_apps,
            now=now,
            shared_since=self._shared_since,
            last_notified=self._shared_last_notified,
        )
        self._prev_shared_apps = curr_apps
        if not notify_apps:
            return
        names = format_shared_apps(notify_apps)
        gnome_notify(
            "Micrófono compartido",
            f"{names} usan el micrófono a la vez. "
            "Cuidado si ibas a mandar un audio en otra app.",
            icon="dialog-warning",
            urgency=Notify.Urgency.CRITICAL,
        )
        log_line(f"micrófono compartido: {names}")

    def _shared_mic_active(self) -> bool:
        return len(unique_capture_apps(self.clients)) >= 2

    def _status_title(self) -> str:
        shared = self._shared_mic_active()
        if self._record_alive() and self.paused:
            return "Pausa - mic compartido" if shared else "Grabación en pausa"
        if self._record_alive():
            return "Grabando - mic compartido" if shared else "Grabando reunión"
        if self.transcribe_proc is not None and self.transcribe_proc.poll() is None:
            return "Transcribiendo"
        if shared:
            return "Micrófono compartido"
        if self.state.phase == "arming" or self.clients:
            return "Micrófono en uso"
        return "Micrófono libre"

    def _paint(self) -> None:
        title = self._status_title()
        recording = self._record_alive()
        shared = self._shared_mic_active()
        recent = recent_transcripts(default_output_dir())
        key = (
            title,
            self.paused,
            recording,
            shared,
            tuple((item.app, item.pid, item.device) for item in self.clients),
            tuple(path.name for path in recent),
        )
        if recording:
            self.indicator.set_attention_icon_full(ICON_ACTIVE, "Grabando")
            self.indicator.set_status(AppIndicator.IndicatorStatus.ATTENTION)
        elif shared:
            self.indicator.set_attention_icon_full(ICON_SHARED, "Micrófono compartido")
            self.indicator.set_status(AppIndicator.IndicatorStatus.ATTENTION)
        else:
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.indicator.set_icon_full(ICON_IDLE, title)
        self.indicator.set_title(title)
        if key == self._status_key:
            return
        self._status_key = key
        self._rebuild_menu(title, recent)

    def _rebuild_menu(self, title: str, recent: list[Path]) -> None:
        for child in self.menu.get_children():
            self.menu.remove(child)
        header = Gtk.MenuItem(label=title)
        header.set_sensitive(False)
        self.menu.append(header)
        if self.clients:
            for client in self.clients:
                label = f"{client.app} - {client.device}"
                item = Gtk.MenuItem(label=label)
                item.set_sensitive(False)
                self.menu.append(item)
        else:
            idle = Gtk.MenuItem(label="Nadie está capturando el micrófono")
            idle.set_sensitive(False)
            self.menu.append(idle)
        self.menu.append(Gtk.SeparatorMenuItem())
        heading = Gtk.MenuItem(label="Últimas 24 h")
        heading.set_sensitive(False)
        self.menu.append(heading)
        if recent:
            for path in recent:
                item = Gtk.MenuItem(label=path.name)
                item.connect("activate", self._on_open_transcript, str(path))
                self.menu.append(item)
        else:
            empty = Gtk.MenuItem(label="Sin transcripciones")
            empty.set_sensitive(False)
            self.menu.append(empty)
        self.menu.append(Gtk.SeparatorMenuItem())
        search_item = Gtk.MenuItem(label="Buscar")
        search_item.connect("activate", self._on_search)
        self.menu.append(search_item)
        view_item = Gtk.MenuItem(label="Ver conversaciones")
        view_item.connect("activate", self._on_view)
        self.menu.append(view_item)
        if self._record_alive() and self.paused:
            resume_item = Gtk.MenuItem(label="Reanudar")
            resume_item.connect("activate", self._on_resume)
            self.menu.append(resume_item)
            self._append_stop_and_cancel()
        elif self._record_alive():
            pause_item = Gtk.MenuItem(label="Pausar")
            pause_item.connect("activate", self._on_pause)
            self.menu.append(pause_item)
            self._append_stop_and_cancel()
        else:
            record_item = Gtk.MenuItem(label="Grabar")
            record_item.connect("activate", self._on_record)
            self.menu.append(record_item)
        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)
        self.menu.show_all()

    def _append_stop_and_cancel(self) -> None:
        new_item = Gtk.MenuItem(label="Nueva reunión")
        new_item.connect("activate", self._on_new_meeting)
        self.menu.append(new_item)
        stop_item = Gtk.MenuItem(label="Detener")
        stop_item.connect("activate", self._on_stop)
        self.menu.append(stop_item)
        cancel_item = Gtk.MenuItem(label="Cancelar")
        cancel_item.connect("activate", self._on_cancel)
        self.menu.append(cancel_item)

    def _on_record(self, *_args: object) -> None:
        if self._record_alive() or self.state.phase == "recording":
            return
        self.manual = True
        now = GLib.get_monotonic_time() / 1_000_000
        action = tick(
            self.state,
            foreign_active=bool(self.clients),
            now=now,
            start_requested=True,
            hold=True,
        )
        if action == "start":
            log_line("grabación manual")
            self._start_recording()
        self._paint()

    def _on_pause(self, *_args: object) -> None:
        if not self._record_alive():
            return
        if self.mp3 is not None:
            self._pause_audio_at = probe_duration_seconds(self.mp3)
        self._pause_wall = datetime.now()
        self._signal_tree(signal.SIGSTOP)
        self.paused = True
        self.pause_started = GLib.get_monotonic_time() / 1_000_000
        self._call_ended_notified = False
        self._silence_since = None
        log_line("grabación en pausa")
        self._paint()

    def _save_pause(self) -> None:
        wall = self._pause_wall
        audio_at = self._pause_audio_at
        self._pause_wall = None
        self._pause_audio_at = None
        if self.mp3 is None or wall is None or audio_at is None:
            return
        paused_seconds = (datetime.now() - wall).total_seconds()
        add_pause(self.mp3, audio_at, paused_seconds)

    def _on_resume(self, *_args: object) -> None:
        if not self._record_alive():
            return
        self._save_pause()
        self._close_pause_interval()
        self._signal_tree(signal.SIGCONT)
        self.paused = False
        self._call_ended_notified = False
        self._silence_since = None
        self._silence_checked_at = 0.0
        log_line("grabación reanudada")
        self._paint()

    def _on_cancel(self, *_args: object) -> None:
        if not self._record_alive():
            return
        if self._cancel_dialog is not None:
            self._cancel_dialog.present()
            return
        dialog = Gtk.MessageDialog(
            None,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.NONE,
            "¿Borrar esta grabación?",
        )
        dialog.format_secondary_text("Se descarta el audio y no se transcribe.")
        dialog.add_button("Seguir grabando", Gtk.ResponseType.CANCEL)
        dialog.add_button("Sí, borrar", Gtk.ResponseType.OK)
        dialog.set_keep_above(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.connect("response", self._on_cancel_response)
        self._cancel_dialog = dialog
        dialog.show_all()

    def _on_cancel_response(self, dialog: Gtk.MessageDialog, response: int) -> None:
        self._cancel_dialog = None
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not self._record_alive():
            return
        self.cancel_requested = True
        self.restart_after_stop = False
        if self.paused:
            self._save_pause()
            self._signal_tree(signal.SIGCONT)
            self.paused = False
            self.pause_started = None
        self.stop_requested = True
        log_line("cancelación pedida")

    def _on_search(self, *_args: object) -> None:
        if self._search_dialog is not None:
            self._search_dialog.present()
            return
        dialog = Gtk.Dialog(title="Buscar en las reuniones")
        dialog.set_default_size(880, 520)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_border_width(8)
        query = Gtk.Entry()
        query.set_placeholder_text("Tema o palabras")
        mode = Gtk.ComboBoxText()
        mode.append_text("Tema")
        mode.append_text("Palabra")
        mode.set_active(0)
        participant = Gtk.Entry()
        participant.set_placeholder_text("Participante (opcional)")
        button = Gtk.Button(label="Buscar")
        status = Gtk.Label(label="")
        status.set_xalign(0)
        store = Gtk.ListStore(str, str, str, str, str, str)
        tree = Gtk.TreeView(model=store)
        tree.set_headers_visible(True)
        tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        _append_search_column(tree, "Relevancia", 0, expand=False)
        _append_search_column(tree, "Reunión", 1, expand=False)
        _append_search_column(tree, "Hora", 2, expand=False)
        _append_search_column(tree, "Quién", 3, expand=False)
        _append_search_column(tree, "Texto", 4, expand=True, wrap=True)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(tree)
        scrolled.set_vexpand(True)
        box.pack_start(query, False, False, 0)
        box.pack_start(mode, False, False, 0)
        box.pack_start(participant, False, False, 0)
        box.pack_start(button, False, False, 0)
        box.pack_start(status, False, False, 0)
        box.pack_start(scrolled, True, True, 0)
        button.connect(
            "clicked",
            lambda *_a: self._run_search(query, mode, participant, store, button, status),
        )
        query.connect(
            "activate",
            lambda *_a: self._run_search(query, mode, participant, store, button, status),
        )
        tree.connect("row-activated", self._on_search_row, store)
        dialog.connect("delete-event", self._on_search_close)
        self._search_dialog = dialog
        dialog.show_all()

    def _on_search_close(self, *_args: object) -> bool:
        self._search_dialog = None
        return False

    def _run_search(
        self,
        query: Gtk.Entry,
        mode: Gtk.ComboBoxText,
        participant: Gtk.Entry,
        store: Gtk.ListStore,
        button: Gtk.Button,
        status: Gtk.Label,
    ) -> None:
        button.set_sensitive(False)
        button.set_label("Buscando...")
        status.set_text("Buscando...")
        store.clear()
        text = query.get_text()
        who = participant.get_text()
        word = (mode.get_active_text() or "Tema") == "Palabra"
        try:
            command = search_command(
                graba_reunion_bin(),
                text,
                word=word,
                participant=who,
                output_dir=default_output_dir(),
            )
        except FileNotFoundError as error:
            self._finish_search(button, status, str(error))
            return

        def worker() -> None:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as error:
                GLib.idle_add(self._show_search_error, store, button, status, str(error))
                return
            GLib.idle_add(
                self._show_search_results,
                store,
                button,
                status,
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_search(self, button: Gtk.Button, status: Gtk.Label, message: str) -> None:
        button.set_label("Buscar")
        button.set_sensitive(True)
        status.set_text(message)

    def _show_search_error(
        self,
        store: Gtk.ListStore,
        button: Gtk.Button,
        status: Gtk.Label,
        message: str,
    ) -> bool:
        store.clear()
        self._finish_search(button, status, message)
        return False

    def _show_search_results(
        self,
        store: Gtk.ListStore,
        button: Gtk.Button,
        status: Gtk.Label,
        code: int,
        stdout: str,
        stderr: str,
    ) -> bool:
        store.clear()
        if code != 0:
            self._finish_search(button, status, (stderr or "La búsqueda falló.").strip())
            return False
        try:
            payload = json.loads(stdout or "[]")
        except json.JSONDecodeError:
            self._finish_search(button, status, "La búsqueda no devolvió JSON.")
            return False
        if not payload:
            self._finish_search(button, status, "Sin resultados.")
            return False
        for item in payload:
            path_text = item.get("path") or ""
            score = item.get("score")
            if isinstance(score, (int, float)):
                score_text = f"{round(score * 100)}%"
            else:
                score_text = ""
            store.append(
                [
                    score_text,
                    meeting_stamp(Path(path_text)),
                    item.get("spoken_at") or "",
                    item.get("speaker") or "",
                    item.get("snippet") or "",
                    path_text,
                ]
            )
        count = len(payload)
        noun = "resultado" if count == 1 else "resultados"
        self._finish_search(button, status, f"{count} {noun}")
        return False

    def _on_search_row(
        self,
        _tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
        store: Gtk.ListStore,
    ) -> None:
        target = store[path][5]
        clock = store[path][2]
        if target:
            open_viewer(Path(target), clock=clock)

    def _on_view(self, *_args: object) -> None:
        open_viewer()

    def _on_open_transcript(self, _item: Gtk.MenuItem, path_text: str) -> None:
        open_viewer(Path(path_text))

    def _on_new_meeting(self, *_args: object) -> None:
        if not self._record_alive():
            return
        self.restart_after_stop = True
        log_line("nueva reunión pedida")
        self._stop_recording()
        self._paint()

    def _start_followup(self) -> None:
        self.manual = not self.clients
        self.state.phase = "recording"
        self.state.arm_since = None
        self.state.quiet_since = None
        log_line("sigue con una grabación nueva")
        self._start_recording()

    def _on_stop(self, *_args: object) -> None:
        self.restart_after_stop = False
        self.stop_requested = True

    def _on_quit(self, *_args: object) -> None:
        self.quitting = True
        self.restart_after_stop = False
        if self._record_alive():
            self.stop_requested = True
            return
        Gtk.main_quit()


def main() -> None:
    MicIndicator()
    Gtk.main()
