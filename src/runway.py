"""D1: the euro runway. How far euro liquidity is from chapter II's pressure point, three mechanical
scenarios for when it gets there, and whether €STR minus the DFR has started drifting up.

The scenarios are extrapolations of the trailing year's drain, NOT forecasts. Choices are fixed in
docs/METHODOLOGY.md, "Desk upgrade D1". `run()` writes results/desk/runway.json and runway_paths.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import corridors
import data
import features as F

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "desk"
TRAILING_WEEKS = 52
SCENARIOS = {"slow": 0.5, "base": 1.0, "fast": 1.5}
HORIZON_END = pd.Timestamp("2028-12-31")
REPORT_DATES = ("2026-12-31", "2027-12-31")
TREND_DAYS = 365        # calendar days in the trend sample
TREND_HAC_LAGS = 20     # about a month of business days
ALPHA = 0.05


# --------------------------------------------------------------------------- #
# 1. Distance to the pressure point
# --------------------------------------------------------------------------- #
def boundaries(reserves_eur: dict) -> dict[str, float]:
    """The band's upper end, the kink and the band's lower end, in EUR bn (chapter II reports trillions)."""
    lo, hi = reserves_eur["pressure_band"]
    return {"upper": hi * 1e3, "kink": reserves_eur["pressure_point"] * 1e3, "lower": lo * 1e3}


def distances(latest_bn: float, bounds: dict[str, float]) -> dict[str, float]:
    """Latest liquidity minus each boundary (EUR bn): positive = runway left, negative = already below."""
    return {k: float(latest_bn - v) for k, v in bounds.items()}


def last_cross_below(s: pd.Series, level: float) -> pd.Timestamp | None:
    """Start of the current run at or below `level`: the first week of that run (None if the latest is above)."""
    s = s.dropna()
    if s.empty or s.iloc[-1] > level:
        return None
    above = s[s > level]
    after = s[s.index > above.index[-1]] if len(above) else s
    return after.index[0]


# --------------------------------------------------------------------------- #
# 2. Scenarios
# --------------------------------------------------------------------------- #
def trailing_weekly_change(s: pd.Series, weeks: int = TRAILING_WEEKS) -> float:
    """Mean weekly change over the trailing `weeks` observations (EUR bn per week)."""
    s = s.dropna()
    if len(s) <= weeks:
        return float("nan")
    return float((s.iloc[-1] - s.iloc[-1 - weeks]) / weeks)


def scenario_paths(latest_date: pd.Timestamp, latest_bn: float, drift: float,
                   end: pd.Timestamp = HORIZON_END, scales: dict[str, float] = SCENARIOS) -> pd.DataFrame:
    """Linear weekly paths (EUR bn), one column per scenario, from the latest week to `end`."""
    weeks = pd.date_range(latest_date, end, freq="7D")
    steps = np.arange(len(weeks))
    return pd.DataFrame({name: latest_bn + scale * drift * steps for name, scale in scales.items()}, index=weeks)


def first_at_or_below(path: pd.Series, level: float) -> pd.Timestamp | None:
    """First week a path is at or below `level` (None if it never gets there within the horizon)."""
    hit = path[path <= level]
    return hit.index[0] if len(hit) else None


def scenario_table(paths: pd.DataFrame, bounds: dict[str, float], history: pd.Series, drift: float) -> dict:
    """Crossing dates per scenario and boundary, and the level on each report date."""
    latest = float(history.dropna().iloc[-1])
    out = {}
    for name in paths:
        rows = {}
        for b, level in bounds.items():
            if latest <= level:
                since = last_cross_below(history, level)
                rows[b] = {"status": "already crossed", "date": str(since.date()) if since is not None else None}
            elif drift >= 0:
                rows[b] = {"status": "not reached (no drain)", "date": None}
            else:
                hit = first_at_or_below(paths[name], level)
                rows[b] = ({"status": "reached", "date": str(hit.date())} if hit is not None else
                           {"status": "beyond horizon", "date": None})
        levels = {d: float(paths[name].asof(pd.Timestamp(d))) for d in REPORT_DATES}
        out[name] = {"scale": SCENARIOS.get(name, float("nan")), "weekly_drift_bn": float(SCENARIOS[name] * drift),
                     "crossings": rows, "levels_bn": levels}
    return out


# --------------------------------------------------------------------------- #
# 3. Trend in €STR minus the DFR
# --------------------------------------------------------------------------- #
def month_turn_days(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last business day of each month in `days` and the first business day after it."""
    s = pd.Series(days, index=days)
    last = s.groupby([days.year, days.month]).max()
    turn = set(last)
    for d in last:
        nxt = days[days > d]
        if len(nxt):
            turn.add(nxt[0])
    return pd.DatetimeIndex(sorted(turn))


def trend_test(y: pd.Series, lags: int = TREND_HAC_LAGS) -> dict:
    """OLS of y (bp) on time in years with Newey-West errors: slope (bp per year), 95% CI and p-value."""
    y = y.dropna()
    t = (y.index - y.index[0]).days.to_numpy() / 365.25
    X = sm.add_constant(t)
    res = sm.OLS(y.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    lo, hi = res.conf_int(alpha=ALPHA)[1]
    return {"n": int(len(y)), "start": str(y.index[0].date()), "end": str(y.index[-1].date()),
            "slope_bp_per_year": float(res.params[1]), "ci": [float(lo), float(hi)], "p_value": float(res.pvalues[1]),
            "first_bp": float(y.iloc[:20].mean()), "last_bp": float(y.iloc[-20:].mean()), "hac_lags": lags}


def trend_verdict(slope: float, p_value: float, alpha: float = ALPHA) -> str:
    """'drifting up', 'drifting down' or 'no significant trend' (pre-registered rule)."""
    if p_value < alpha and slope > 0:
        return "drifting up"
    if p_value < alpha and slope < 0:
        return "drifting down"
    return "no significant trend"


def spread_trend(long: pd.DataFrame | None = None) -> dict:
    """The D1 trend test on the last 12 months, and its sensitivity without month-end turn days."""
    y = F.target("EUR", long)
    end = y.index[-1]
    window = y[y.index > end - pd.Timedelta(days=TREND_DAYS)]
    main = trend_test(window)
    main["verdict"] = trend_verdict(main["slope_bp_per_year"], main["p_value"])
    no_turns = window[~window.index.isin(month_turn_days(window.index))]
    sens = trend_test(no_turns)
    sens["verdict"] = trend_verdict(sens["slope_bp_per_year"], sens["p_value"])
    return {"main": main, "without_turn_days": sens}


def published_by(s: pd.Series, lag_bd: int, day: pd.Timestamp, currency: str = "EUR") -> pd.Series:
    """Only the observations already published on `day` (observation date + lag business days <= day)."""
    if s.empty:
        return s
    return s[data.available_dates(s.index, lag_bd, currency) <= day]


# --------------------------------------------------------------------------- #
# Everything
# --------------------------------------------------------------------------- #
def analyse(long: pd.DataFrame | None = None, corridor_summary: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """Distance, scenarios and the trend test (dict) and the scenario paths with history (frame)."""
    summary = corridor_summary or corridors.load_summary()
    res = summary["reserves"]["EUR"]
    as_of = data.as_of(long)
    liq = published_by(data.get("eur_liquidity", long).dropna(), data.DERIVED_LAGS["eur_liquidity"], as_of)
    sec = published_by((data.get("mp_securities", long) / 1e3).dropna(), data.sources.lag("mp_securities"), as_of)
    latest_date, latest = liq.index[-1], float(liq.iloc[-1])
    bounds = boundaries(res)
    identified = bool(res["kink_identified"])
    drift = trailing_weekly_change(liq)
    sec_drift = trailing_weekly_change(sec)
    paths = scenario_paths(latest_date, latest, drift)
    out = {
        "data_as_of": str(data.as_of(long).date()), "latest_date": str(latest_date.date()), "latest_bn": latest,
        "kink_identified": identified, "boundaries_bn": bounds,
        "distance_bn": distances(latest, bounds) if identified else None,
        "drift": {"liquidity_bn_per_week": drift, "securities_bn_per_week": sec_drift,
                  "securities_share": float(sec_drift / drift) if drift else float("nan"),
                  "liquidity_12m_change_bn": float(drift * TRAILING_WEEKS),
                  "securities_12m_change_bn": float(sec_drift * TRAILING_WEEKS), "weeks": TRAILING_WEEKS},
        "scenarios": scenario_table(paths, bounds, liq, drift) if identified else None,
        "trend": spread_trend(long),
    }
    hist = liq[liq.index >= "2019-01-01"].rename("actual").to_frame()
    frame = pd.concat([hist, paths], axis=1, sort=True)
    return out, frame


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/desk/runway.json and runway_paths.csv (EUR bn)."""
    out, frame = analyse(long)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runway.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    frame.to_csv(out_dir / "runway_paths.csv", float_format="%.3f", index_label="date")
    return out
