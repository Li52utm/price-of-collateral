"""U6: property-based no-look-ahead tests (hypothesis).

Randomly perturb (or delete) every observation dated AFTER a cut-off t and check that every model input
for a day at or before t is unchanged. The ECB maintenance-period calendar (`min_reserves`) is excluded
from the perturbation: the ECB publishes that calendar in advance, so the project treats it as known.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as hs

import data
import features as F
import france_daily as FD

LONG = data.load_long()
CALENDAR_KNOWN_IN_ADVANCE = {"min_reserves"}
CUTOFFS = pd.bdate_range("2021-01-04", "2026-06-30")
SETTINGS = settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def perturb_after(long: pd.DataFrame, t: pd.Timestamp, seed: int, mode: str) -> pd.DataFrame:
    """Scale, shift or delete every observation dated after t (except the calendar known in advance)."""
    rng = np.random.default_rng(seed)
    out = long.copy()
    after = (out["date"] > t) & ~out["series"].isin(CALENDAR_KNOWN_IN_ADVANCE)
    if mode == "delete":
        return out[~after].reset_index(drop=True)
    noise = rng.normal(0, 5, after.sum()) if mode == "shift" else rng.uniform(0.2, 3.0, after.sum())
    out.loc[after, "value"] = out.loc[after, "value"] + noise if mode == "shift" else out.loc[after, "value"] * noise
    return out


@SETTINGS
@given(i=hs.integers(0, len(CUTOFFS) - 1), seed=hs.integers(0, 10_000),
       mode=hs.sampled_from(["shift", "scale", "delete"]), currency=hs.sampled_from(["USD", "EUR"]))
def test_forecast_inputs_ignore_data_after_t(i: int, seed: int, mode: str, currency: str) -> None:
    t = CUTOFFS[i]
    days = data.business_days(currency, t - pd.Timedelta(days=120), t)
    before = F.build(currency, days, LONG)
    after = F.build(currency, days, perturb_after(LONG, t, seed, mode))
    cols = [c for c in before.columns if c != "day_type"]
    pd.testing.assert_frame_equal(before[cols], after[cols])


@SETTINGS
@given(i=hs.integers(0, len(CUTOFFS) - 1), seed=hs.integers(0, 10_000), mode=hs.sampled_from(["shift", "delete"]))
def test_daily_france_inputs_ignore_data_after_t(i: int, seed: int, mode: str) -> None:
    t = CUTOFFS[i]
    before = FD.daily_frame(LONG).loc[:t]
    after = FD.daily_frame(perturb_after(LONG, t, seed, mode)).loc[:t]
    pd.testing.assert_frame_equal(before, after)


@settings(max_examples=200, deadline=None)
@given(values=hs.lists(hs.floats(-10, 10, allow_nan=False), min_size=5, max_size=60),
       lag=hs.integers(0, 5), cut=hs.integers(0, 59), bump=hs.floats(-100, 100, allow_nan=False))
def test_point_in_time_never_sees_the_future(values: list, lag: int, cut: int, bump: float) -> None:
    obs = pd.bdate_range("2025-01-06", periods=len(values))
    s = pd.Series(values, index=obs)
    t = obs[min(cut, len(obs) - 1)]
    query = pd.bdate_range(obs[0], t)
    s2 = s.copy()
    s2[s2.index > t] += bump + 1.0
    a = data.point_in_time(s, lag, query, "EUR")
    b = data.point_in_time(s2, lag, query, "EUR")
    pd.testing.assert_series_equal(a, b)
    # And nothing is known before its publication lag has passed.
    avail = data.available_dates(obs, lag, "EUR")
    first_known = a.first_valid_index()
    if first_known is not None:
        assert first_known >= avail[0]


# --------------------------------------------------------------------------- #
# Desk upgrade: new model inputs
# --------------------------------------------------------------------------- #
@SETTINGS
@given(i=hs.integers(0, len(CUTOFFS) - 1), seed=hs.integers(0, 10_000), mode=hs.sampled_from(["shift", "delete"]),
       currency=hs.sampled_from(["USD", "EUR"]))
def test_treasury_cash_rows_ignore_data_after_t(i: int, seed: int, mode: str, currency: str) -> None:
    """D2: every row of the weekly data set dated at or before t is unchanged by data after t."""
    import autonomous as A
    t = CUTOFFS[i]
    before = A.weekly_dataset(currency, LONG).loc[:t]
    after = A.weekly_dataset(currency, perturb_after(LONG, t, seed, mode)).loc[:t]
    pd.testing.assert_frame_equal(before, after)


@SETTINGS
@given(i=hs.integers(0, len(CUTOFFS) - 1), seed=hs.integers(0, 10_000), mode=hs.sampled_from(["shift", "delete"]))
def test_runway_liquidity_published_by_t_ignores_later_data(i: int, seed: int, mode: str) -> None:
    """D1: the liquidity history the runway sees on day t is the same whatever is published after t."""
    import runway as R
    t = CUTOFFS[i]
    def seen(long: pd.DataFrame) -> pd.Series:
        return R.published_by(data.get("eur_liquidity", long).dropna(), data.DERIVED_LAGS["eur_liquidity"], t)
    pd.testing.assert_series_equal(seen(LONG), seen(perturb_after(LONG, t, seed, mode)))
