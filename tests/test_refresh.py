"""The refresh's pipeline checks stop on a bad download before anything is written."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pipeline  # noqa: E402
import refresh_snapshots  # noqa: E402
from validation import demo_long  # noqa: E402


def _frame(n_estr: int, n_sofr: int, end: str = "2026-11-03") -> pd.DataFrame:
    return demo_long({"estr": pd.Series(2.0, index=pd.bdate_range(end=end, periods=n_estr)),
                      "sofr": pd.Series(4.0, index=pd.bdate_range(end=end, periods=n_sofr))})


def test_a_good_download_passes() -> None:
    refresh_snapshots.check_download(_frame(30, 30), _frame(29, 29, "2026-11-02"), pd.Timestamp("2026-11-04"))


def test_a_shorter_download_stops_the_refresh() -> None:
    with pytest.raises(pipeline.DataCheckError):
        refresh_snapshots.check_download(_frame(20, 30), _frame(29, 29), pd.Timestamp("2026-11-04"))


def test_a_missing_series_stops_the_refresh() -> None:
    previous = _frame(29, 29)
    new = previous[previous["series"] == "estr"]
    with pytest.raises(pipeline.DataCheckError):
        refresh_snapshots.check_download(new, previous, pd.Timestamp("2026-11-04"))


def test_stale_sofr_stops_the_refresh() -> None:
    with pytest.raises(pipeline.DataCheckError):
        refresh_snapshots.check_download(_frame(30, 30, "2026-10-01"), None, pd.Timestamp("2026-11-04"))
