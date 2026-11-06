"""D7: the UK (hand-built examples, offline) and its sentences."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import findings
import uk as U
import validation
import wording as w


def _long() -> pd.DataFrame:
    weds = pd.date_range("2024-01-03", periods=120, freq="7D")
    share = np.linspace(5, 35, len(weds))
    reserves = pd.Series(700.0, index=weds) * 1e3
    str_ = reserves * share / 100 * 0.6
    iltr = reserves * share / 100 * 0.4
    days = pd.bdate_range(weds[0], weds[-1])
    return validation.demo_long({
        "boe_reserves": reserves, "boe_str": str_, "boe_iltr": iltr, "boe_apf": pd.Series(500e3, index=weds),
        "sonia": pd.Series(np.linspace(3.70, 3.735, len(days)), index=days),
        "bank_rate": pd.Series([3.75], index=days[:1]),
        "estr": pd.Series(2.0, index=days), "sofr": pd.Series(4.0, index=days)})


def test_sonia_spread_carries_bank_rate_forward() -> None:
    s = U.sonia_spread(_long())
    assert s.iloc[0] == pytest.approx(-5.0) and s.iloc[-1] == pytest.approx(-1.5)
    st = U.spread_stats(s, recent=10)
    assert st["recent_share_above"] == 0.0 and st["latest_bp"] == pytest.approx(-1.5)


def test_weekly_frame_and_trend() -> None:
    wk = U.weekly_frame(_long())
    assert wk["repo_share"].iloc[0] == pytest.approx(5.0) and wk["repo_share"].iloc[-1] == pytest.approx(35.0)
    tr = U.share_trend(wk["repo_share"], weeks=104)
    assert tr["verdict"] == "increasingly" and tr["slope_pp_per_year"] > 0
    flat = U.share_trend(pd.Series(np.random.default_rng(0).normal(20, 1, 104), index=wk.index[:104]))
    assert flat["verdict"] == "no significant change"
    falling = U.share_trend(-wk["repo_share"])
    assert falling["verdict"] == "decreasingly"
    assert U.weeks_ago(wk["repo_share"], 1000) is None


def test_link_is_positive_when_both_rise() -> None:
    long = _long()
    assert U.link(U.sonia_spread(long), U.weekly_frame(long), start="2024-01-01") > 0.9


def _summary() -> tuple[dict, dict, dict]:
    wk = {"str_bn": 143.0, "iltr_bn": 84.0, "repo_share_pct": 35.2, "reserves_bn": 645.0, "latest_date": "2026-10-28",
          "repo_share_52w_ago": 20.8, "repo_share_104w_ago": 7.1, "apf_bn": 488.0, "apf_104w_ago": 659.0}
    trend = {"verdict": "increasingly", "n": 104, "slope_pp_per_year": 15.4, "ci": [14.8, 16.0], "p_value": 0.0001}
    sp = {"by_year": {2023: {"median": -7.1}, 2026: {"median": -2.0}}, "recent_median_bp": -2.0,
          "recent_share_above": 0.0}
    return wk, trend, sp


@pytest.mark.parametrize("verdict,word", [("increasingly", "increasingly supplied"),
                                          ("decreasingly", "decreasingly supplied"),
                                          ("no significant change", "no significant change")])
def test_uk_repo_sentence_flips(verdict: str, word: str) -> None:
    wk, trend, _ = _summary()
    s = w.uk_repo_sentence(wk, {**trend, "verdict": verdict})
    assert word in s and "35% of reserve balances" in s and "shrank from GBP 659 bn" in s
    assert "grew from" in w.uk_repo_sentence({**wk, "apf_104w_ago": 300.0}, trend)


def test_uk_spread_sentence_flips() -> None:
    _, _, sp = _summary()
    s = w.uk_spread_sentence(sp, 0.9)
    assert "2.0 bp below Bank Rate" in s and "closer to Bank Rate than in 2023" in s and "rose together" in s
    s2 = w.uk_spread_sentence({**sp, "recent_median_bp": -9.0}, -0.5)
    assert "further from" in s2 and "fell as" in s2


def test_uk_lines_consistent_with_results() -> None:
    r = findings.load_results()
    u = r["uk"]
    lines = findings.uk_lines(r)
    tr = u["trend"]
    assert (tr["verdict"] == "increasingly") == (tr["slope_pp_per_year"] > 0 and tr["p_value"] < 0.05)
    assert ("increasingly supplied" in lines[0]) == (tr["verdict"] == "increasingly")
    assert u["weekly"]["repo_bn"] == pytest.approx(u["weekly"]["str_bn"] + u["weekly"]["iltr_bn"])
    assert findings.uk_lines({}) == []
