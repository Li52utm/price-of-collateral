"""D4: who holds the collateral (hand-built examples, offline) and its sentences."""

from __future__ import annotations

import pandas as pd
import pytest

import findings
import holders as H
import validation
import wording as w


def _long() -> pd.DataFrame:
    days = pd.to_datetime(["2021-12-31", "2022-12-31", "2025-12-31"])
    vals = {"S1_S2": [90.0, 100.0, 150.0], "S121": [20.0, 30.0, 20.0], "S122_S123": [20.0, 20.0, 40.0],
            "S124-S129": [10.0, 10.0, 10.0], "S2": [30.0, 35.0, 75.0]}
    series = {f"hold_FR_{k}": pd.Series(v, index=days) * 1e3 for k, v in vals.items()}
    series["estr"] = pd.Series([1.0], index=days[-1:])
    series["sofr"] = pd.Series([1.0], index=days[-1:])
    return validation.demo_long(series)


def test_holdings_and_shares() -> None:
    h = H.holdings("FR", _long())
    assert h.loc["2022-12-31", "Other domestic"] == pytest.approx(5.0)
    sh = H.shares(h)
    assert sh.loc["2025-12-31"].sum() == pytest.approx(100.0)
    assert sh.loc["2025-12-31", "Non-residents"] == pytest.approx(50.0)


def test_shift_and_absorption() -> None:
    h = H.holdings("FR", _long())
    s = H.shift(H.shares(h), 2022)
    assert s["change_pp"]["Non-residents"] == pytest.approx(15.0)
    assert s["largest_rise"] == "Non-residents" and s["largest_fall"] == "Domestic central bank"
    a = H.absorption(h, 2022)
    assert a["total_change_bn"] == pytest.approx(50.0)
    assert a["change_bn"]["Non-residents"] == pytest.approx(40.0)
    assert a["share_of_increase"]["Domestic banks"] == pytest.approx(0.4)
    assert a["absorbers"] == ["Non-residents", "Domestic banks"]   # other domestic: 5 -> 5, unchanged
    assert H.shift(H.shares(h), 1999) == {} and H.absorption(h, 1999) == {}


def test_sentences_follow_the_numbers() -> None:
    h = H.holdings("FR", _long())
    s = H.shift(H.shares(h), 2022)
    line = w.holder_shift_sentence("FR", s)
    assert "largest gain in share was non-residents (+15.0 pp" in line and "the domestic central bank (-" in line
    assert "the same for" in w.holder_summary_sentence({"FR": s, "IT": s})
    other = {**s, "largest_rise": "Domestic banks"}
    assert "shifted differently" in w.holder_summary_sentence({"FR": s, "IT": other})
    a = H.absorption(h, 2022)
    text = w.france_absorption_sentence(a)
    assert text.startswith("French government debt grew") and "reduced its holdings" in text
    a2 = {**a, "change_bn": {**a["change_bn"], "Domestic central bank": 5.0}}
    assert "increased its holdings" in w.france_absorption_sentence(a2)
    assert "not available" in w.france_absorption_sentence({})


def test_holder_lines_consistent_with_results() -> None:
    r = findings.load_results()
    h = r["holders"]
    lines = findings.holder_lines(r)
    assert len(lines) == 1 + len(h["countries"])
    fr = h["countries"]["FR"]["shift"]
    assert w.holder_phrase(fr["largest_rise"]) in lines[1]
    a = h["france_absorption"]
    assert a["largest_absorber"] == max(a["change_bn"], key=a["change_bn"].get)
    assert findings.holder_lines({}) == [] and findings.france_absorption_line({}) is None
