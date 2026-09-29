from __future__ import annotations

import subprocess
from pathlib import Path

from graba_reunion.mic_watch import (
    WatchState,
    advance_manual_silence,
    clear_recording_pending,
    descendant_pids,
    file_trailing_is_silent,
    mark_recording_pending,
    parse_capture_clients,
    recent_transcripts,
    recording_decision,
    tick,
    unfinished_recordings,
)


def _node(node_id: int, props: dict) -> dict:
    return {"id": node_id, "type": "PipeWire:Interface:Node", "info": {"props": props}}


def _port(port_id: int, node_id: int) -> dict:
    return {
        "id": port_id,
        "type": "PipeWire:Interface:Port",
        "info": {"props": {"node.id": node_id}},
    }


def _link(out_port: int, in_port: int) -> dict:
    return {
        "id": out_port * 100 + in_port,
        "type": "PipeWire:Interface:Link",
        "info": {"output-port-id": out_port, "input-port-id": in_port},
    }


def _dump() -> list[dict]:
    return [
        _node(
            1,
            {
                "media.class": "Audio/Source",
                "node.name": "alsa_input.mic",
                "node.description": "HyperX",
            },
        ),
        _node(
            2,
            {
                "media.class": "Audio/Source",
                "node.name": "alsa_output.speakers.monitor",
                "node.description": "Monitor",
            },
        ),
        _node(
            3,
            {
                "media.class": "Stream/Input/Audio",
                "application.name": "WEBRTC VoiceEngine",
                "application.process.binary": "Discord",
                "application.process.id": 103,
                "pipewire.client.access": "flatpak",
                "pipewire.access.portal.app_id": "com.discordapp.Discord",
            },
        ),
        _node(
            4,
            {
                "media.class": "Stream/Input/Audio",
                "application.process.binary": "ffmpeg",
                "application.process.id": 5000,
            },
        ),
        _node(
            5,
            {
                "media.class": "Stream/Input/Audio",
                "application.process.binary": "ffmpeg",
                "application.process.id": 7000,
            },
        ),
        _node(
            6,
            {
                "media.class": "Stream/Input/Audio",
                "application.process.binary": "ffmpeg",
                "application.process.id": 8000,
            },
        ),
        _port(10, 1),
        _port(11, 3),
        _port(12, 1),
        _port(13, 4),
        _port(14, 1),
        _port(15, 5),
        _port(18, 2),
        _port(19, 6),
        _link(10, 11),
        _link(12, 13),
        _link(14, 15),
        _link(18, 19),
    ]


def test_discord_counts_and_own_ffmpeg_does_not() -> None:
    clients = parse_capture_clients(_dump(), ignore_pids={5000})
    apps = {client.app for client in clients}
    assert "Discord" in apps
    assert "ffmpeg" in apps
    pids = {client.pid for client in clients}
    assert 5000 not in pids
    assert 7000 in pids
    assert all(client.device != "Monitor" for client in clients)


def test_monitor_link_is_ignored() -> None:
    clients = parse_capture_clients(_dump(), ignore_pids={5000, 7000, 8000})
    assert [client.app for client in clients] == ["Discord"]
    assert clients[0].flatpak is True
    assert clients[0].pid is None


def test_arm_and_quiet_debounce() -> None:
    state = WatchState()
    assert tick(state, foreign_active=True, now=0.0) == "none"
    assert state.phase == "arming"
    assert tick(state, foreign_active=True, now=2.9) == "none"
    assert tick(state, foreign_active=True, now=3.0) == "start"
    assert state.phase == "recording"
    assert tick(state, foreign_active=False, now=4.0) == "none"
    assert tick(state, foreign_active=True, now=5.0) == "none"
    assert state.quiet_since is None
    assert tick(state, foreign_active=False, now=6.0) == "none"
    assert tick(state, foreign_active=False, now=16.0) == "stop"
    assert state.phase == "idle"


def test_arming_cancels_if_mic_drops() -> None:
    state = WatchState()
    tick(state, foreign_active=True, now=0.0)
    assert tick(state, foreign_active=False, now=1.0) == "none"
    assert state.phase == "idle"


def test_manual_silence_stops_after_ten_minutes() -> None:
    since, stop = advance_manual_silence(None, 0.0, silent=True)
    assert since == 0.0
    assert stop is False
    since, stop = advance_manual_silence(since, 599.0, silent=True)
    assert stop is False
    since, stop = advance_manual_silence(since, 600.0, silent=True)
    assert stop is True
    assert advance_manual_silence(10.0, 20.0, silent=False) == (None, False)
    assert advance_manual_silence(10.0, 700.0, silent=None) == (10.0, False)


def test_trailing_silence_on_generated_audio(tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp3"
    loud = tmp_path / "loud.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "2",
            "-q:a",
            "9",
            str(silent),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-q:a",
            "9",
            str(loud),
        ],
        check=True,
    )
    assert file_trailing_is_silent(silent) is True
    assert file_trailing_is_silent(loud) is False


def test_manual_start_and_hold() -> None:
    state = WatchState()
    assert tick(state, foreign_active=False, now=0.0, start_requested=True) == "start"
    assert state.phase == "recording"
    assert tick(state, foreign_active=False, now=30.0, hold=True) == "none"
    assert state.phase == "recording"
    assert state.quiet_since is None
    assert tick(state, foreign_active=False, now=40.0, hold=True, stop_requested=True) == "stop"


def test_paused_recording_does_not_stop() -> None:
    state = WatchState(phase="recording", quiet_since=0.0)
    assert tick(state, foreign_active=False, now=30.0, paused=True) == "none"
    assert state.phase == "recording"
    assert state.quiet_since is None


def test_stop_while_paused() -> None:
    state = WatchState(phase="recording")
    assert tick(state, foreign_active=False, now=0.0, paused=True, stop_requested=True) == "stop"
    assert state.phase == "idle"
    state = WatchState(phase="recording")
    assert tick(state, foreign_active=True, now=0.0, stop_requested=True) == "stop"
    assert state.phase == "idle"


def test_recording_decision_threshold() -> None:
    assert recording_decision(59.9) == "discard"
    assert recording_decision(60.0) == "transcribe"
    assert recording_decision(None) == "transcribe"


def test_unfinished_recordings_skip_transcribed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.mic_watch.data_dir", lambda: tmp_path)
    mp3 = tmp_path / "recordings" / "reunion_x.mp3"
    mp3.parent.mkdir()
    mp3.write_bytes(b"x")
    mark_recording_pending(mp3)
    assert unfinished_recordings() == [mp3.resolve()]
    mp3.with_suffix(".txt").write_text("hola", encoding="utf-8")
    assert unfinished_recordings() == []
    assert not (tmp_path / "pending" / f"{mp3.stem}.path").exists()


def test_clear_recording_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.mic_watch.data_dir", lambda: tmp_path)
    mp3 = tmp_path / "reunion_y.mp3"
    mp3.write_bytes(b"x")
    mark_recording_pending(mp3)
    clear_recording_pending(mp3)
    assert unfinished_recordings() == []


def test_unfinished_drops_marker_if_mp3_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("graba_reunion.mic_watch.data_dir", lambda: tmp_path)
    mp3 = tmp_path / "reunion_z.mp3"
    mark_recording_pending(mp3)
    assert unfinished_recordings() == []
    assert not (tmp_path / "pending" / f"{mp3.stem}.path").exists()


def test_recent_transcripts_last_day(tmp_path) -> None:
    import os

    fresh = tmp_path / "reunion_new.txt"
    newer = tmp_path / "reunion_newer.txt"
    old = tmp_path / "reunion_old.txt"
    other = tmp_path / "notas.md"
    for path in (fresh, newer, old, other):
        path.write_text("hola", encoding="utf-8")
    now = 1_700_000_000.0
    os.utime(fresh, (now - 3600, now - 3600))
    os.utime(newer, (now - 60, now - 60))
    os.utime(old, (now - 25 * 3600, now - 25 * 3600))
    assert recent_transcripts(tmp_path, now=now) == [newer, fresh]


def test_descendant_pids_includes_child() -> None:
    import os

    child = subprocess.Popen(["sleep", "30"])
    try:
        assert child.pid in descendant_pids(os.getpid())
    finally:
        child.terminate()
        child.wait(timeout=2)
