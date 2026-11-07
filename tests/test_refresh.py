"""The refresh's pipeline checks stop on a bad download before anything is written."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import refresh_snapshots  # noqa: E402

import pipeline  # noqa: E402
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


# --------------------------------------------------------------------------- #
# Saturday 7 Nov 2026: FRED's IORB already ran to Monday 9 Nov (docs/METHODOLOGY.md, corrections log)
# --------------------------------------------------------------------------- #
SATURDAY_FETCH = pd.Timestamp("2026-11-07 15:06:49")


def _saturday_download() -> pd.DataFrame:
    """The download as seen on 7 Nov 2026: IORB (7-day series) to Mon 9 Nov, the target range to Sat 7 Nov,
    €STR and SOFR to Fri 6 Nov."""
    return demo_long({"iorb": pd.Series(3.90, index=pd.date_range("2026-11-04", "2026-11-09")),
                      "fed_upper": pd.Series(4.00, index=pd.date_range("2026-11-02", "2026-11-07")),
                      "estr": pd.Series(1.93, index=pd.bdate_range("2026-10-01", "2026-11-06")),
                      "sofr": pd.Series(3.92, index=pd.bdate_range("2026-10-01", "2026-11-06"))})


def test_saturday_iorb_reproduces_the_publication_lag_failure() -> None:
    import validation
    rep = validation.check_publication_lags(_saturday_download(), SATURDAY_FETCH)
    assert rep["status"] == validation.FAIL
    assert "iorb (2 observations dated 2026-11-08 to 2026-11-09" in rep["detail"]
    assert "2026-11-07" in rep["detail"]


def test_announced_rates_are_trimmed_to_the_fetch_date_and_validation_passes() -> None:
    import validation
    trimmed, notes = pipeline.trim_announced(_saturday_download(), SATURDAY_FETCH)
    assert notes == ["iorb: 2 rows dated 2026-11-08 to 2026-11-09 (after the fetch date 2026-11-07)"]
    iorb = trimmed[trimmed["series"] == "iorb"]
    assert pd.to_datetime(iorb["date"]).max() == pd.Timestamp("2026-11-07")
    assert len(trimmed) == len(_saturday_download()) - 2
    assert validation.check_publication_lags(trimmed, SATURDAY_FETCH)["status"] == validation.PASS


def test_a_future_dated_market_rate_is_not_trimmed_and_still_fails() -> None:
    import validation
    long = pd.concat([_saturday_download(),
                      demo_long({"sofr": pd.Series(3.95, index=[pd.Timestamp("2026-11-09")])})], ignore_index=True)
    trimmed, notes = pipeline.trim_announced(long, SATURDAY_FETCH)
    assert not any(n.startswith("sofr") for n in notes)
    rep = validation.check_publication_lags(trimmed, SATURDAY_FETCH)
    assert rep["status"] == validation.FAIL and "sofr (1 observations dated 2026-11-09" in rep["detail"]


def test_a_failed_validation_prints_the_full_detail_before_stopping() -> None:
    import validation
    rep = {"checks": [validation.result("Ranges", validation.PASS, "fine"),
                      validation.result("Publication lags", validation.FAIL, "iorb (2 observations dated ...)")],
           "counts": {validation.PASS: 1, validation.WARN: 0, validation.FAIL: 1}}
    lines: list[str] = []
    with pytest.raises(validation.ValidationFailed, match="Publication lags"):
        refresh_snapshots.report_validation(rep, log=lines.append)
    assert "   FAIL Publication lags" in lines
    assert "   --- FAIL Publication lags: iorb (2 observations dated ...)" in lines
    assert not any("fine" in line for line in lines)  # PASS details stay short


def test_every_announced_rate_is_a_registered_zero_lag_series() -> None:
    import sources
    for name in sources.ANNOUNCED_IN_ADVANCE:
        assert sources.BY_NAME[name].lag_bd == 0, name


def test_a_registered_series_missing_from_the_download_stops_the_refresh() -> None:
    import sources
    full = demo_long({s.name: pd.Series(1.0, index=[pd.Timestamp("2026-11-06")]) for s in sources.ALL_SERIES})
    lines: list[str] = []
    refresh_snapshots.check_registered(full, log=lines.append)
    assert lines[0].startswith(f"   {len(sources.ALL_SERIES)} of {len(sources.ALL_SERIES)} registered")
    with pytest.raises(pipeline.DataCheckError, match="oat10_daily"):
        refresh_snapshots.check_registered(full[full["series"] != "oat10_daily"], log=lines.append)
