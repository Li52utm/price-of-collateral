"""D3: the Fed's year-end toolkit. Repo operations (the standing repo facility from July 2021), ON RRP and
bill holdings around every quarter-end and year-end since 2018, with SOFR minus IOR at the turn.

Descriptive only (no model). Choices: docs/METHODOLOGY.md, "Desk upgrade D3". `run()` writes
results/desk/toolkit.json and toolkit_turns.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import data
import features as F

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "desk"
FIRST_TURN = pd.Timestamp("2018-06-01")
WINDOW_BD = 5
USAGE_MIN_BN = 1.0
BILLS_WEEKS = 13
SPLIT_YEAR = 2023


def quarter_turns(days: pd.DatetimeIndex, start: pd.Timestamp = FIRST_TURN) -> pd.DatetimeIndex:
    """Last business day of each March, June, September and December among `days` (complete months only)."""
    s = pd.Series(days, index=days)
    s = s[s.index >= start]
    last = s.groupby([s.index.year, s.index.month]).max()
    turns = [d for d in last if d.month in (3, 6, 9, 12)]
    # The latest month may be incomplete: keep its last day only if a later business day exists in `days`.
    return pd.DatetimeIndex([d for d in turns if (days > d).any()])


def around(s: pd.Series, day: pd.Timestamp, days: pd.DatetimeIndex, n: int = WINDOW_BD) -> dict:
    """Mean of s over the n business days before `day`, its value on `day`, and the mean over the n days after.

    `days` is the business-day calendar; a missing value on a business day counts as zero usage only for
    facility series, so the caller passes series already reindexed to `days`.
    """
    i = days.get_loc(day)
    before = s.iloc[max(0, i - n):i]
    after = s.iloc[i + 1:i + 1 + n]
    return {"before": float(before.mean()) if len(before) == n and before.notna().all() else None,
            "at": float(s.iloc[i]) if pd.notna(s.iloc[i]) else None,
            "after": float(after.mean()) if len(after) == n and after.notna().all() else None}


def bills_at(bills_bn: pd.Series, day: pd.Timestamp, weeks: int = BILLS_WEEKS) -> tuple[float | None, float | None]:
    """Bill holdings on the last Wednesday on or before `day` and their change over `weeks` weeks (USD bn)."""
    upto = bills_bn[bills_bn.index <= day].dropna()
    if upto.empty:
        return None, None
    level = float(upto.iloc[-1])
    prior = upto[upto.index <= upto.index[-1] - pd.Timedelta(weeks=weeks)]
    return level, (float(level - prior.iloc[-1]) if len(prior) else None)


def turn_table(long: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per quarter-end turn: facility usage around it, SOFR minus IOR at it, bill holdings."""
    y = F.target("USD", long)
    end = y.index[-1]
    days = data.business_days("USD", "2018-01-01", end)
    repo = data.get("fed_repo_total", long).reindex(days)
    rrp = data.get("onrrp", long).reindex(days)
    # Facility series: a published business day with no operation is zero usage; days after the last
    # publication stay missing.
    repo[(repo.index <= data.get("fed_repo_total", long).index.max()) & repo.isna()] = 0.0
    bills = data.get("fed_bills", long) / 1e3
    rows = []
    for d in quarter_turns(days[days <= end]):
        r, o = around(repo, d, days), around(rrp, d, days)
        level, change = bills_at(bills, d)
        rows.append({"date": d, "kind": "year-end" if d.month == 12 else "quarter-end",
                     "repo_before": r["before"], "repo_at": r["at"], "repo_after": r["after"],
                     "rrp_before": o["before"], "rrp_at": o["at"], "rrp_after": o["after"],
                     "spread_at_bp": float(y.get(d, np.nan)), "bills_bn": level, "bills_13w_change_bn": change})
    return pd.DataFrame(rows).set_index("date")


def pattern(t: pd.DataFrame, split_year: int = SPLIT_YEAR, min_bn: float = USAGE_MIN_BN) -> dict:
    """Counts of turns with usage, means before/at/after for those turns, and the rank correlation with the spread."""
    used = t["repo_at"].fillna(0) >= min_bn
    early, late = t.index.year < split_year, t.index.year >= split_year
    u = t[used]
    both = t[["spread_at_bp", "repo_at"]].dropna()
    rho = float(both["spread_at_bp"].rank().corr(both["repo_at"].rank())) if len(both) > 3 else float("nan")
    return {"n_turns": int(len(t)), "n_used": int(used.sum()), "n_early": int(early.sum()),
            "n_used_early": int((used & early).sum()), "n_late": int(late.sum()),
            "n_used_late": int((used & late).sum()),
            "mean_before_used": float(u["repo_before"].mean()) if len(u) else None,
            "mean_at_used": float(u["repo_at"].mean()) if len(u) else None,
            "mean_after_used": float(u["repo_after"].dropna().mean()) if u["repo_after"].notna().any() else None,
            "max_at": float(t["repo_at"].max()), "max_at_date": str(t["repo_at"].idxmax().date()),
            "spearman_spread_usage": rho, "min_bn": min_bn, "split_year": split_year}


def latest_state(t: pd.DataFrame, long: pd.DataFrame | None = None) -> dict:
    """Latest facility usage and bill holdings, and the latest turn (for the chapter VII backstop line)."""
    repo, rrp = data.get("fed_repo_total", long).dropna(), data.get("onrrp", long).dropna()
    bills = data.get("fed_bills", long).dropna() / 1e3
    level, change = bills_at(bills, bills.index[-1])
    last = t.iloc[-1]
    recent = repo[repo.index > repo.index[-1] - pd.Timedelta(days=30)]
    return {"repo_date": str(repo.index[-1].date()), "repo_bn": float(repo.iloc[-1]),
            "repo_30d_max_bn": float(recent.max()), "repo_30d_days_used": int((recent >= USAGE_MIN_BN).sum()),
            "rrp_date": str(rrp.index[-1].date()), "rrp_bn": float(rrp.iloc[-1]),
            "bills_date": str(bills.index[-1].date()), "bills_bn": level, "bills_13w_change_bn": change,
            "last_turn": str(t.index[-1].date()), "last_turn_repo_bn": float(last["repo_at"]),
            "last_turn_spread_bp": float(last["spread_at_bp"])}


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/desk/toolkit.json and toolkit_turns.csv."""
    t = turn_table(long)
    out = {"data_as_of": str(data.as_of(long).date()), "pattern": pattern(t), "latest": latest_state(t, long)}
    out_dir.mkdir(parents=True, exist_ok=True)
    t.to_csv(out_dir / "toolkit_turns.csv", float_format="%.3f", index_label="date")
    (out_dir / "toolkit.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
