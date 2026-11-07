"""D9: the numbers behind the desk note's regional funding overview, from the snapshot.

For each region: the overnight spread to policy (latest day and its change over the last month) and the state
variables a funding desk watches (reserves, Treasury cash, facility usage, central bank balances). Rules:
docs/METHODOLOGY.md, "Desk upgrade D9". `run()` writes results/desk/overview.json; desk_note.py turns it into text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data
import features as F
import france_daily as FD
import uk

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "desk" / "overview.json"
MEAN_DAYS = 20     # the 20-day mean of SOFR minus IORB used by the reserves risk


def level_and_change(s: pd.Series, scale: float = 1.0) -> dict:
    """Latest value, its date, and the change from the last value on or before the latest date minus one month."""
    s = s.dropna() * scale
    last_day, value = data.latest(s)   # the project's one definition of "latest"
    prior = s[s.index <= last_day - pd.DateOffset(months=1)]
    return {"date": str(last_day.date()), "value": value,
            "change_1m": float(value - prior.iloc[-1]) if len(prior) else None,
            "prior_date": str(prior.index[-1].date()) if len(prior) else None}


def analyse(long: pd.DataFrame | None = None) -> dict:
    """Every number of the regional overview (spreads in bp; amounts in bn or tn of the currency, as named)."""
    g = lambda n: data.get(n, long)  # noqa: E731
    usd = F.target("USD", long)
    return {
        "data_as_of": str(data.as_of(long).date()),
        "US": {"spread": level_and_change(usd), "spread_20d_mean": float(usd.iloc[-MEAN_DAYS:].mean()),
               "reserves_tn": level_and_change(g("reserves"), 1e-6), "tga_bn": level_and_change(g("tga_daily"), 1e-3),
               "onrrp_bn": level_and_change(g("onrrp"))},
        "EUR": {"spread": level_and_change(F.target("EUR", long)),
                "liquidity_bn": level_and_change(g("eur_liquidity")),
                "gov_deposits_bn": level_and_change(g("gov_deposits"), 1e-3)},
        "FR": {"spread": level_and_change(FD.daily_spread(long))},
        "UK": {"spread": level_and_change(uk.sonia_spread(long)), "reserves_bn": level_and_change(g("boe_reserves"),
                                                                                                    1e-3)},
        "JP": {"spread": level_and_change(F.target("JPY", long)),
               "current_accounts_tn": level_and_change(g("boj_current_accounts"), 1e-4)},
    }


def run(long: pd.DataFrame | None = None, path: Path = OUT_PATH) -> dict:
    """Write results/desk/overview.json."""
    out = analyse(long)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
