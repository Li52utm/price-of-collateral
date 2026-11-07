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
from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import MO
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    EasterMonday,
    GoodFriday,
    Holiday,
    USFederalHolidayCalendar,
    next_monday,
    next_monday_or_tuesday,
)
from pandas.tseries.offsets import CustomBusinessDay, DateOffset

import sources

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "results" / "snapshots"   # = paths.SNAPSHOT_DIR (inputs: never redirected)
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


class USRepoCalendar(USFederalHolidayCalendar):
    """US federal holidays plus Good Friday: SIFMA closes the bond market and SOFR is not published
    (no SOFR on any Good Friday 2018-2026; corrected 2026-11-04, see docs/METHODOLOGY.md)."""
    rules = USFederalHolidayCalendar.rules + [GoodFriday]


class UKCalendar(AbstractHolidayCalendar):
    """England and Wales bank holidays (D7): fixed rules with weekend substitution. One-off holidays (royal events)
    are not modelled; UK publication lags are set conservatively to absorb them."""
    rules = [Holiday("New Year", month=1, day=1, observance=next_monday), GoodFriday, EasterMonday,
             Holiday("Early May", month=5, day=1, offset=DateOffset(weekday=MO(1))),
             Holiday("Spring", month=5, day=31, offset=DateOffset(weekday=MO(-1))),
             Holiday("Summer", month=8, day=31, offset=DateOffset(weekday=MO(-1))),
             Holiday("Christmas", month=12, day=25, observance=next_monday),
             Holiday("Boxing Day", month=12, day=26, observance=next_monday_or_tuesday)]


CALENDARS = {"EUR": TargetCalendar(), "USD": USRepoCalendar(), "JPY": JapanCalendar(), "GBP": UKCalendar()}
CURRENCY_OF_SOURCE = {"ecb": "EUR", "bbk": "EUR", "fred": "USD", "nyfed": "USD", "ofr": "USD",
                      "fiscal": "USD", "boj": "JPY", "webstat": "EUR", "eurostat": "EUR", "boe": "GBP"}


@cache
def bday(currency: str) -> CustomBusinessDay:
    """Business-day offset for a currency's calendar."""
    return CustomBusinessDay(calendar=CALENDARS[currency])


def business_days(currency: str, start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Every business day of the currency's calendar from start to end (inclusive)."""
    return pd.date_range(start, end, freq=bday(currency))


def currency_of(name: str) -> str:
    """The business-day calendar of a series (EUR, USD, JPY or GBP)."""
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
    """The committed snapshot as a long frame (date, series, value), cached on the file time."""
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
    """Treasury coupon settlement dates from the committed snapshot."""
    if not Path(path).exists():
        raise SnapshotMissing(f"{path} not found")
    return pd.read_csv(path, parse_dates=["date"])


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """The snapshot manifest (as-of date, fetch time, coverage and lag per series)."""
    if not Path(path).exists():
        raise SnapshotMissing(f"{path} not found")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def as_of(long: pd.DataFrame | None = None) -> pd.Timestamp:
    """The snapshot's as-of date: the last day on which both €STR and SOFR are published."""
    long = load_long() if long is None else long
    return min(raw("estr", long).index.max(), raw("sofr", long).index.max())


# --------------------------------------------------------------------------- #
# "Latest": one definition for every number shown as latest (METHODOLOGY.md, corrections log 2026-11-07)
# --------------------------------------------------------------------------- #
def latest(s: pd.Series) -> tuple[pd.Timestamp, float]:
    """The latest published value of a series: its last non-missing observation in the snapshot, and its date.

    The snapshot holds only values published by its fetch date (the refresh trims announced policy rates
    dated later and validation fails any other future date), so the last stored observation IS the latest
    published value. Not "the last week with a following week" (a model's sample) and not "published by
    the as-of date" (the as-of date is an observation date: its own €STR and SOFR were published a day later).
    """
    s = s.dropna()
    if s.empty:
        raise ValueError(f"{s.name}: no observations")
    return s.index[-1], float(s.iloc[-1])


def latest_common_date(names: list[str], long: pd.DataFrame | None = None) -> pd.Timestamp:
    """The latest date on which EVERY named series has a published observation.

    Comparing two "latest" values is only valid on one date: if a policy rate is announced for day t but
    the market rate is published only to t-1, both must be read on t-1 (2026-11-07: Bank Rate 4.00% on
    5 Nov against SONIA of 4 Nov gave a false +26.6 bp of headroom).
    """
    common: pd.DatetimeIndex | None = None
    for name in names:
        idx = get(name, long).dropna().index
        common = idx if common is None else common.intersection(idx)
    if common is None or common.empty:
        raise ValueError(f"no date on which all of {names} are published")
    return common.max()


def value_at(name: str, day: pd.Timestamp, long: pd.DataFrame | None = None) -> float:
    """The observation of a series on exactly `day` (use with latest_common_date)."""
    return float(get(name, long).dropna().loc[day])


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
    if iorb.empty:  # a view of the data before IORB existed (found by tests/test_point_in_time.py, U6)
        return ioer.rename("usd_ior")
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
    settlements.sort_values("date", kind="mergesort").to_csv(directory / "settlements.csv", index=False,
                                                             date_format="%Y-%m-%d")
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
