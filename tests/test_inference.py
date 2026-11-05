"""U2: bootstrap intervals, Holm adjustment, calibration verdicts, and the wording that uses them."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import findings
import inference
import stats_tools as st
import wording as w


@pytest.fixture(scope="module")
def r() -> dict:
    return findings.load_results()


def test_holm_by_hand() -> None:
    # sorted 0.005, 0.01, 0.03, 0.04 -> x4, x3, x2, x1 = 0.02, 0.03, 0.06, 0.04 -> monotone 0.02, 0.03, 0.06, 0.06
    assert list(st.holm([0.01, 0.04, 0.03, 0.005])) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert np.isnan(st.holm([np.nan, 0.01])[0]) and st.holm([np.nan, 0.01])[1] == pytest.approx(0.01)
    assert list(st.holm([0.9, 0.8])) == pytest.approx([1.0, 1.0])  # 0.8 x 2 caps at 1


def test_clopper_pearson_contains_the_share() -> None:
    lo, hi = st.clopper_pearson(90, 100)
    assert lo < 0.9 < hi and lo == pytest.approx(0.8238, abs=1e-3) and hi == pytest.approx(0.9510, abs=1e-3)
    assert st.clopper_pearson(0, 10)[0] == 0.0 and st.clopper_pearson(10, 10)[1] == 1.0


def test_block_bootstrap_ci_is_reproducible_and_covers_the_mean() -> None:
    x = np.random.default_rng(0).normal(1.0, 1.0, 400)
    a = st.block_bootstrap_ci(lambda i: float(x[i].mean()), len(x), 10, 300, 42)
    b = st.block_bootstrap_ci(lambda i: float(x[i].mean()), len(x), 10, 300, 42)
    assert a == b and a["lower"] < x.mean() < a["upper"]


def test_every_test_is_registered_with_holm_at_least_raw(r: dict) -> None:
    tests = r["tests"]["tests"]
    families = {t["family"] for t in tests}
    assert families >= {"F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"}
    assert sum(t["family"] == "F1" for t in tests) == 6
    for t in tests:
        if t["p"] is not None:
            assert t["p_holm"] >= t["p"] - 1e-12 and t["p_holm"] <= 1


def test_forecast_holm_matches_the_registry(r: dict) -> None:
    reg = {t["id"]: t["p_holm"] for t in r["tests"]["tests"]}
    for c, cur in r["forecast"]["currencies"].items():
        for m in cur["models"]:
            if m["model"] != "baseline":
                assert m["dm_turn_p_holm"] == pytest.approx(reg[f"dm_turn_{c}_{m['model']}"])


def test_significance_words_use_adjusted_p(r: dict) -> None:
    for c in ("USD", "EUR"):
        cur = r["forecast"]["currencies"][c]
        win = next(m for m in cur["models"] if m["model"] == cur["winner"])
        if cur["winner"] == "baseline":
            continue
        s = w.model_comparison_sentence(c, win["label"], win["pinball_turn"], 1.0, win["dm_turn_p_holm"], False,
                                        None, True)
        assert ("not statistically significant" in s) == (win["dm_turn_p_holm"] >= 0.05)
        assert "Holm-adjusted p" in s
    _, e = findings.calendar_answer(r)
    sig = [c for c in ("USD", "EUR") if findings.model_winner(r["forecast"], c)[1] is not None
           and findings.model_winner(r["forecast"], c)[1] < 0.05]
    assert ("significantly in neither" in e) == (not sig)


def test_too_close_to_call_rule(r: dict) -> None:
    for c, cs in r["bootstrap"]["credit_scarcity"].items():
        lo, hi = cs["difference"]["lower"], cs["difference"]["upper"]
        assert cs["too_close_to_call"] == (lo <= 0 <= hi)
        verdict = findings.collateral_verdict(r, c)
        assert (verdict == "too close to call") == cs["too_close_to_call"]
        s = w.credit_scarcity_ci_sentence(c, cs["point"]["difference"], lo, hi)
        assert ("too close to call" in s) == cs["too_close_to_call"]
    assert w.final_verdict("scarcity", True) == "too close to call"
    assert w.final_verdict("scarcity", False) == "scarcity"


@pytest.mark.parametrize("lo,hi,verdict", [(0.85, 0.95, "well calibrated"), (0.70, 0.88, "too narrow"),
                                           (0.92, 0.99, "too wide")])
def test_calibration_verdict_rule(lo: float, hi: float, verdict: str) -> None:
    got = "well calibrated" if lo <= 0.9 <= hi else "too narrow" if hi < 0.9 else "too wide"
    assert got == verdict
    s = w.calibration_sentence("USD", "State model", (lo + hi) / 2, lo, hi, verdict, 100)
    assert f"Verdict: {verdict}" in s


def test_calibration_on_real_results(r: dict) -> None:
    for c, cal in r["calibration"].items():
        lo, hi = cal["interval_lower"], cal["interval_upper"]
        expected = "well calibrated" if lo <= 0.9 <= hi else "too narrow" if hi < 0.9 else "too wide"
        assert cal["verdict"] == expected
        assert sum(cal["pit"]["observed"]) == pytest.approx(1.0)


def test_calibration_counts_on_a_toy_example() -> None:
    pred = pd.DataFrame({"actual": [0.0, 1.0, 2.0, 3.0], "day_type": "ordinary",
                         "m_q05": [-1.0] * 4, "m_q50": [0.5] * 4, "m_q90": [2.5] * 4, "m_q95": [2.9] * 4})
    cal = inference.calibration(pred, "m")
    assert cal["interval_coverage"] == 0.75                    # 3.0 is above q95
    assert cal["pit"]["observed"] == [0.0, 0.25, 0.5, 0.0, 0.25]


def test_ci_words_flip() -> None:
    assert w.excludes_zero(0.1, 0.5) and w.excludes_zero(-0.5, -0.1) and not w.excludes_zero(-0.1, 0.1)
    s = w.model_comparison_sentence("USD", "M", 1.0, 2.0, 0.2, False, {"lower": -1.0, "upper": -0.1}, True)
    assert "excludes zero" in s
    s = w.model_comparison_sentence("USD", "M", 1.0, 2.0, 0.2, False, {"lower": -1.0, "upper": 0.1}, True)
    assert "includes zero" in s
    assert "too close to call" in w.credit_scarcity_ci_sentence("IT", -2.0, -5.0, 1.0)
    assert "scarcity effects are larger" in w.credit_scarcity_ci_sentence("IT", -2.0, -5.0, -1.0)
    assert "credit effect is larger" in w.credit_scarcity_ci_sentence("IT", 2.0, 1.0, 5.0)
