"""D1: the euro runway (hand-built examples, offline) and its generated sentences."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import findings  # noqa: E402
import runway as R  # noqa: E402
import wording as w  # noqa: E402

RES = {"pressure_band": [2.0, 4.0], "pressure_point": 3.0, "kink_identified": True}


def test_boundaries_and_distances() -> None:
    b = R.boundaries(RES)
    assert b == {"upper": 4000.0, "kink": 3000.0, "lower": 2000.0}
    assert R.distances(2500.0, b) == {"upper": -1500.0, "kink": -500.0, "lower": 500.0}


def test_last_cross_below_finds_start_of_current_run() -> None:
    s = pd.Series([5, 3, 5, 3, 2], index=pd.date_range("2024-01-05", periods=5, freq="7D"), dtype=float)
    assert R.last_cross_below(s, 4) == s.index[3]          # the run that started after the last week above 4
    assert R.last_cross_below(s, 1) is None                # latest above the level
    assert R.last_cross_below(pd.Series([1.0, 0.5], index=s.index[:2]), 2) == s.index[0]


def test_trailing_weekly_change_and_paths() -> None:
    s = pd.Series(np.arange(60, 0, -1, dtype=float), index=pd.date_range("2025-01-03", periods=60, freq="7D"))
    assert R.trailing_weekly_change(s, 52) == pytest.approx(-1.0)
    assert np.isnan(R.trailing_weekly_change(s.iloc[:10], 52))
    paths = R.scenario_paths(pd.Timestamp("2026-01-02"), 100.0, -2.0, pd.Timestamp("2026-01-30"))
    assert paths.loc["2026-01-30"].to_dict() == {"slow": 96.0, "base": 92.0, "fast": 88.0}
    assert R.first_at_or_below(paths["base"], 95.0) == pd.Timestamp("2026-01-23")
    assert R.first_at_or_below(paths["base"], 0.0) is None


def test_scenario_table_statuses() -> None:
    hist = pd.Series([5000.0, 4500.0], index=pd.to_datetime(["2026-10-23", "2026-10-30"]))
    b = R.boundaries(RES)
    paths = R.scenario_paths(hist.index[-1], 4500.0, -50.0)
    tab = R.scenario_table(paths, b, hist, -50.0)
    assert tab["base"]["crossings"]["upper"]["status"] == "reached"
    assert tab["fast"]["crossings"]["upper"]["date"] < tab["base"]["crossings"]["upper"]["date"] \
        < tab["slow"]["crossings"]["upper"]["date"]
    rising = R.scenario_table(R.scenario_paths(hist.index[-1], 4500.0, 5.0), b, hist, 5.0)
    assert rising["base"]["crossings"]["kink"]["status"] == "not reached (no drain)"
    below = pd.Series([3500.0, 1500.0], index=hist.index)
    done = R.scenario_table(R.scenario_paths(hist.index[-1], 1500.0, -5.0), b, below, -5.0)
    assert done["base"]["crossings"]["lower"] == {"status": "already crossed", "date": "2026-10-30"}
    slow = R.scenario_table(R.scenario_paths(hist.index[-1], 4500.0, -0.01), b, hist, -0.01)
    assert slow["slow"]["crossings"]["lower"]["status"] == "beyond horizon"


def test_trend_test_recovers_known_slope() -> None:
    days = pd.bdate_range("2025-01-01", "2025-12-31")
    t = (days - days[0]).days / 365.25
    noise = np.random.default_rng(0).normal(0, 0.1, len(days))
    out = R.trend_test(pd.Series(-7 + 2 * t + noise, index=days))
    assert out["slope_bp_per_year"] == pytest.approx(2.0, abs=0.1)
    assert out["ci"][0] < 2.0 < out["ci"][1] and out["p_value"] < 0.001
    assert R.trend_verdict(1.0, 0.01) == "drifting up"
    assert R.trend_verdict(-1.0, 0.01) == "drifting down"
    assert R.trend_verdict(1.0, 0.20) == "no significant trend"


def test_month_turn_days() -> None:
    days = pd.bdate_range("2026-01-26", "2026-02-06")
    turns = R.month_turn_days(days)
    assert list(turns) == [pd.Timestamp("2026-01-30"), pd.Timestamp("2026-02-02"), pd.Timestamp("2026-02-06")]


def test_published_by_respects_lag() -> None:
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-10-23", "2026-10-30"]))
    assert R.published_by(s, 2, pd.Timestamp("2026-11-02")).tolist() == [1.0]
    assert R.published_by(s, 2, pd.Timestamp("2026-11-03")).tolist() == [1.0, 2.0]


def test_distance_sentence_three_cases() -> None:
    b = {"upper": 4000.0, "kink": 3000.0, "lower": 2000.0}
    assert "already below the whole" in w.runway_distance_sentence(1500, "x", b, R.distances(1500, b))
    assert "still above the whole" in w.runway_distance_sentence(4500, "x", b, R.distances(4500, b))
    inside = w.runway_distance_sentence(2500, "x", b, R.distances(2500, b))
    assert "inside the pressure band" in inside and "EUR 500 bn above the band lower end" in inside
    assert "no distance is quoted" in w.runway_distance_sentence(2500, "x", b, None)


def test_drift_and_scenario_sentences() -> None:
    assert "more than accounts for" in w.runway_drift_sentence(-8.0, -10.0)
    assert "accounts for less than half of" in w.runway_drift_sentence(-8.0, -1.0)
    assert "not what moved" in w.runway_drift_sentence(5.0, -1.0)
    hist = pd.Series([5000.0, 4500.0], index=pd.to_datetime(["2026-10-23", "2026-10-30"]))
    tab = R.scenario_table(R.scenario_paths(hist.index[-1], 4500.0, -50.0), R.boundaries(RES), hist, -50.0)
    s = w.runway_scenario_sentence(tab)
    assert s.startswith("These are scenarios, not forecasts") and "enters and leaves" in s
    assert "not identified" in w.runway_scenario_sentence(None)


@pytest.mark.parametrize("slope,p,verdict,word", [(1.0, 0.001, "drifting up", "started drifting up"),
                                                  (-1.0, 0.001, "drifting down", "drifting down"),
                                                  (1.0, 0.4, "no significant trend", "no significant trend")])
def test_trend_sentence_flips(slope: float, p: float, verdict: str, word: str) -> None:
    s = w.spread_trend_sentence(slope, slope - 0.5, slope + 0.5, p, verdict, -7, -6, verdict)
    assert word in s and ("not statistically" in s) == (p >= 0.05) and "the same holds" in s


def test_runway_lines_consistent_with_results() -> None:
    r = findings.load_results()
    rw = r["runway"]
    lines = findings.runway_lines(r)
    n_below = sum(v <= 0 for v in rw["distance_bn"].values())
    assert ("already below the whole" in lines[0]) == (n_below == 3)
    assert "scenarios, not forecasts" in lines[2]
    v = rw["trend"]["main"]
    assert (v["verdict"] == "drifting up") == (v["slope_bp_per_year"] > 0 and v["p_value"] < 0.05)
    assert ("started drifting up" in lines[3]) == (v["verdict"] == "drifting up")
    assert findings.runway_lines({}) == []
