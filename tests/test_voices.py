from __future__ import annotations

from pathlib import Path

from graba_reunion.voices import (
    SpeakerTrack,
    VoiceBank,
    VoiceCluster,
    VoiceProfile,
    bank_from_names,
    best_similarity,
    cluster_tracks,
    is_new_voice,
    merge_voice_banks,
    parse_names_file,
    patch_names_file,
    profile_match_scores,
    transcript_from_whisperx,
    voice_pair_scores,
)


def _track(label: str, embedding: tuple[float, ...], *, source: str = "a.mp3") -> SpeakerTrack:
    return SpeakerTrack(
        source_name=source,
        mp3_path=f"/tmp/{source}",
        label=label,
        embedding=embedding,
        speech_seconds=10.0,
        clip_start=1.0,
        clip_end=5.0,
    )


def test_playback_window_skips_turn_edge() -> None:
    from graba_reunion.voices import playback_window

    start, end = playback_window(1841.701, 1853.701)
    assert start == 1841.701 + 3.0
    assert end == 1853.701
    short_start, short_end = playback_window(10.0, 13.0)
    assert (short_start, short_end) == (10.0, 13.0)


def test_nan_embedding_does_not_collapse_clusters() -> None:
    fresh = _track("SPEAKER_00", (1.0, 0.0))
    other = _track("SPEAKER_01", (0.0, 1.0))
    broken = _track("SPEAKER_02", (float("nan"), float("nan")))
    clusters = cluster_tracks([fresh, other, broken], threshold=0.7)
    assert len(clusters) == 3


def test_cluster_tracks_groups_similar_voices() -> None:
    same_a = _track("SPEAKER_00", (1.0, 0.0), source="uno.mp3")
    same_b = _track("SPEAKER_01", (0.99, 0.01), source="dos.mp3")
    other = _track("SPEAKER_00", (0.0, 1.0), source="dos.mp3")
    clusters = cluster_tracks([same_a, other, same_b], threshold=0.7)
    assert len(clusters) == 2
    grouped = {
        frozenset(track.source_name + track.label for track in cluster.tracks)
        for cluster in clusters
    }
    assert frozenset({"uno.mp3SPEAKER_00", "dos.mp3SPEAKER_01"}) in grouped


def test_parse_names_and_build_bank() -> None:
    clusters = cluster_tracks(
        [_track("SPEAKER_00", (1.0, 0.0)), _track("SPEAKER_01", (0.0, 1.0))],
        threshold=0.99,
    )
    names = parse_names_file("# comentario\n1=Pablo\n2=\n3=Ana]\n")
    bank = bank_from_names(clusters, names)
    assert [profile.name for profile in bank.profiles] == ["Pablo"]
    assert bank.match([1.0, 0.0]) == "Pablo"
    assert bank.match([0.0, 1.0]) is None


def test_ignored_voice_is_not_a_profile() -> None:
    clusters = cluster_tracks(
        [_track("SPEAKER_00", (1.0, 0.0)), _track("SPEAKER_01", (0.0, 1.0))],
        threshold=0.99,
    )
    bank = bank_from_names(clusters, {1: "Pablo", 2: "-"})
    assert [profile.name for profile in bank.profiles] == ["Pablo"]
    assert bank.match([0.0, 1.0]) is None
    assert bank.match([1.0, 0.0]) == "Pablo"


def test_voice_pair_scores_rank_the_closer_pair_first() -> None:
    pablo_a = VoiceCluster(1, (_track("SPEAKER_00", (1.0, 0.0)),))
    pablo_b = VoiceCluster(2, (_track("SPEAKER_01", (0.98, 0.02)),))
    other = VoiceCluster(3, (_track("SPEAKER_02", (0.0, 1.0)),))
    scores = voice_pair_scores([pablo_a, other, pablo_b])
    assert scores[0][:2] == (1, 2)
    assert scores[0][2] > 0.9
    assert best_similarity([(1.0, 0.0)], []) == 0.0
    bank = VoiceBank(
        threshold=0.7,
        profiles=(VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),),
    )
    matches = profile_match_scores(pablo_a, bank)
    assert matches[0][0] == "Pablo"
    assert matches[0][1] > 0.9


def test_is_new_voice_skips_known_and_rejected() -> None:
    known = VoiceCluster(1, (_track("SPEAKER_00", (1.0, 0.0)),))
    ignored = VoiceCluster(2, (_track("SPEAKER_01", (0.0, 1.0)),))
    fresh = VoiceCluster(3, (_track("SPEAKER_02", (0.0, 0.0, 1.0)),))
    bank = VoiceBank(
        threshold=0.7,
        profiles=(VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),),
        rejected=((0.0, 1.0),),
    )
    assert is_new_voice(known, bank) is False
    assert is_new_voice(ignored, bank) is False
    assert is_new_voice(fresh, bank) is True


def test_merge_voice_banks_keeps_previous_profiles() -> None:
    base = VoiceBank(
        threshold=0.7,
        profiles=(VoiceProfile(name="Pablo", embeddings=((1.0, 0.0),)),),
    )
    extra = VoiceBank(
        threshold=0.7,
        profiles=(
            VoiceProfile(name="Pablo", embeddings=((0.9, 0.1),)),
            VoiceProfile(name="Mica", embeddings=((0.0, 1.0),)),
        ),
        rejected=((0.2, 0.2),),
    )
    merged = merge_voice_banks(base, extra)
    by_name = {profile.name: profile.embeddings for profile in merged.profiles}
    assert set(by_name) == {"Pablo", "Mica"}
    assert len(by_name["Pablo"]) == 2
    assert merged.rejected == ((0.2, 0.2),)


def test_patch_names_file_updates_only_filled_ids(tmp_path: Path) -> None:
    path = tmp_path / "nombres.txt"
    path.write_text("# lista\n1=\n2=Ana\n", encoding="utf-8")
    patch_names_file({1: "Pablo", 2: "", 3: "Nano"}, path)
    text = path.read_text(encoding="utf-8")
    assert "1=Pablo" in text
    assert "2=Ana" in text
    assert "3=Nano" in text


def test_transcript_uses_profile_name() -> None:
    bank = VoiceBank(
        threshold=0.7,
        profiles=(VoiceProfile(name="Ana", embeddings=((1.0, 0.0),)),),
    )
    text = transcript_from_whisperx(
        {
            "speaker_embeddings": {"SPEAKER_00": [1.0, 0.0], "SPEAKER_01": [0.0, 1.0]},
            "segments": [
                {"speaker": "SPEAKER_00", "text": "hola"},
                {"speaker": "SPEAKER_01", "text": "chau"},
            ],
        },
        bank,
    )
    assert text == "[Ana]: hola\n[SPEAKER_01]: chau\n"


def test_transcript_uses_recording_clock(tmp_path: Path) -> None:
    from datetime import datetime

    from graba_reunion.timing import Pause, RecordingTiming, _write

    audio = tmp_path / "reunion_2026-09-29_13-00-00.mp3"
    audio.write_bytes(b"x")
    _write(
        audio,
        RecordingTiming(
            started_at=datetime(2026, 9, 29, 13, 0, 0),
            duration_seconds=120,
            pauses=(Pause(at_seconds=60, paused_seconds=120),),
        ),
    )
    text = transcript_from_whisperx(
        {"segments": [{"speaker": "SPEAKER_00", "text": "hola", "start": 90}]},
        VoiceBank(threshold=0.7, profiles=()),
        audio=audio,
    )
    assert text == "[13:03:30] [SPEAKER_00]: hola\n"
