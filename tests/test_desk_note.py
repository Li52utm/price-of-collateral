"""Phase 6: the desk note's client rule, its wording, and the generated findings."""

from __future__ import annotations

import copy

import pytest

import desk_note
import findings
import wording as w


def test_term_out_and_client_verdict_flip() -> None:
    lock, line = w.term_out_line("USD", 8.0, 3.0, 1.0)
    assert lock and line.startswith("USD: Term out")
    assert "above the term premium (+3.0 bp: term funding costs 3.0 bp more" in line
    lock, line = w.term_out_line("EUR", 0.1, None, 1.0)
    assert not lock and "Stay overnight" in line and "no usable term rate" in line
    assert w.client_verdict(True, True)[0] == "Yes"
    assert w.client_verdict(True, False)[0] == "Partly" and "dollar leg" in w.client_verdict(True, False)[1]
    assert w.client_verdict(False, False)[0] == "No"


def test_story_answer_flips_with_the_ranking() -> None:
    assert "now costs more than Italian" in w.story_answer(11, 3, 4, 3)[1]
    assert "still costs less than Italian" in w.story_answer(11, 3, 2, 3)[1]


def test_window_starts_seven_business_days_before_the_turn() -> None:
    frozen = findings.load_results()["frozen"]
    days = desk_note.window_days(frozen["currencies"]["USD"]["path"])
    assert days[0] == "2026-12-21" and "2026-12-31" in days and "2027-01-04" not in days


def test_build_follows_the_rule_when_the_forecast_changes() -> None:
    r = findings.load_results()
    note = desk_note.build(r)
    assert note["client"]["verdict"] in ("Yes", "No", "Partly")
    bumped = copy.deepcopy(r)
    for cur in ("USD", "EUR"):
        for day in bumped["frozen"]["currencies"][cur]["path"].values():
            day["q50"] += 50  # a huge expected spike in both currencies
    assert desk_note.build(bumped)["client"]["verdict"] == "Yes"
    md = desk_note.markdown(note)
    assert "## Recommendation" in md and "Forecast frozen on" in md and note["client"]["verdict"] in md


def test_findings_are_generated_for_every_chapter() -> None:
    r = findings.load_results()
    for key in findings.QUESTIONS:
        q, a, e = findings.answer(key, r)
        assert a != findings.NOT_AVAILABLE[0] and e
    assert len(findings.readme_findings()) == 6
    assert findings.answer("france", {})[1] == findings.NOT_AVAILABLE[0]


def test_expected_excess_uses_the_window_mean() -> None:
    fc = {"latest_level": 0.0, "path": {d: {"q50": 1.0} for d in
                                        ("2026-12-18", "2026-12-21", "2026-12-22", "2026-12-23", "2026-12-24",
                                         "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31", "2027-01-04")}}
    assert desk_note.expected_excess(fc) == pytest.approx(1.0)


def test_night_weights_give_the_turn_its_weekend() -> None:
    import pandas as pd

    import stats_tools as st
    days = pd.DatetimeIndex(["2026-12-21", "2026-12-22", "2026-12-23", "2026-12-24", "2026-12-28", "2026-12-29",
                             "2026-12-30", "2026-12-31"])
    weights = st.night_weights(days, pd.Timestamp("2027-01-04"))
    assert list(weights) == [1, 1, 1, 4, 1, 1, 1, 4] and weights.sum() == 14
    fc = {"latest_level": 0.0, "path": {str(d.date()): {"q50": 14.0 if d == days[-1] else 0.0} for d in days}}
    fc["path"]["2027-01-04"] = {"q50": 0.0}
    assert desk_note.expected_excess(fc) == pytest.approx(4.0)  # 14 bp x 4 nights / 14 nights
