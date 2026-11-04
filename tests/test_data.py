"""Data layer: point-in-time availability, calendars, derived series and the committed snapshot."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import data
import sources
import validation


def test_point_in_time_respects_the_lag() -> None:
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))  # Mon-Wed
    index = pd.date_range("2026-01-05", "2026-01-09", freq="B")
    out = data.point_in_time(s, 1, index, "USD")
    # Monday's value is first usable on Tuesday, Tuesday's on Wednesday, ...
    assert np.isnan(out.iloc[0])
    assert out.tolist()[1:] == [1.0, 2.0, 3.0, 3.0]
    same_day = data.point_in_time(s, 0, index, "USD")
    assert same_day.tolist() == [1.0, 2.0, 3.0, 3.0, 3.0]


def test_point_in_time_skips_holidays_and_weekends() -> None:
    # A value dated Thursday 24 Dec 2026 with a one-day lag: 25 Dec is a TARGET holiday, then a weekend,
    # and 28 Dec is the next business day.
    s = pd.Series([5.0], index=pd.to_datetime(["2026-12-24"]))
    index = pd.date_range("2026-12-24", "2026-12-29", freq="D")
    out = data.point_in_time(s, 1, index, "EUR")
    assert out.loc[:"2026-12-27"].isna().all() and out.loc["2026-12-28"] == 5.0


def test_monthly_values_are_not_usable_before_their_lag() -> None:
    monthly = pd.Series([3.0], index=pd.to_datetime(["2026-09-01"]))  # September average
    index = pd.date_range("2026-09-01", "2026-11-30", freq="B")
    out = data.point_in_time(monthly, sources.lag("y10_FR"), index, "EUR")
    first = out.first_valid_index()
    assert first > pd.Timestamp("2026-10-01")  # never inside the month it averages


def test_calendars() -> None:
    eur = data.business_days("EUR", "2026-12-23", "2027-01-04")
    assert pd.Timestamp("2026-12-25") not in eur and pd.Timestamp("2027-01-01") not in eur
    usd = data.business_days("USD", "2026-11-25", "2026-11-27")
    assert pd.Timestamp("2026-11-26") not in usd  # Thanksgiving


def test_every_registered_series_has_a_lag() -> None:
    for spec in sources.ALL_SERIES:
        assert spec.lag_bd >= 0 and spec.freq in ("daily", "weekly", "monthly", "maintenance_period")
    assert sources.lag("mmsr_rate_le_KS_IT") == sources.MMSR_LAG_BD


def test_boj_policy_rule() -> None:
    loan = pd.Series([0.3, 0.5, 0.75], index=pd.to_datetime(["2008-12-19", "2024-08-01", "2025-01-27"]))
    long = validation.demo_long({"boj_loan_rate": loan,
                                 "estr": pd.Series([1.0], index=pd.to_datetime(["2025-03-01"]))})
    policy = data.boj_policy(long)
    assert policy.loc["2016-06-01"] == -0.10
    assert policy.loc["2024-04-01"] == 0.10
    assert policy.loc["2024-09-01"] == pytest.approx(0.25)
    assert policy.loc["2025-02-01"] == pytest.approx(0.50)


def test_snapshot_loads_and_has_the_core_series() -> None:
    long = data.load_long()
    names = set(long["series"])
    for name in ("estr", "dfr", "sofr", "usd_ior", "tona", "boj_policy", "y10_FR", "mmsr_rate_le_KS_IT"):
        assert name in names or name in data.DERIVED
    manifest = data.load_manifest()
    assert pd.Timestamp(manifest["as_of"]) == data.as_of(long)
    assert manifest["series"]["estr"]["lag_bd"] == 1
    assert len(data.load_settlements()) > 1000


def test_maintenance_period_ends_are_tuesdays_or_mondays_before_a_wednesday_start() -> None:
    ends = data.maintenance_period_ends()
    recent = ends[ends >= "2024-01-01"]
    assert len(recent) >= 10
    assert (recent.day_of_week <= 1).mean() > 0.8  # periods start on Wednesdays (Tuesday after holidays)
