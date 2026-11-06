"""D2: Treasury cash and overnight funding (hand-built examples, offline) and its sentences."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import autonomous as A
import findings
import wording as w


def test_weekly_spread_means_days_after_previous_week_end() -> None:
    days = pd.bdate_range("2026-01-05", "2026-01-16")
    y = pd.Series(np.arange(len(days), dtype=float), index=days)
    weeks = pd.DatetimeIndex(["2026-01-02", "2026-01-09", "2026-01-16"])
    s = A.weekly_spread(y, weeks)
    assert s.loc["2026-01-09"] == 2.0 and s.loc["2026-01-16"] == 7.0
    assert A.weekly_spread(y.iloc[:2], weeks, min_days=3).empty


def _frame(n: int = 200, b_cash: float = 0.5, b_liq: float = -1.0, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cash, liq = rng.normal(0, 1, n), rng.normal(0, 1, n)
    return pd.DataFrame({"d_cash": cash, "d_liq": liq,
                         "d_spread": 0.1 + b_cash * cash + b_liq * liq + rng.normal(0, 0.1, n)},
                        index=pd.date_range("2019-01-04", periods=n, freq="7D"))


def test_ols_and_bootstrap_recover_coefficients() -> None:
    f = _frame()
    res = A.ols(f)
    assert res["coef"]["cash"] == pytest.approx(0.5, abs=0.03) and res["coef"]["liq"] == pytest.approx(-1.0, abs=0.03)
    assert res["p"]["cash"] < 0.001
    ci = A.bootstrap_ci(f, n_boot=200)
    assert ci["cash"][0] < 0.5 < ci["cash"][1] and ci["liq"][1] < 0
    np.testing.assert_allclose(A.coef_vector(f), [res["coef"]["const"], 0.5, -1.0], atol=0.05)


def test_out_of_sample_against_no_change() -> None:
    f = _frame()
    good = A.out_of_sample(f.iloc[:100], f.iloc[100:])
    assert good["r2_oos"] > 0.9 and good["rmse_model"] < good["rmse_no_change"]
    noise = _frame(b_cash=0.0, b_liq=0.0, seed=1)
    noise["d_spread"] -= 0.1
    assert A.out_of_sample(f.iloc[:100], noise.iloc[100:])["r2_oos"] < 0


def test_verdict_rule() -> None:
    assert A.verdict([0.1, 0.3], 0.1) == "matters"
    assert A.verdict([-0.3, -0.1], -0.1) == "some evidence"
    assert A.verdict([-0.1, 0.3], 0.1) == "some evidence"
    assert A.verdict([-0.1, 0.3], -0.1) == "no clear effect"


@pytest.mark.parametrize("coef,word", [(0.5, "rises when Treasury cash rises"),
                                       (-0.5, "falls when Treasury cash rises")])
def test_treasury_cash_sentence_flips(coef: float, word: str) -> None:
    s = w.treasury_cash_sentence("USD", coef, coef - 0.2, coef + 0.2, 0.01, 0.1, -1.0, -1.5, -0.5, "matters")
    assert word in s and "excludes zero" in s and "beats a no-change" in s and "matter for overnight" in s
    s = w.treasury_cash_sentence("EUR", coef, -1, 1, 0.5, -0.1, 0.0, -1, 1, "no clear effect")
    assert "includes zero" in s and "does not beat" in s and "no clear effect" in s and "not statistically" in s


def test_treasury_cash_answer() -> None:
    both = w.treasury_cash_answer("matters", "matters")
    assert both == "Treasury cash swings matter for overnight funding in both currencies."
    assert "do not clearly matter for dollar" in w.treasury_cash_answer("matters", "no clear effect")


def test_treasury_cash_lines_consistent_with_results() -> None:
    r = findings.load_results()
    a = r["autonomous"]
    lines = findings.treasury_cash_lines(r)
    for i, cur in enumerate(("EUR", "USD")):
        v = a["currencies"][cur]
        assert v["verdict"] == A.verdict(v["full"]["ci"]["cash"], v["oos"]["r2_oos"])
        assert ("rises when" in lines[i]) == (v["full"]["coef"]["cash"] > 0)
        assert ("does not beat" in lines[i]) == (v["oos"]["r2_oos"] <= 0)
    assert findings.treasury_cash_lines({}) == []


def test_policy_change_weeks() -> None:
    long = pd.concat([pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-14"]), "series": "dfr",
                                    "value": [2.0, 2.25]})])
    weeks = pd.DatetimeIndex(["2026-01-09", "2026-01-16", "2026-01-23"])
    assert list(A.policy_change_weeks("EUR", weeks, long)) == [pd.Timestamp("2026-01-16")]
