"""Phase 3: regimes from the data, Markov switching, reserves fits, case studies, wording."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import corridors as C
import wording as w


def test_runs_and_phases() -> None:
    mask = pd.Series([False, True, True, False, True], index=pd.date_range("2026-01-01", periods=5))
    assert C.runs(mask) == [(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")),
                            (pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05"))]
    policy = pd.Series([1.0, 1.25, 1.5, 1.5, 1.25], index=pd.date_range("2026-01-01", periods=5))
    phases = C.policy_phases(policy)
    assert [p["kind"] for p in phases] == ["hiking", "cutting"] and phases[0]["n"] == 2


def test_regimes_are_generated_from_the_data() -> None:
    eur = C.regimes("EUR")
    negative = [r for r in eur if r["kind"] == "negative rates"]
    assert negative and negative[0]["start"] == pd.Timestamp("2014-06-11") and negative[0]["end"] == pd.Timestamp("2022-07-26")
    jpy_negative = [r for r in C.regimes("JPY") if r["kind"] == "negative rates"]
    assert jpy_negative[0]["start"] == pd.Timestamp("2016-02-16")


def test_piecewise_recovers_a_kink_and_logistic_pressure_point() -> None:
    x = np.linspace(1, 5, 200)
    y = np.where(x < 2.5, -5 + 20 * (2.5 - x), -5.0)
    m = C.fit_piecewise(x, y)
    assert m["kink"] == pytest.approx(2.5, abs=0.1)
    logistic = {"kind": "logistic", "params": [-5.0, 30.0, 2.0, 0.2]}
    p = C.pressure_point(logistic)
    assert C.predict_logistic(logistic, np.array([p]))[0] == pytest.approx(-5 + C.PRESSURE_BP)


def test_markov_is_reproducible_and_uses_train_parameters() -> None:
    rng = np.random.default_rng(3)
    calm = rng.normal(-5, 1, 400)
    stressed = rng.normal(10, 8, 100)
    y = pd.Series(np.concatenate([calm[:200], stressed, calm[200:]]),
                  index=pd.bdate_range("2021-01-01", periods=500))
    a, b = C.fit_markov(y), C.fit_markov(y)
    assert a["mean_bp"] == b["mean_bp"]
    assert a["sd_bp"]["stressed"] > a["sd_bp"]["calm"]


def test_committed_summary() -> None:
    s = C.load_summary()
    assert set(s["markov"]) == {"EUR", "USD", "JPY"} and set(s["reserves"]) == {"USD", "EUR"}
    for r in s["reserves"].values():
        assert r["winner"] in C.FITS and r["pressure_band"][0] <= r["pressure_point"] <= r["pressure_band"][1]
    sept = [c for c in s["cases"] if c["case"] == "September 2019" and c["currency"] == "USD"][0]
    assert sept["peak_date"] == "2019-09-17" and sept["peak_bp"] > 300


def test_corridor_wording_flips() -> None:
    inside = w.corridor_sentence("USD", 0.96, 0.02, 0.0, 3.0, "2018-04-02")
    assert "stayed inside" in inside and "held tightly" in inside
    below = w.corridor_sentence("EUR", 0.0, 1.0, -6.8, 0.4, "2019-10-01")
    assert "below the ECB's floor" in below and "6.8 bp below" in below
    m_good = w.markov_sentence("USD", -5.7, 8.6, 25.1, 5.1, -3.0, -3.5, 0.06)
    assert "better than a single normal" in m_good and "funding stress" in m_good
    m_bad = w.markov_sentence("EUR", -4.6, -7.7, 1.1, 0.9, -2.5, -2.3, 1.0)
    assert "does not travel out of sample" in m_bad and "how deep the floor sits" in m_bad
    r = w.reserves_sentence("USD", "linear", -6.4, 1.57, [1.52, 2.89], 2.89, "reserves")
    assert "rises by about 6.4 bp" in r and "a reference only" in r and "inside that band" in r
    r2 = w.reserves_sentence("USD", "piecewise", 3.0, 1.57, [1.52, 2.0], 2.89, "reserves")
    assert "falls" in r2 and "reference only" not in r2 and "above that band" in r2
    stats = {"EUR": {"recent_iqr_bp": 0.4, "recent_median_bp": -6.8}, "USD": {"recent_iqr_bp": 3.0, "recent_median_bp": 0}}
    assert w.corridors_answer(stats, {"USD": {"slope_per_unit": -6.4}})[0] == "Yes, within a few basis points"
    stats["USD"]["recent_iqr_bp"] = 9
    ans = w.corridors_answer(stats, {"USD": {"slope_per_unit": 2.0}})
    assert ans[0].startswith("Mostly") and "have not pushed" in ans[1]
