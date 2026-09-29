from __future__ import annotations

from pathlib import Path

from graba_reunion.search import parse_chunks, search_command, search_transcripts


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_parse_chunks_keeps_speaker() -> None:
    chunks = parse_chunks(
        Path("reunion.txt"),
        "[Pablo]: hola\nseguimos\n[Nano]: el acta\n",
    )
    assert [(chunk.speaker, chunk.text) for chunk in chunks] == [
        ("Pablo", "hola seguimos"),
        ("Nano", "el acta"),
    ]


def test_parse_chunks_keeps_clock() -> None:
    chunks = parse_chunks(
        Path("reunion.txt"),
        "[13:10:25] [Pablo]: medicina preventiva\n",
    )
    assert chunks[0].spoken_at == "13:10:25"
    assert chunks[0].speaker == "Pablo"
    assert chunks[0].text == "medicina preventiva"


def test_literal_search_and_participant(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", "[Pablo]: hay que entregar el laboratorio\n[Nano]: el acta\n")
    word_hits = search_transcripts(tmp_path, "ACTA", word=True)
    assert len(word_hits) == 1
    assert word_hits[0].speaker == "Nano"
    assert "acta" in word_hits[0].snippet.casefold()

    participant_hits = search_transcripts(tmp_path, "", participant="pablo")
    assert len(participant_hits) == 1
    assert "laboratorio" in participant_hits[0].snippet


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        if "laboratorio" in text.casefold():
            vectors.append([1.0, 0.0])
        else:
            vectors.append([0.0, 1.0])
    return vectors


def test_topic_search_ranks_with_fake_vectors(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", "[Pablo]: entrega del laboratorio\n[Nano]: silencio\n")
    cache = tmp_path / "cache.json"
    hits = search_transcripts(
        tmp_path,
        "laboratorio",
        participant="Pablo",
        embed_texts=_fake_embed,
        cache_path=cache,
    )
    assert hits
    assert hits[0].speaker == "Pablo"
    assert hits[0].score == 1.0
    assert cache.is_file()

    calls = {"count": 0}

    def counting(texts: list[str]) -> list[list[float]]:
        calls["count"] += 1
        return _fake_embed(texts)

    again = search_transcripts(
        tmp_path,
        "laboratorio",
        embed_texts=counting,
        cache_path=cache,
    )
    assert again
    assert calls["count"] == 1


def test_search_command_flags() -> None:
    command = search_command(
        "graba-reunion",
        "presupuesto",
        word=True,
        participant="Pablo",
        output_dir=Path("/tmp/recs"),
    )
    assert command == [
        "graba-reunion",
        "search",
        "--json",
        "-d",
        "/tmp/recs",
        "--word",
        "--participant",
        "Pablo",
        "presupuesto",
    ]
