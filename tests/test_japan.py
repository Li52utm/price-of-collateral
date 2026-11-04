"""Phase 5: pass-through measures on hand-built paths, the ECM half-life, the committed summary, wording."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import japan as J
import wording as w


def test_half_gap_days_on_a_slow_path() -> None:
    days = pd.bdate_range("2026-01-01", periods=40)
    values = np.r_[np.zeros(10), np.linspace(0.05, 0.25, 10), np.full(20, 0.25)]
    s = pd.Series(values, index=days)
    out = J.half_gap_days(s, days[10], 0.25)
    # Target 0.25; within 0.125 first when the ramp reaches 0.1389 (index 4 of the ramp).
    assert out["half_gap_days"] == int(np.argmax(np.abs(values[10:] - 0.25) <= 0.125))
    instant = pd.Series(np.r_[np.zeros(10), np.full(30, 0.25)], index=days)
    assert J.half_gap_days(instant, days[10], 0.25)["half_gap_days"] == 0


def test_ecm_recovers_a_known_speed() -> None:
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2016-02-16", periods=1500)
    policy = pd.Series(0.0, index=days)
    policy[days >= days[500]] = 0.25
    tona = np.zeros(len(days))
    for t in range(1, len(days)):
        tona[t] = tona[t - 1] - 0.2 * (tona[t - 1] - policy.iloc[t - 1]) + 0.5 * (policy.iloc[t] - policy.iloc[t - 1]) \
            + rng.normal(0, 0.002)
    df = pd.DataFrame({"tona": tona, "policy": policy}, index=days)
    out = J.ecm(df, days[0])
    assert out["gamma"] == pytest.approx(-0.2, abs=0.05)
    assert out["half_life_days"] == pytest.approx(np.log(0.5) / np.log(0.8), rel=0.3)


def test_committed_summary() -> None:
    s = J.load_summary()
    dates = [c["date"] for c in s["changes"]]
    assert "2016-02-16" in dates and "2024-03-21" in dates
    assert s["ecm_negative"]["beta"] is None  # no policy change inside the negative-rate sample
    assert s["ecm_exit"]["half_life_days"] < s["ecm_negative"]["half_life_days"]


def test_japan_wording() -> None:
    assert "on the effective day" in w.japan_change_sentence("2025-01-27", 25, 0, 1.0)
    assert "after 43 business days" in w.japan_change_sentence("2016-02-16", -20, 43, 0.35)
    assert "a 20 bp cut" in w.japan_change_sentence("2016-02-16", -20, 43, 0.35)
    assert w.japan_answer(7, 7, 0.4, 13, -2)[0] == "Yes, immediately"
    assert w.japan_answer(7, 5, 0.4, 13, -2)[0].startswith("Yes, since the exit")
    assert w.japan_answer(7, 2, 0.4, 13, -2)[0] == "Only partly"
