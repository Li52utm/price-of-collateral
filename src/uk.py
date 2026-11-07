"""D7: the UK, from QE to repo-led reserves. SONIA against Bank Rate, and how much of the reserve stock is
now supplied through the Bank of England's repo facilities (Short-Term Repo and Indexed Long-Term Repo).

Choices: docs/METHODOLOGY.md, "Desk upgrade D7". `run()` writes results/desk/uk.json, uk_daily.csv and
uk_weekly.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

import data
import paths

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = paths.RESULTS / "desk"
RECENT_DAYS = 250
TREND_WEEKS = 104
HAC_LAGS = 8
ALPHA = 0.05
LINK_FROM = "2023-01-01"


def sonia_spread(long: pd.DataFrame | None = None) -> pd.Series:
    """Daily SONIA minus Bank Rate (bp) on SONIA days, Bank Rate carried forward."""
    sonia, rate = data.get("sonia", long).dropna(), data.get("bank_rate", long).dropna()
    rate = rate.reindex(rate.index.union(sonia.index)).ffill().reindex(sonia.index)
    return ((sonia - rate) * 100).dropna().rename("sonia_minus_bank_rate")


def spread_stats(s: pd.Series, recent: int = RECENT_DAYS) -> dict:
    """Median and 95th percentile per year and over the last `recent` days; share of recent days above zero."""
    by_year = s.groupby(s.index.year).agg(["median", lambda x: x.quantile(0.95)])
    by_year.columns = ["median", "p95"]
    last = s.iloc[-recent:]
    return {"by_year": {int(y): {"median": float(r["median"]), "p95": float(r["p95"])} for y, r in by_year.iterrows()},
            "recent_median_bp": float(last.median()), "recent_p95_bp": float(last.quantile(0.95)),
            "recent_share_above": float((last > 1e-9).mean()), "latest_bp": float(s.iloc[-1]),
            "latest_date": str(s.index[-1].date())}


def weekly_frame(long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Weekly reserves, STR, ILTR, repo total, the repo share and the APF loan (GBP bn), Wednesdays."""
    cols = {k: data.get(f"boe_{k}", long) / 1e3 for k in ("reserves", "str", "iltr", "apf")}
    f = pd.DataFrame(cols).dropna(subset=["reserves", "str", "iltr"])
    f["repo"] = f["str"] + f["iltr"]
    f["repo_share"] = f["repo"] / f["reserves"] * 100
    return f


def share_trend(share: pd.Series, weeks: int = TREND_WEEKS, lags: int = HAC_LAGS) -> dict:
    """OLS of the repo share on time (years) over the latest `weeks` weeks with Newey-West errors."""
    s = share.dropna().iloc[-weeks:]
    t = (s.index - s.index[0]).days.to_numpy() / 365.25
    res = sm.OLS(s.to_numpy(), sm.add_constant(t)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    lo, hi = res.conf_int(alpha=ALPHA)[1]
    slope, p = float(res.params[1]), float(res.pvalues[1])
    verdict = ("increasingly" if slope > 0 and p < ALPHA else "decreasingly" if slope < 0 and p < ALPHA
               else "no significant change")
    return {"n": int(len(s)), "start": str(s.index[0].date()), "end": str(s.index[-1].date()),
            "slope_pp_per_year": slope, "ci": [float(lo), float(hi)], "p_value": p, "verdict": verdict}


def weeks_ago(s: pd.Series, n: int) -> float | None:
    """The value n observations before the latest (None if the history is shorter)."""
    s = s.dropna()
    return float(s.iloc[-1 - n]) if len(s) > n else None


def link(spread: pd.Series, weekly: pd.DataFrame, start: str = LINK_FROM) -> float:
    """Spearman correlation of the weekly mean spread (Thursday to Wednesday) with the repo share since `start`."""
    rows = {}
    weeks = weekly.index[weekly.index >= start]
    for prev, end in zip(weeks[:-1], weeks[1:], strict=True):
        days = spread[(spread.index > prev) & (spread.index <= end)]
        if len(days):
            rows[end] = float(days.mean())
    s = pd.Series(rows)
    both = pd.concat([s, weekly["repo_share"]], axis=1, keys=["spread", "share"], sort=True).dropna()
    return float(both["spread"].rank().corr(both["share"].rank())) if len(both) > 3 else float("nan")


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/desk/uk.json, uk_daily.csv and uk_weekly.csv."""
    s = sonia_spread(long)
    wk = weekly_frame(long)
    last = wk.iloc[-1]
    out = {"data_as_of": str(data.as_of(long).date()), "spread": spread_stats(s),
           "weekly": {"latest_date": str(wk.index[-1].date()), "reserves_bn": float(last["reserves"]),
                      "str_bn": float(last["str"]), "iltr_bn": float(last["iltr"]), "repo_bn": float(last["repo"]),
                      "repo_share_pct": float(last["repo_share"]),
                      "repo_share_52w_ago": weeks_ago(wk["repo_share"], 52),
                      "repo_share_104w_ago": weeks_ago(wk["repo_share"], 104),
                      "apf_bn": float(last["apf"]), "apf_104w_ago": weeks_ago(wk["apf"], 104),
                      "reserves_104w_ago": weeks_ago(wk["reserves"], 104)},
           "trend": share_trend(wk["repo_share"]), "spearman_spread_share": link(s, wk)}
    out_dir.mkdir(parents=True, exist_ok=True)
    s.loc["2018-01-01":].to_csv(out_dir / "uk_daily.csv", float_format="%.2f", index_label="date")
    wk.loc["2018-01-01":].to_csv(out_dir / "uk_weekly.csv", float_format="%.3f", index_label="date")
    (out_dir / "uk.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
