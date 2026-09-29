from __future__ import annotations

from pathlib import Path

from graba_reunion.meetings import list_meetings, meeting_by_rank


def test_rank_one_is_newest_and_skips_generic_title(tmp_path: Path) -> None:
    (tmp_path / "reunion_2026-01-01_09-00-00.txt").write_text("vieja\n", encoding="utf-8")
    (tmp_path / "reunion_2026-02-02_10-00-00.txt").write_text("nueva\n", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("no entra\n", encoding="utf-8")
    (tmp_path / "reunion_2026-02-02_10-00-00_minuta.md").write_text(
        "# Minuta de reunión\n\n# Presupuesto\n",
        encoding="utf-8",
    )
    meetings = list_meetings(tmp_path, prefix="reunion")
    assert [item.path.name for item in meetings] == [
        "reunion_2026-02-02_10-00-00.txt",
        "reunion_2026-01-01_09-00-00.txt",
    ]
    assert meetings[0].title == "Presupuesto"
    assert meetings[0].recorded_label == "2026-02-02 10:00:00"
    assert meeting_by_rank(tmp_path, 1, prefix="reunion") == meetings[0]
    assert meetings[1].title == "reunion_2026-01-01_09-00-00"
