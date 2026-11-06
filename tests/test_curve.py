"""D5: French 2s10s against Germany (hand-built examples, offline) and its sentence."""

from __future__ import annotations

import pandas as pd
import pytest

import curve as C
import findings
import wording as w


def _frame() -> pd.DataFrame:
    days = pd.bdate_range("2023-12-25", "2024-06-14")
    n = len(days)
    fr2 = pd.Series(3.0, index=days)
    fr10 = pd.Series([3.3] * (n - 5) + [3.8] * 5, index=days)   # France steepens in the last week
    de2 = pd.Series(2.9, index=days)
    de10 = pd.Series(3.0, index=days)
    return C.curve_frame(fr2, fr10, de2, de10)


def test_curve_frame_and_legs() -> None:
    c = _frame()
    assert c["fr_2s10s"].iloc[0] == pytest.approx(30.0) and c["de_2s10s"].iloc[0] == pytest.approx(10.0)
    assert c["excess"].iloc[0] == pytest.approx(20.0)
    assert (c["excess"] - (c["spread10"] - c["spread2"])).abs().max() < 1e-9


def _summary() -> dict:
    return C.summarise(_frame(), reference=("2023-12-25", "2024-05-31"), base_day=pd.Timestamp("2024-06-03"))


def test_summarise_and_verdict() -> None:
    s = _summary()
    assert s["latest"]["excess"] == pytest.approx(70.0)
    assert s["verdict"] == "unusual" and s["latest_percentile"] == 1.0
    assert s["change_since_base"]["excess"] == pytest.approx(50.0) and s["larger_leg"] == "10-year"
    assert C.steepness_verdict(10.0, 20.0) == "within range"
    assert C.steepness_verdict(-1.0, 20.0) == "none"
    assert C.percentile_of(2.0, pd.Series([1.0, 2.0, 3.0, 4.0])) == 0.5


@pytest.mark.parametrize("verdict,word", [("unusual", "unusually large"), ("within range", "within its"),
                                          ("none", "no extra curve steepness")])
def test_steepness_sentence_flips(verdict: str, word: str) -> None:
    s = _summary()
    s["verdict"] = verdict
    text = w.steepness_sentence(s, verdict)
    assert word in text and "widened" in text and "The same reading holds" in text
    assert "reading changes" in w.steepness_sentence(s, "none" if verdict != "none" else "unusual")
    s["change_since_base"] = {**s["change_since_base"], "excess": -3.0}
    assert "narrowed" in w.steepness_sentence(s)


def test_steepness_line_consistent_with_results() -> None:
    r = findings.load_results()
    m = r["curve"]["main"]
    assert m["verdict"] == C.steepness_verdict(m["latest"]["excess"], m["reference"]["p95"])
    line = findings.steepness_line(r)
    assert ("no extra" in line) == (m["latest"]["excess"] <= 0)
    assert findings.steepness_line({}) is None
