from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from graba_reunion.commands.voice_wizard import _handler, merge_voice_pair
from graba_reunion.voice_enroll import load_review
from graba_reunion.voices import (
    SpeakerTrack,
    VoiceBank,
    VoiceCluster,
    VoiceProfile,
    load_voice_bank,
    names_path,
    save_voice_bank,
)


def _track(label: str, embedding: tuple[float, ...]) -> SpeakerTrack:
    return SpeakerTrack(
        source_name="reunion.mp3",
        mp3_path="/tmp/reunion.mp3",
        label=label,
        embedding=embedding,
        speech_seconds=40.0,
        clip_start=1.0,
        clip_end=8.0,
    )


def test_wizard_saves_a_new_name_and_keeps_the_old_one(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    clips = tmp_path / "data" / "graba-reunion" / "voices" / "clips"
    clips.mkdir(parents=True)
    clip = clips / "2.wav"
    clip.write_bytes(b"RIFFclip")
    save_voice_bank(
        VoiceBank(
            threshold=0.7,
            profiles=(VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),),
        )
    )
    clusters = [
        VoiceCluster(1, (_track("SPEAKER_00", (1.0, 0.0)),)),
        VoiceCluster(2, (_track("SPEAKER_01", (0.0, 1.0)),), clip_path=str(clip)),
    ]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(clusters))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/") as response:
            page = response.read().decode("utf-8")
        assert "Voces nuevas" in page
        assert "parecidos" in page
        with urlopen(f"http://127.0.0.1:{port}/parecidos") as response:
            similar_page = response.read().decode("utf-8")
        assert "Parecidos entre voces" in similar_page
        assert "Unir" in similar_page
        with urlopen(f"http://127.0.0.1:{port}/api/similar") as response:
            similar = json.loads(response.read().decode("utf-8"))
        assert similar["pairs"][0]["score"] < 0.2
        assert similar["voices"]
        with urlopen(f"http://127.0.0.1:{port}/api/voices") as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["known_names"] == ["Pablo"]
        assert [item["id"] for item in payload["voices"]] == [2]
        assert payload["voices"][0]["clip"] == "/clips/2.wav"
        with urlopen(f"http://127.0.0.1:{port}/clips/2.wav") as response:
            assert response.read() == b"RIFFclip"
        missing = Request(f"http://127.0.0.1:{port}/clips/../secreto.wav")
        try:
            urlopen(missing)
            raise AssertionError("el clip de afuera no tiene que servirse")
        except Exception as error:
            assert getattr(error, "code", None) == 404
        body = json.dumps({"names": {"1": "Otra", "2": "Mica", "9": "Nadie"}}).encode()
        request = Request(
            f"http://127.0.0.1:{port}/api/voices",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            saved = json.loads(response.read().decode("utf-8"))
        assert "Mica" in saved["message"]
    finally:
        httpd.shutdown()

    bank = load_voice_bank()
    assert bank.match((1.0, 0.0)) == "Pablo"
    assert bank.match((0.0, 1.0)) == "Mica"
    assert "2=Mica" in names_path().read_text(encoding="utf-8")
    assert "1=Otra" not in names_path().read_text(encoding="utf-8")


def test_merge_voice_pair_moves_both_samples_to_one_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    clusters = [
        VoiceCluster(1, (_track("SPEAKER_00", (1.0, 0.0)),)),
        VoiceCluster(2, (_track("SPEAKER_01", (0.0, 1.0)),)),
    ]
    save_voice_bank(
        VoiceBank(
            threshold=0.7,
            profiles=(
                VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),
                VoiceProfile(name="Mica", embeddings=((0.0, 1.0),)),
            ),
        )
    )
    message = merge_voice_pair(clusters, 1, 2, "Pablo")
    assert "Pablo" in message["message"]
    assert [cluster.cluster_id for cluster in clusters] == [1]
    assert len(clusters[0].tracks) == 2
    bank = load_voice_bank()
    assert [profile.name for profile in bank.profiles] == ["Pablo"]
    assert bank.match((0.0, 1.0)) == "Pablo"
    assert [cluster.cluster_id for cluster in load_review()] == [1]
