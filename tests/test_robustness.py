"""U3: the robustness table is internally consistent and the badge wording matches it."""

from __future__ import annotations

import robustness as R
import wording as w


def test_summary_counts_match_rows() -> None:
    t = R.load()
    assert set(t["summary"]) == set(R.FINDINGS)
    for key, s in t["summary"].items():
        rows = [r for r in t["rows"] if r["finding"] == key]
        assert 3 <= len(rows) <= 6
        assert s["n"] == sum(r["holds"] is not None for r in rows)
        assert s["holds"] == sum(bool(r["holds"]) for r in rows)
        assert s["not_computable"] == sum(r["holds"] is None for r in rows)


def test_badge_text() -> None:
    assert w.robustness_badge_text(4, 5) == "Holds in 4 of 5 robustness checks"
    assert w.robustness_badge_text(5, 5) == "Holds in all 5 robustness checks"
    assert w.robustness_badge_text(0, 4) == "Holds in 0 of 4 robustness checks"
    assert w.robustness_badge_text(4, 4, 1) == "Holds in all 4 robustness checks (1 not computable)"


def test_summarise_on_toy_rows() -> None:
    rows = [R._row("R1", "a", True, ""), R._row("R1", "b", False, ""), R._row("R1", "c", None, "")]
    s = R.summarise(rows)["R1"]
    assert (s["holds"], s["n"], s["not_computable"]) == (1, 2, 1)


def test_desk_note_alternative_uses_business_day_weights() -> None:
    import forecast
    fz = forecast.load_frozen()["currencies"]["USD"]
    assert R.excess(fz, nights=False) < R.excess(fz)       # the turn gets more weight with nights
    assert R.excess(fz, start_bd=10) != R.excess(fz, start_bd=10)  # NaN: the frozen path is too short
