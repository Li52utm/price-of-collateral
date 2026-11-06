"""D0: how much the daily OAT-Bund spread is affected by mixing two yield constructions.

The French daily yield (Webstat TEC10) is a constant-maturity 10-year yield; the German daily yield used by
chapter IV (`bund10_daily`) is the current 10-year Bund, a single bond whose residual maturity drifts from
about 10 to about 9.5 years between new issues. The Bundesbank's fitted constant-maturity 10-year yield
(`bund10_cm`) lets us measure the gap day by day; the ECB monthly yields give a third reference for both
countries. Choices: docs/METHODOLOGY.md, "Desk upgrade D0". `run()` writes results/france/construction.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "france" / "construction.json"
MONTHLY_FROM = "2010-01-01"
RECENT_DAYS = 250
SMALL_GAP_BP = 3.0   # |mean daily gap| at or below this is "small" (one tenth of the 30 bp blowout threshold)


def gap_stats(gap_bp: pd.Series, recent_days: int = RECENT_DAYS) -> dict:
    """Summary of a daily gap in bp: mean, median, spread of values, recent mean and the latest value."""
    g = gap_bp.dropna()
    return {"n_days": int(len(g)), "first": str(g.index[0].date()), "last": str(g.index[-1].date()),
            "mean_bp": float(g.mean()), "median_bp": float(g.median()), "sd_bp": float(g.std(ddof=1)),
            "p05_bp": float(g.quantile(0.05)), "p95_bp": float(g.quantile(0.95)),
            "recent_mean_bp": float(g.iloc[-recent_days:].mean()), "latest_bp": float(g.iloc[-1])}


def monthly_comparison(daily: pd.Series, monthly: pd.Series, start: str = MONTHLY_FROM) -> dict:
    """Monthly mean of a daily yield minus a monthly yield (bp): mean and mean absolute difference."""
    m = daily.resample("MS").mean()
    both = pd.concat([m, monthly], axis=1, keys=["daily", "monthly"], sort=True).dropna().loc[start:]
    diff = (both["daily"] - both["monthly"]) * 100
    return {"n_months": int(len(both)), "mean_bp": float(diff.mean()), "mean_abs_bp": float(diff.abs().mean())}


def analyse(long: pd.DataFrame | None = None) -> dict:
    """Daily German construction gap and the monthly comparisons against the ECB IRS yields."""
    current, cm = data.get("bund10_daily", long), data.get("bund10_cm", long)
    oat = data.get("oat10_daily", long)
    both = pd.concat([current, cm], axis=1, keys=["current", "cm"], sort=True).dropna()
    gap = ((both["current"] - both["cm"]) * 100).rename("gap_bp")
    y_fr, y_de = data.get("y10_FR", long), data.get("y10_DE", long)
    spread_daily = (oat - current).dropna()
    spread_cm = (oat - cm).dropna()
    monthly = {
        "oat_tec10_vs_irs_fr": monthly_comparison(oat, y_fr),
        "bund_current_vs_irs_de": monthly_comparison(current, y_de),
        "bund_cm_vs_irs_de": monthly_comparison(cm, y_de),
        "spread_current_vs_irs": monthly_comparison(spread_daily, (y_fr - y_de).dropna()),
        "spread_cm_vs_irs": monthly_comparison(spread_cm, (y_fr - y_de).dropna()),
    }
    stats = gap_stats(gap)
    return {"data_as_of": str(data.as_of(long).date()), "gap": stats,
            "spread_effect_mean_bp": -stats["mean_bp"], "spread_effect_latest_bp": -stats["latest_bp"],
            "small": bool(abs(stats["mean_bp"]) <= SMALL_GAP_BP), "small_gap_bp": SMALL_GAP_BP,
            "latest_spread_current_bp": float(spread_daily.iloc[-1] * 100),
            "latest_spread_cm_bp": float(spread_cm.iloc[-1] * 100), "monthly": monthly}


def run(long: pd.DataFrame | None = None, path: Path = OUT_PATH) -> dict:
    """Write results/france/construction.json."""
    out = analyse(long)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load(path: Path = OUT_PATH) -> dict | None:
    """The saved D0 result, or None."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
