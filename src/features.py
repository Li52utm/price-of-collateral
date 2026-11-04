"""Targets and features for the funding-spike forecasts (chapters V and VII).

Everything here follows docs/METHODOLOGY.md, Phase 2 (fixed before any test result was computed):
targets in basis points, calendar features known in advance, and state features taken as they were
PUBLISHED at the forecast origin, HORIZON_BD business days before the target day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import data

HORIZON_BD = 40
LEVEL_DAYS = 5
CURRENCIES = ("USD", "EUR", "JPY")
TARGET_START = {"USD": "2018-04-02", "EUR": "2019-10-01", "JPY": "2016-01-04"}
TARGET_LAG = {"USD": 1, "EUR": 1, "JPY": 2}  # publication lag of SOFR, €STR, TONA
TARGET_LABEL = {"USD": "SOFR minus interest on reserves", "EUR": "€STR minus the deposit facility rate",
                "JPY": "TONA minus the BoJ policy rate"}
STATE = {"USD": {"liq": ("reserves", 1e6), "rrp": ("onrrp", 1e3)},   # USD mn -> tn; USD bn -> tn
         "EUR": {"liq": ("eur_liquidity", 1e3)},                     # EUR bn -> tn
         "JPY": {"liq": ("boj_current_accounts", 1e6)}}              # JPY 100 mn -> JPY 100 tn
CALENDAR_COLUMNS = {"USD": ["me", "me_m1", "me_p1", "qe", "ye", "ye_m1", "ye_p1", "us_settle", "us_tax"],
                    "EUR": ["me", "me_m1", "me_p1", "qe", "ye", "ye_m1", "ye_p1", "mp_end", "mp_start"],
                    "JPY": ["me", "me_m1", "me_p1", "qe", "ye", "ye_m1", "ye_p1"]}
TAX_DAYS = ((3, 15), (4, 15), (6, 15), (9, 15), (12, 15))


def target(currency: str, long: pd.DataFrame | None = None) -> pd.Series:
    """Daily spread of the market overnight rate to the policy rate, in bp, on days the market rate exists."""
    if currency == "USD":
        market, policy = data.get("sofr", long), data.get("usd_ior", long)
    elif currency == "EUR":
        market, policy = data.get("estr", long), data.get("dfr", long)
    elif currency == "JPY":
        market, policy = data.get("tona", long), data.get("boj_policy", long)
    else:
        raise ValueError(currency)
    # Policy rates are step functions: carry each setting forward to every market day.
    policy = policy.reindex(policy.index.union(market.index)).ffill().reindex(market.index)
    spread = ((market - policy) * 100).dropna().loc[TARGET_START[currency]:]
    return spread.rename(f"spread_{currency}")


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
def _turn_days(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    s = pd.Series(calendar, index=calendar)
    month = s.dt.to_period("M")
    last = s.groupby(month).transform("max") == s
    first = s.groupby(month).transform("min") == s
    out = pd.DataFrame(index=calendar)
    out["me"] = last.astype(int)
    out["me_m1"] = out["me"].shift(-1, fill_value=0)
    out["me_p1"] = first.astype(int).where(out.index != calendar[0], 0)
    out["qe"] = (last & calendar.month.isin([3, 6, 9, 12])).astype(int)
    out["ye"] = (last & (calendar.month == 12)).astype(int)
    out["ye_m1"] = out["ye"].shift(-1, fill_value=0)
    out["ye_p1"] = out["ye"].shift(1, fill_value=0)
    return out


def calendar_features(days: pd.DatetimeIndex, currency: str, settlements: pd.DataFrame | None = None,
                      mp_ends: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Calendar dummies for `days` (computed on the currency's full business-day calendar)."""
    calendar = data.business_days(currency, days.min() - pd.Timedelta(days=40), days.max() + pd.Timedelta(days=40))
    out = _turn_days(calendar)
    if currency == "USD":
        coupons = settlements[settlements["security_type"].isin(["Note", "Bond"])]["date"] if settlements is not None \
            else pd.Series(dtype="datetime64[ns]")
        out["us_settle"] = calendar.isin(pd.DatetimeIndex(coupons)).astype(int)
        tax = []
        for year in range(calendar.year.min(), calendar.year.max() + 1):
            for month, dom in TAX_DAYS:
                tax.append(data.bday("USD").rollforward(pd.Timestamp(year, month, dom)))
        out["us_tax"] = calendar.isin(pd.DatetimeIndex(tax)).astype(int)
    if currency == "EUR":
        ends = mp_ends if mp_ends is not None else pd.DatetimeIndex([])
        out["mp_end"] = calendar.isin(ends).astype(int)
        starts = pd.DatetimeIndex([e + data.bday("EUR") for e in ends])
        out["mp_start"] = calendar.isin(starts).astype(int)
    return out.reindex(days)[CALENDAR_COLUMNS[currency]].fillna(0).astype(int)


def day_type(cal: pd.DataFrame) -> pd.Series:
    """'ye', 'qe', 'me' or 'ordinary' for each day (the comparable-day class of the baseline)."""
    kind = pd.Series("ordinary", index=cal.index)
    kind[cal["me"] == 1] = "me"
    kind[cal["qe"] == 1] = "qe"
    kind[cal["ye"] == 1] = "ye"
    return kind


# --------------------------------------------------------------------------- #
# Point in time at the forecast origin
# --------------------------------------------------------------------------- #
def origins(days: pd.DatetimeIndex, currency: str, horizon: int = HORIZON_BD,
            cap: pd.Timestamp | None = None) -> pd.DatetimeIndex:
    """Forecast origin for each target day: `horizon` business days earlier (capped at `cap`, the as-of date)."""
    offset = data.bday(currency)
    holidays = np.asarray(offset.holidays, dtype="datetime64[D]")
    d = np.asarray(days.values, dtype="datetime64[D]")
    o = pd.DatetimeIndex(np.busday_offset(np.busday_offset(d, 0, roll="forward", holidays=holidays),
                                          -horizon, roll="forward", holidays=holidays))
    if cap is not None:
        o = o.where(o <= cap, cap)
    return o


def at_origin(s: pd.Series, lag_bd: int, origin: pd.DatetimeIndex, currency: str) -> np.ndarray:
    """The value of `s` as published on each origin date."""
    unique = pd.DatetimeIndex(sorted(set(origin)))
    known = data.point_in_time(s, lag_bd, unique, currency)
    return known.reindex(origin).to_numpy()


def build(currency: str, days: pd.DatetimeIndex, long: pd.DataFrame | None = None,
          horizon: int = HORIZON_BD, cap: pd.Timestamp | None = None) -> pd.DataFrame:
    """Feature matrix for target days `days`: calendar + state at the origin + the baseline forecast.

    Columns: calendar dummies, `level`, `liq`, (`rrp`), `qe_liq`, `ye_liq`, `origin`, `day_type`,
    `baseline` (the last comparable day's value published by the origin).
    """
    settlements = data.load_settlements() if currency == "USD" and long is None else (
        _settlements_or_none() if currency == "USD" else None)
    mp_ends = data.maintenance_period_ends(long) if currency == "EUR" else None
    X = calendar_features(days, currency, settlements, mp_ends)
    origin = origins(days, currency, horizon, cap)
    y = target(currency, long)
    lag = TARGET_LAG[currency]
    X["level"] = at_origin(y.rolling(LEVEL_DAYS).mean().dropna(), lag, origin, currency)
    for col, (name, scale) in STATE[currency].items():
        X[col] = at_origin(data.get(name, long) / scale, data.sources.lag(name) if name not in data.DERIVED_LAGS
                           else data.DERIVED_LAGS[name], origin, currency)
    X["qe_liq"] = X["qe"] * X["liq"]
    X["ye_liq"] = X["ye"] * X["liq"]
    X["origin"] = origin
    X["day_type"] = day_type(X)
    X["baseline"] = baseline_point(y, X["day_type"], origin, currency, long)
    return X


def _settlements_or_none() -> pd.DataFrame | None:
    try:
        return data.load_settlements()
    except data.SnapshotMissing:
        return None


def baseline_point(y: pd.Series, kinds: pd.Series, origin: pd.DatetimeIndex, currency: str,
                   long: pd.DataFrame | None = None) -> np.ndarray:
    """Value on the most recent day of the same type that was published by the origin."""
    settlements = _settlements_or_none() if currency == "USD" else None
    mp_ends = data.maintenance_period_ends(long) if currency == "EUR" else None
    y_types = day_type(calendar_features(y.index, currency, settlements, mp_ends))
    out = np.full(len(kinds), np.nan)
    for kind in ("ye", "qe", "me", "ordinary"):
        rows = np.asarray(kinds == kind)
        if rows.any():
            history = y[y_types == kind]
            out[rows] = at_origin(history, TARGET_LAG[currency], origin[rows], currency)
    return out


def feature_columns(currency: str, model: str) -> list[str]:
    """Regressors of the calendar-only and calendar+state models."""
    cal = CALENDAR_COLUMNS[currency]
    if model == "calendar":
        return cal
    if model == "state":
        return cal + ["level"] + list(STATE[currency]) + ["qe_liq", "ye_liq"]
    raise ValueError(model)
