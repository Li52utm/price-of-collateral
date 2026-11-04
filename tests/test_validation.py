"""Validation checks on hand-built examples: each status flips when the data does."""

from __future__ import annotations

import pandas as pd
import pytest

import validation as v
from validation import FAIL, PASS, WARN, demo_long


def _days(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="B")


def test_result_and_worst() -> None:
    assert v.worst([PASS, WARN]) == WARN and v.worst([PASS, FAIL, WARN]) == FAIL and v.worst([]) == PASS
    with pytest.raises(ValueError):
        v.result("x", "OK", "")


def test_coverage_share_counts_gaps() -> None:
    days = _days("2026-03-02", "2026-03-31")
    full = pd.Series(1.0, index=days)
    assert v.coverage_share(full, "USD") == (1.0, 0)
    holed = full.drop(days[5:9])
    share, gap = v.coverage_share(holed, "USD")
    assert share < 0.9 and gap == 4


def test_spot_values_pass_and_fail() -> None:
    long = demo_long({"estr": pd.Series([-0.549], index=pd.to_datetime(["2019-10-01"]))})
    checks = [("estr", "2019-10-01", -0.549, 0.0005)]
    assert v.check_spot_values(long, checks)["status"] == PASS
    wrong = demo_long({"estr": pd.Series([-0.40], index=pd.to_datetime(["2019-10-01"]))})
    assert v.check_spot_values(wrong, checks)["status"] == FAIL


def test_eonia_check_flags_a_broken_spread() -> None:
    days = _days("2019-10-02", "2019-12-31")
    estr = pd.Series(-0.55, index=days)
    good = demo_long({"estr": estr, "eonia": estr + 0.085})
    assert v.check_eonia_estr(good)["status"] == PASS
    bad = demo_long({"estr": estr, "eonia": estr + 0.20})
    assert v.check_eonia_estr(bad)["status"] == FAIL


def test_publication_lag_check_fails_on_future_dates() -> None:
    days = _days("2026-10-01", "2026-11-03")
    long = demo_long({"estr": pd.Series(1.0, index=days)})
    assert v.check_publication_lags(long, pd.Timestamp("2026-11-04"))["status"] == PASS
    assert v.check_publication_lags(long, pd.Timestamp("2026-11-01"))["status"] == FAIL
    assert v.check_publication_lags(long, pd.Timestamp("2026-12-31"))["status"] == WARN


def test_committed_validation_report_has_no_failures() -> None:
    import json
    from pathlib import Path

    rep = json.loads((Path(__file__).resolve().parent.parent / "results" / "data_validation.json").read_text())
    assert rep["counts"][FAIL] == 0 and len(rep["checks"]) >= 8
