"""Phase 4: Kaplan-Meier by hand, blowout episodes, collateral decision rule, events, wording."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import collateral as C
import events
import france as Fr
import survival
import wording as w


def test_kaplan_meier_matches_a_hand_computation() -> None:
    # Durations 2, 3, 3, 5 (censored), 7: S(2)=4/5, S(3)=4/5*1/3... computed step by step:
    km = survival.kaplan_meier([2, 3, 3, 5, 7], [True, True, True, False, True])
    s = dict(zip(km["time"], km["survival"]))
    assert s[2.0] == pytest.approx(0.8)
    assert s[3.0] == pytest.approx(0.8 * (1 - 2 / 4))
    assert s[5.0] == pytest.approx(0.4)          # censoring does not move the curve
    assert s[7.0] == pytest.approx(0.0)
    assert survival.median_time(km) == 3.0
    row = km[km["time"] == 2.0].iloc[0]
    greenwood = 1 / (5 * 4)
    assert row["se"] == pytest.approx(0.8 * np.sqrt(greenwood))
    assert row["lower"] < 0.8 < row["upper"]
    assert survival.survival_at(km, 4)["survival"] == pytest.approx(0.4)


def test_episode_rule_start_peak_and_half_retracement() -> None:
    idx = pd.date_range("2008-01-01", periods=30, freq="MS")
    values = [50.0] * 14 + [90, 110, 100, 85, 79, 70, 60] + [55.0] * 9
    eps = Fr.episodes(pd.Series(values, index=idx), "XX", threshold=30)
    assert len(eps) == 1
    e = eps[0]
    assert e["start"] == idx[14] and e["baseline"] == 50 and e["peak"] == 110
    # Half retracement: 110 - 0.5*(110-50) = 80 -> first month <= 80 is the 79 month.
    assert e["recovery"] == idx[18] and e["duration"] == 4 and e["observed"]
    ongoing = Fr.episodes(pd.Series(values[:17], index=idx[:17]), "XX", threshold=30)
    assert not ongoing[0]["observed"]


def test_a_steady_grind_is_not_a_blowout() -> None:
    idx = pd.date_range("2008-01-01", periods=40, freq="MS")
    grind = pd.Series(np.linspace(50, 100, 40), index=idx)  # +1.3 bp a month
    assert Fr.episodes(grind, "XX", threshold=30) == []


def test_collateral_decision_rule() -> None:
    assert C.decide({"credit": 5, "liquidity": 1, "de_holdings": 1}, {"credit": 0.01, "liquidity": 0.5, "de_holdings": 0.5}) == "credit"
    assert C.decide({"credit": 1, "liquidity": 4, "de_holdings": 1}, {"credit": 0.01, "liquidity": 0.01, "de_holdings": 0.5}) == "scarcity"
    assert C.decide({"credit": 5, "liquidity": 1, "de_holdings": 1}, {"credit": 0.2, "liquidity": 0.5, "de_holdings": 0.5}) == "both / unclear"


def test_events_have_official_sources_and_exclusions_are_recorded() -> None:
    listed = ("Assemblée nationale", "Bloomberg", "CNBC", "Reuters", "Financial Times", "Les Echos", "Le Monde",
              "Moody's (official)", "Agence France Trésor (official)")
    for ev in events.EVENTS:
        outlets = {s["outlet"] for s in ev["sources"]}
        assert len(outlets) >= 2 and outlets <= set(listed)                     # two independent listed sources
        for s in ev["sources"]:
            assert s["url"].startswith("https://") and s["accessed"] and s["method"]
        pd.Timestamp(ev["date"])
    assert events.EXCLUDED and all(e["reason"] for e in events.EXCLUDED)


def test_committed_france_summary_is_consistent() -> None:
    s = Fr.load_summary()
    d = s["decomposition"]
    assert d["oat_leg"] + d["bund_leg"] == pytest.approx(d["spread_change"])
    e = s["euro_wide"]
    assert e["cum_euro_wide"] + e["cum_france_specific"] == pytest.approx(e["cum_change"])
    assert s["survival"]["n_episodes"] >= 10 and s["threshold_bp"] == Fr.THRESHOLD_BP
    assert 0 <= s["repo"]["position_before"] <= 1.5


def test_france_wording_flips() -> None:
    assert "not in a blowout" in w.france_status_sentence(False, 97, 75, 8.4, 30)
    assert "is in a blowout" in w.france_status_sentence(True, 140, None, None, 30)
    assert "mainly France-specific" in w.france_specific_sentence("2024-06", 45, -9, 54)
    assert "mainly euro-wide" in w.france_specific_sentence("2024-06", 45, 40, 5)
    assert "closer to Italian" in w.repo_treatment_sentence(7, 3.5, 13, 4, 0.5, 0.8, 0.001, 4, 3)
    assert "away from Italian" in w.repo_treatment_sentence(7, 3.5, 13, 4, 0.8, 0.5, 0.3, 2, 3)
    assert "unusually large" in w.event_sentence("x", "2025-09", 20, 0.95)
    assert "narrowed" in w.event_sentence("x", "2025-09", -3, 0.1)
    yes = w.oat_answer(False, 9, 0.6, 0.5, 0.6, 0.8, True, True, True, 0.9)[0]
    no = w.oat_answer(False, 9, 0.6, 0.5, 0.6, 0.8, False, False, False, 0.9)[0]
    assert yes.startswith("Possibly") and no.startswith("Not yet: none")
    assert w.collateral_answer("scarcity", "both / unclear", 0.03, 0.001)[0] == "Scarcity for Italy; no clear driver for France"
    assert w.collateral_answer("credit", "credit", 0.3, 0.3)[0] == "Mostly credit risk"
    assert "neither country" in w.collateral_answer("credit", "credit", 0.3, 0.3)[1]
