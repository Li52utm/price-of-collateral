"""Data layer: reads ONLY the committed snapshots in results/snapshots/ (never downloads).

- `results/snapshots/series.csv`: every series in long format (date, series, value), written by
  scripts/refresh_snapshots.py. Values are as published; nothing is forward-filled in the file.
- `results/snapshots/settlements.csv`: US Treasury auction issue (settlement) dates and sizes.
- `results/snapshots/manifest.json`: as-of date, fetch time, and per-series coverage and lag.

Point in time: `point_in_time(series, lag_bd, index)` returns, for each day t of `index`, the latest
value whose observation date plus its publication lag (business days of the series' own calendar)
is on or before t. Every model input goes through it, so no model can see a value before it was
published.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import AbstractHolidayCalendar, EasterMonday, GoodFriday, Holiday, USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

import sources

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "results" / "snapshots"
SERIES_PATH = SNAPSHOT_DIR / "series.csv"
SETTLEMENTS_PATH = SNAPSHOT_DIR / "settlements.csv"
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #
class TargetCalendar(AbstractHolidayCalendar):
    """TARGET2 closing days (the euro settlement calendar)."""
    rules = [Holiday("New Year", month=1, day=1), GoodFriday, EasterMonday,
             Holiday("Labour Day", month=5, day=1), Holiday("Christmas", month=12, day=25),
             Holiday("Boxing Day", month=12, day=26)]


class JapanCalendar(AbstractHolidayCalendar):
    """Japanese bank holidays: the 31 Dec - 3 Jan closure and the fixed-date national holidays.

    Moving holidays (Coming of Age Day, Marine Day, Respect for the Aged Day, Sports Day, equinoxes)
    are not modelled; Japanese publication lags are set conservatively to absorb them.
    """
    rules = [Holiday("New Year 1", month=1, day=1), Holiday("New Year 2", month=1, day=2),
             Holiday("New Year 3", month=1, day=3), Holiday("Foundation Day", month=2, day=11),
             Holiday("Emperor's Birthday", month=2, day=23, start_date="2020-01-01"),
             Holiday("Showa Day", month=4, day=29), Holiday("Constitution Day", month=5, day=3),
             Holiday("Greenery Day", month=5, day=4), Holiday("Children's Day", month=5, day=5),
             Holiday("Culture Day", month=11, day=3), Holiday("Labour Thanksgiving", month=11, day=23),
             Holiday("Year end", month=12, day=31)]


CALENDARS = {"EUR": TargetCalendar(), "USD": USFederalHolidayCalendar(), "JPY": JapanCalendar()}
CURRENCY_OF_SOURCE = {"ecb": "EUR", "bbk": "EUR", "fred": "USD", "nyfed": "USD", "ofr": "USD",
                      "fiscal": "USD", "boj": "JPY"}


@lru_cache(maxsize=None)
def bday(currency: str) -> CustomBusinessDay:
    """Business-day offset for a currency's calendar."""
    return CustomBusinessDay(calendar=CALENDARS[currency])


def business_days(currency: str, start, end) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq=bday(currency))


def currency_of(name: str) -> str:
    if name.startswith(("mmsr_", "pspp_", "eur_")):
        return "EUR"
    if name.startswith(("boj_",)) or name in ("tona",):
        return "JPY"
    if name.startswith("usd_"):
        return "USD"
    return CURRENCY_OF_SOURCE[sources.BY_NAME[name].source]


# --------------------------------------------------------------------------- #
# Reading the snapshot
# --------------------------------------------------------------------------- #
class SnapshotMissing(FileNotFoundError):
    """The committed snapshot is not there (run scripts/refresh_snapshots.py)."""


@lru_cache(maxsize=4)
def _read_long(path: str, stamp: float) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def load_long(path: Path = SERIES_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        raise SnapshotMissing(f"{path} not found: run scripts/refresh_snapshots.py")
    return _read_long(str(path), Path(path).stat().st_mtime)


def raw(name: str, long: pd.DataFrame | None = None) -> pd.Series:
    """One series exactly as stored (observation dates, no filling)."""
    long = load_long() if long is None else long
    sub = long[long["series"] == name]
    s = pd.Series(sub["value"].to_numpy(dtype=float), index=pd.DatetimeIndex(sub["date"]), name=name)
    return s.sort_index()


def get(name: str, long: pd.DataFrame | None = None) -> pd.Series:
    """A stored or derived series by name (see DERIVED)."""
    if name in DERIVED:
        return DERIVED[name](long)
    return raw(name, long)


def load_settlements(path: Path = SETTLEMENTS_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        raise SnapshotMissing(f"{path} not found")
    return pd.read_csv(path, parse_dates=["date"])


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    if not Path(path).exists():
        raise SnapshotMissing(f"{path} not found")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def as_of(long: pd.DataFrame | None = None) -> pd.Timestamp:
    """The snapshot's as-of date: the last day on which both €STR and SOFR are published."""
    long = load_long() if long is None else long
    return min(raw("estr", long).index.max(), raw("sofr", long).index.max())


# --------------------------------------------------------------------------- #
# Point in time
# --------------------------------------------------------------------------- #
def available_dates(obs_dates: pd.DatetimeIndex, lag_bd: int, currency: str) -> pd.DatetimeIndex:
    """The first day each observation may be used: observation date + lag business days.

    An observation dated on a non-business day (e.g. a monthly series dated on the 1st, or a
    weekly series dated on a holiday) is first rolled forward to the next business day.
    """
    holidays = np.asarray(bday(currency).holidays, dtype="datetime64[D]")
    days = np.asarray(pd.DatetimeIndex(obs_dates).values, dtype="datetime64[D]")
    rolled = np.busday_offset(days, 0, roll="forward", holidays=holidays)
    return pd.DatetimeIndex(np.busday_offset(rolled, lag_bd, roll="forward", holidays=holidays))


def point_in_time(s: pd.Series, lag_bd: int, index: pd.DatetimeIndex, currency: str = "EUR",
                  available: pd.DatetimeIndex | None = None) -> pd.Series:
    """For each t in `index`, the latest value of `s` available on t (NaN before the first)."""
    s = s.dropna().sort_index()
    if s.empty:
        return pd.Series(np.nan, index=index, name=s.name)
    avail = available if available is not None else available_dates(s.index, lag_bd, currency)
    known = pd.Series(s.to_numpy(), index=avail).sort_index()
    known = known[~known.index.duplicated(keep="last")]
    out = known.reindex(known.index.union(index)).ffill().reindex(index)
    out.name = s.name
    return out


def pit(name: str, index: pd.DatetimeIndex, long: pd.DataFrame | None = None) -> pd.Series:
    """A registered or derived series, point in time on `index`, with its own lag and calendar."""
    return point_in_time(get(name, long), sources.lag(name) if name not in DERIVED_LAGS else DERIVED_LAGS[name],
                         index, currency_of(name))


# --------------------------------------------------------------------------- #
# Derived series
# --------------------------------------------------------------------------- #
BOJ_DECISIONS_URL = "https://www.boj.or.jp/en/mopo/mpmdeci/index.htm"
# BoJ policy rate before the basic-loan-rate rule applies. Definition used throughout: the rate the
# BoJ targets for the uncollateralized overnight call rate where it set one, otherwise the rate paid
# on the marginal tier of current account balances. Source: the BoJ's list of monetary policy
# decisions (BOJ_DECISIONS_URL). From 1 Aug 2024 on, the BoJ sets the basic loan rate 0.25 percentage
# points above the policy rate, so the policy rate is read from that daily series (IR01/MADR1Z@D) and
# updates automatically.
BOJ_POLICY_TABLE = [
    ("2008-01-01", 0.50, "target for the uncollateralized overnight call rate around 0.5%"),
    ("2008-10-31", 0.30, "target lowered to around 0.3%"),
    ("2008-12-19", 0.10, "target lowered to around 0.1%; 0.1% paid on excess reserves"),
    ("2016-02-16", -0.10, "negative interest rate (-0.1%) applied to the policy-rate balance"),
    ("2024-03-21", 0.10, "exit from negative rates: target 0-0.1%, 0.1% paid on current accounts"),
]
BOJ_LOAN_RULE_START = pd.Timestamp("2024-08-01")
BOJ_LOAN_SPREAD = 0.25


def boj_policy(long: pd.DataFrame | None = None) -> pd.Series:
    """Daily BoJ policy rate: BOJ_POLICY_TABLE, then the basic loan rate minus 0.25 from 1 Aug 2024."""
    loan = raw("boj_loan_rate", long)
    long = load_long() if long is None else long
    days = pd.date_range("2008-01-01", max(loan.index.max(), long["date"].max()), freq="D")
    table = pd.Series({pd.Timestamp(d): r for d, r, _ in BOJ_POLICY_TABLE})
    policy = table.reindex(days.union(table.index)).ffill().reindex(days)
    after = loan.reindex(days.union(loan.index)).ffill().reindex(days) - BOJ_LOAN_SPREAD
    policy[days >= BOJ_LOAN_RULE_START] = after[days >= BOJ_LOAN_RULE_START]
    return policy.rename("boj_policy")


def usd_ior(long: pd.DataFrame | None = None) -> pd.Series:
    """Interest on reserves: IOER to 28 Jul 2021, IORB afterwards (the Fed renamed and merged the rate)."""
    ioer, iorb = raw("ioer", long), raw("iorb", long)
    return pd.concat([ioer[ioer.index < iorb.index.min()], iorb]).rename("usd_ior")


def eur_liquidity(long: pd.DataFrame | None = None) -> pd.Series:
    """Weekly euro liquidity proxy (EUR bn): current accounts + deposit facility - marginal lending.

    The ECB's daily excess-liquidity series starts only in Sep 2024; this weekly proxy has the full
    history. It omits minimum reserve requirements (about EUR 0.2 trillion against trillions of
    liquidity), which data validation checks against the daily series where both exist.
    """
    ca, df, mlf = raw("ilm_current_accounts", long), raw("ilm_deposit_facility", long), raw("ilm_mlf", long)
    frame = pd.concat([ca, df, mlf], axis=1).dropna()
    return ((frame.iloc[:, 0] + frame.iloc[:, 1] - frame.iloc[:, 2]) / 1e3).rename("eur_liquidity")


DERIVED = {"boj_policy": boj_policy, "usd_ior": usd_ior, "eur_liquidity": eur_liquidity}
DERIVED_LAGS = {"boj_policy": 0, "usd_ior": 0, "eur_liquidity": 2}


def maintenance_period_ends(long: pd.DataFrame | None = None) -> pd.DatetimeIndex:
    """Last days of ECB maintenance periods: the MMSR period dates (2018 on) and the day before each
    change in minimum reserve requirements (daily series, Sep 2024 on)."""
    ends = set(raw("mmsr_rate_le_KS_ALL", long).index)
    mrr = raw("min_reserves", long)
    changes = mrr.index[mrr.diff().fillna(0) != 0]
    for day in changes:
        if not (day.month == 1 and day.day == 1):  # 1 Jan 2026: euro-area enlargement, not a new period
            ends.add(day - bday("EUR"))
    return pd.DatetimeIndex(sorted(ends))


# --------------------------------------------------------------------------- #
# Writing (refresh only)
# --------------------------------------------------------------------------- #
def write_snapshot(long: pd.DataFrame, settlements: pd.DataFrame, fetched_at: str,
                   directory: Path = SNAPSHOT_DIR) -> dict:
    """Write series.csv, settlements.csv and manifest.json; return the manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    long = long.sort_values(["series", "date"]).reset_index(drop=True)
    long.to_csv(directory / "series.csv", index=False, float_format="%.6g", date_format="%Y-%m-%d")
    settlements.sort_values("date").to_csv(directory / "settlements.csv", index=False, date_format="%Y-%m-%d")
    coverage = long.groupby("series")["date"].agg(["min", "max", "size"])
    manifest = {
        "as_of": str(as_of(long).date()),
        "fetched_at": fetched_at,
        "series": {name: {"first": str(row["min"].date()), "last": str(row["max"].date()), "n": int(row["size"]),
                          "lag_bd": sources.lag(name)}
                   for name, row in coverage.iterrows()},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    _read_long.cache_clear()
    return manifest
