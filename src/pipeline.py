"""Checks for the scheduled data refresh (scripts/refresh_snapshots.py).

Every download is checked before anything is written. If any check fails the
refresh stops with DataCheckError, no snapshot is changed, and the GitHub
Action fails without committing. Pure functions: tests/test_framework.py.
"""

from __future__ import annotations

import pandas as pd

import sources


class DataCheckError(RuntimeError):
    """A download is empty, shorter than before, or otherwise not plausible."""


def check_growth(name: str, new: pd.DataFrame | pd.Series | None,
                 previous: pd.DataFrame | pd.Series | None) -> None:
    """A fresh download must be non-empty, not shorter than, and not end before the committed snapshot."""
    if new is None or len(new) == 0:
        raise DataCheckError(f"{name}: the download is empty")
    if previous is None or len(previous) == 0:
        return
    if len(new) < len(previous):
        raise DataCheckError(f"{name}: {len(new)} rows, fewer than the previous snapshot's {len(previous)}")
    if new.index[-1] < previous.index[-1]:
        raise DataCheckError(f"{name}: last date {new.index[-1].date()} is before the previous "
                             f"snapshot's {previous.index[-1].date()}")


def check_columns(name: str, new: pd.DataFrame, required: list[str] | tuple[str, ...]) -> None:
    """Every required column is present and has at least one value."""
    missing = [c for c in required if c not in new.columns]
    if missing:
        raise DataCheckError(f"{name}: missing columns {missing}")
    empty = [c for c in required if new[c].dropna().empty]
    if empty:
        raise DataCheckError(f"{name}: columns with no data {empty}")


def check_recent(name: str, series: pd.Series, as_of: pd.Timestamp, max_age_days: int) -> None:
    """The last valid observation is no older than `max_age_days` calendar days before `as_of`."""
    last = series.dropna().index.max()
    if pd.isna(last) or (as_of - last).days > max_age_days:
        raise DataCheckError(f"{name}: last observation {last} is more than {max_age_days} days before {as_of.date()}")


def trim_announced(long: pd.DataFrame, fetched: pd.Timestamp,
                   announced: frozenset[str] = sources.ANNOUNCED_IN_ADVANCE) -> tuple[pd.DataFrame, list[str]]:
    """Drop observations dated after the fetch date, for announced-in-advance policy rates ONLY.

    A source can publish an administered rate ahead of the day it applies to (FRED's IORB on a Saturday
    already runs to the next Monday). The value is public, but the snapshot records what was observed up
    to the fetch date, so those rows are dropped here and listed for the log. Every other series is left
    untouched, so a future-dated market rate still reaches validation and fails it.
    Returns (trimmed long frame, one "name: n rows dated d1 to d2" line per trimmed series).
    """
    cutoff = fetched.normalize()
    dates = pd.to_datetime(long["date"])
    drop = long["series"].isin(announced) & (dates > cutoff)
    notes = [f"{name}: {len(part)} rows dated {part['date'].min().date()} to {part['date'].max().date()} "
             f"(after the fetch date {cutoff.date()})"
             for name, part in long.assign(date=dates)[drop].groupby("series")]
    return long[~drop].reset_index(drop=True), notes
