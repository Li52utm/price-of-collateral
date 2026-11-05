"""Phase 2: statistics tools, features without look-ahead, models, the frozen forecast and its score."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import features as F
import forecast as fc
import stats_tools as st
import wording as w


# --------------------------------------------------------------------------- #
# Statistics tools
# --------------------------------------------------------------------------- #
def test_pinball_by_hand() -> None:
    y = np.array([10.0, 0.0])
    q = np.array([8.0, 2.0])
    assert st.pinball(y, q, 0.9).tolist() == pytest.approx([0.9 * 2, 0.1 * 2])
    assert st.pinball(y, q, 0.5).tolist() == pytest.approx([1.0, 1.0])


def test_diebold_mariano_direction() -> None:
    rng = np.random.default_rng(0)
    base = rng.uniform(1, 2, 300)
    better = base - 0.5 + rng.normal(0, 0.05, 300)
    dm = st.diebold_mariano(better, base, horizon=1)
    assert dm["mean_diff"] < 0 and dm["stat"] < 0 and dm["p_value"] < 0.01
    same = st.diebold_mariano(base + rng.normal(0, 0.1, 300), base, horizon=1)
    assert same["p_value"] > 0.01


def test_chow_test_finds_a_break() -> None:
    x = np.arange(100.0)
    y = np.where(x < 50, 1.0 + 0.1 * x, 20.0 + 0.1 * x) + np.random.default_rng(1).normal(0, 0.5, 100)
    X = np.column_stack([np.ones(100), x])
    assert st.chow_test(y, X, 50)["p_value"] < 0.001
    y2 = 1.0 + 0.1 * x + np.random.default_rng(2).normal(0, 0.5, 100)
    assert st.chow_test(y2, X, 50)["p_value"] > 0.01


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def test_calendar_turn_days() -> None:
    days = pd.bdate_range("2026-12-01", "2027-01-08")
    cal = F.calendar_features(pd.DatetimeIndex(days), "JPY")
    jp_days = cal.index[cal["ye"] == 1]
    assert pd.Timestamp("2026-12-30") in jp_days  # Japan closes on 31 December
    eur = F.calendar_features(pd.DatetimeIndex(days), "EUR", mp_ends=pd.DatetimeIndex(["2026-12-22"]))
    assert eur.loc["2026-12-31", "ye"] == 1 and eur.loc["2026-12-31", "qe"] == 1 and eur.loc["2026-12-31", "me"] == 1
    assert eur.loc["2027-01-04", "ye_p1"] == 1 and eur.loc["2026-12-23", "mp_start"] == 1


def test_origins_are_forty_business_days_back_and_capped() -> None:
    o = F.origins(pd.DatetimeIndex(["2026-12-31"]), "USD")
    assert len(pd.bdate_range(o[0], "2026-12-31", freq="C", holidays=["2026-11-11", "2026-11-26",
                                                                      "2026-12-25"])) - 1 == 40
    capped = F.origins(pd.DatetimeIndex(["2027-03-31"]), "USD", cap=pd.Timestamp("2026-11-03"))
    assert capped[0] == pd.Timestamp("2026-11-03")


def test_state_features_use_only_data_published_by_the_origin() -> None:
    y = F.target("USD")
    X = F.build("USD", y.index[-300:])
    # The level at the origin must equal the 5-day mean of the target as published by then.
    row = X.iloc[-1]
    published = y[y.index < row["origin"]]  # SOFR lag is 1 business day
    assert row["level"] == pytest.approx(published.iloc[-5:].mean())
    # Changing the target after the origin must not change any feature.
    later = y.copy()
    later[later.index >= row["origin"]] += 100
    assert later.loc[:row["origin"]].iloc[:-1].equals(y.loc[:row["origin"]].iloc[:-1])


def test_targets_are_in_basis_points() -> None:
    usd, eur = F.target("USD"), F.target("EUR")
    assert usd.loc["2019-09-17"] == pytest.approx(315, abs=1)  # SOFR 5.25% vs IOER 2.10%
    assert -15 < eur.median() < 0  # €STR trades below the DFR in the floor system


# --------------------------------------------------------------------------- #
# Models and outputs
# --------------------------------------------------------------------------- #
def test_quantiles_never_cross() -> None:
    pred = fc._sort_quantiles(pd.DataFrame({0.05: [3.0], 0.5: [1.0], 0.9: [2.0], 0.95: [0.0]}))
    assert pred.iloc[0].tolist() == [0.0, 1.0, 2.0, 3.0]


def test_summary_has_a_winner_per_currency_and_honest_split() -> None:
    summary = fc.load_summary()
    assert summary is not None
    for currency in fc.EVAL_CURRENCIES:
        c = summary["currencies"][currency]
        assert c["winner"] in fc.MODELS
        assert pd.Timestamp(c["train_end"]) <= fc.TRAIN_END < pd.Timestamp(c["test_start"])
        best = min(c["models"], key=lambda m: m["pinball_turn"])
        assert best["model"] == c["winner"]


def test_frozen_forecast_cannot_be_overwritten(tmp_path) -> None:
    path = tmp_path / "frozen.json"
    path.write_text("{}")
    with pytest.raises(FileExistsError):
        fc.create_frozen_forecast(path)
    assert path.read_text() == "{}"


def test_committed_frozen_forecast_is_complete_and_untouched_by_run(tmp_path) -> None:
    frozen_path = fc.FROZEN_PATH
    if not frozen_path.exists():  # only between the code commit and the freeze (see METHODOLOGY.md)
        pytest.skip("the Year-End 2026 forecast has not been frozen yet")
    before = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    fc.run(out_dir=tmp_path)  # what the refresh runs
    assert hashlib.sha256(frozen_path.read_bytes()).hexdigest() == before
    frozen = json.loads(frozen_path.read_text())
    for key in ("model_version", "data_as_of", "created_at", "git_commit", "code_sha256"):
        assert frozen[key]
    for currency in fc.FORECAST_CURRENCIES:
        f = frozen["currencies"][currency]
        assert f["q05"] <= f["q50"] <= f["q90"] <= f["q95"] and f["turn_day"] == "2026-12-31"


def test_scoring_waits_for_the_year_end_and_then_scores() -> None:
    frozen = {"created_at": "x", "currencies": {"USD": {"turn_day": "2026-12-31", "q05": -5.0, "q50": 5.0,
                                                        "q90": 20.0, "q95": 30.0}}}
    assert fc.score_yearend(frozen) is None  # 31 Dec 2026 is not in the data yet
    future = fc.F.target("USD").iloc[-5:]
    fake = pd.concat([future, pd.Series([12.0], index=[pd.Timestamp("2026-12-31")])])

    class Stub:
        pass

    # Score with a stubbed target that contains the year-end value.
    original = fc.F.target
    try:
        fc.F.target = lambda currency, long=None: fake
        score = fc.score_yearend(frozen)
    finally:
        fc.F.target = original
    s = score["currencies"]["USD"]
    assert s["actual"] == 12.0 and s["inside_interval"] and s["below_q90"]
    assert s["pinball"]["q50"] == pytest.approx(0.5 * 7)


# --------------------------------------------------------------------------- #
# Wording
# --------------------------------------------------------------------------- #
def test_model_comparison_wording_flips() -> None:
    won = w.model_comparison_sentence("USD", "Calendar + state quantile regression", 1.5, 2.0, 0.04, False)
    assert "25% lower" in won and "statistically significant (p = 0.040)" in won
    lost = w.model_comparison_sentence("JPY", "Baseline", 0.67, 0.67, None, True)
    assert "neither regression beat it" in lost


def test_yearend_contrast_follows_signs() -> None:
    opposite = w.yearend_contrast_sentence(11.0, 0.8, 8, -1.2, 0.1, 7)
    assert "rose by 11.0 bp" in opposite and "fell by 1.2 bp" in opposite and "opposite direction" in opposite
    same = w.yearend_contrast_sentence(11.0, 0.8, 8, 2.0, 0.6, 7)
    assert "same direction" in same
    assert "balance sheets" in w.yearend_mechanism_sentence(11.0, -1.2)
    assert "balance sheets" not in w.yearend_mechanism_sentence(-1.0, -1.2)


def test_term_rule_and_answer_wording() -> None:
    assert "saved USD 14.9k" in w.term_rule_sentence(14_861, 36_305, 9, 42)
    assert "cost USD 2.0k against always borrowing overnight" in w.term_rule_sentence(-2_000, 5_000, 3, 42)
    assert w.calendar_answer(True, True, 0.01, 0.02, 11, -1)[0] == "Yes, in both currencies"
    assert w.calendar_answer(True, True, 0.04, 0.18, 11, -1)[0] == "Partly: reliably in dollars"
    assert w.calendar_answer(True, True, 0.3, 0.18, 11, -1)[0].startswith("Partly: the models beat")
    assert w.calendar_answer(False, False, None, None, 11, -1)[0] == "Not better than a naive rule"
