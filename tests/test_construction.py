"""D0: the construction gap between the current Bund and the constant-maturity Bund (hand-built examples)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import construction  # noqa: E402
import findings  # noqa: E402
import validation  # noqa: E402
import wording as w  # noqa: E402


def test_gap_stats_hand_example() -> None:
    days = pd.bdate_range("2026-01-01", periods=4)
    g = construction.gap_stats(pd.Series([-2.0, -4.0, -6.0, -8.0], index=days), recent_days=2)
    assert g["mean_bp"] == -5.0 and g["median_bp"] == -5.0
    assert g["recent_mean_bp"] == -7.0 and g["latest_bp"] == -8.0 and g["n_days"] == 4


def test_monthly_comparison_hand_example() -> None:
    daily = pd.Series([1.0, 1.2, 2.0, 2.2], index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03",
                                                                   "2020-02-04"]))
    monthly = pd.Series([1.0, 2.2], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    out = construction.monthly_comparison(daily, monthly, start="2010-01-01")
    # January: mean 1.1 vs 1.0 -> +10 bp; February: 2.1 vs 2.2 -> -10 bp
    assert out["n_months"] == 2
    assert out["mean_bp"] == pytest.approx(0.0)
    assert out["mean_abs_bp"] == pytest.approx(10.0)


def test_analyse_on_synthetic_frame() -> None:
    days = pd.bdate_range("2024-01-01", periods=300)
    current = pd.Series(2.50, index=days)
    cm = pd.Series(2.55, index=days)              # current Bund 5 bp below constant maturity
    oat = pd.Series(3.30, index=days)
    months = pd.date_range("2024-01-01", periods=15, freq="MS")
    long = validation.demo_long({"bund10_daily": current, "bund10_cm": cm, "oat10_daily": oat,
                                 "y10_FR": pd.Series(3.30, index=months), "y10_DE": pd.Series(2.50, index=months),
                                 "estr": pd.Series(2.0, index=days), "sofr": pd.Series(4.0, index=days)})
    out = construction.analyse(long)
    assert out["gap"]["mean_bp"] == pytest.approx(-5.0)
    assert out["spread_effect_mean_bp"] == pytest.approx(5.0)
    assert out["latest_spread_current_bp"] == pytest.approx(80.0)
    assert out["latest_spread_cm_bp"] == pytest.approx(75.0)
    assert not out["small"]
    assert out["monthly"]["bund_cm_vs_irs_de"]["mean_bp"] == pytest.approx(5.0)


@pytest.mark.parametrize("gap,side,effect", [(-7.0, "below", "wider"), (7.0, "above", "narrower")])
def test_construction_sentence_flips(gap: float, side: str, effect: str) -> None:
    s = w.construction_sentence(gap, gap, 160.0, 153.0, False, 3.0, 1000)
    assert f"{side} the Bundesbank" in s and f"reads {effect}" in s and "material" in s
    assert "small" in w.construction_sentence(gap / 10, gap / 10, 160.0, 159.3, True, 3.0, 1000)


def test_construction_lines_consistent_with_results() -> None:
    r = findings.load_results()
    c = r["construction"]
    lines = findings.construction_lines(r)
    assert len(lines) == 2
    word = "wider" if c["gap"]["mean_bp"] < 0 else "narrower"
    assert f"reads {word}" in lines[0]
    assert ("small" in lines[0]) == c["small"]
    assert findings.construction_lines({}) == []
