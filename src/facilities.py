"""D6: where each central bank's repo backstop sits relative to its floor, and how much headroom the market
overnight rate has below it. One row per central bank, on the as-of date.

Rates come from the snapshot; two prices are rules rather than series and are documented with their source
(see docs/METHODOLOGY.md, "Desk upgrade D6"). `run()` writes results/desk/facilities.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "results" / "desk" / "facilities.json"
FED_SRF_RULE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a1.htm"
BOE_STR_RULE_URL = ("https://www.bankofengland.co.uk/markets/market-notices/2022/august/"
                    "short-term-repo-facility-provisional-market-notice-4-august-2022")
BOE_STR_SPREAD = 0.0   # Short-Term Repo priced at Bank Rate + 0 bp


def value_on(name: str, day: pd.Timestamp, long: pd.DataFrame | None = None) -> tuple[float, str]:
    """The last published value of a series on or before `day` (percent) and its date."""
    s = data.get(name, long).dropna()
    s = s[s.index <= day]
    return float(s.iloc[-1]), str(s.index[-1].date())


def row(bank: str, floor_name: str, floor: float, backstop_name: str, backstop: float, market_name: str,
        market: float, market_date: str, extra: dict | None = None, note: str = "") -> dict:
    """One table row; differences in bp."""
    return {"bank": bank, "floor_name": floor_name, "floor": floor, "backstop_name": backstop_name,
            "backstop": backstop, "backstop_minus_floor_bp": round((backstop - floor) * 100, 4),
            "market_name": market_name, "market": market, "market_date": market_date,
            "headroom_bp": round((backstop - market) * 100, 4), "extra": extra or {}, "note": note}


def table(long: pd.DataFrame | None = None) -> list[dict]:
    """The four rows (ECB, Fed, Bank of England, Bank of Japan) on the as-of date."""
    day = data.as_of(long)
    v = lambda n: value_on(n, day, long)[0]  # noqa: E731
    rows = []
    estr, estr_d = value_on("estr", day, long)
    rows.append(row("ECB", "Deposit facility rate", v("dfr"), "Main refinancing operations (full allotment)", v("mro"),
                    "€STR", estr, estr_d, {"Marginal lending facility": v("mlf")}))
    sofr, sofr_d = value_on("sofr", day, long)
    rows.append(row("Federal Reserve", "Interest on reserve balances", v("usd_ior"),
                    "Standing repo facility (top of the target range)", v("fed_upper"), "SOFR", sofr, sofr_d,
                    {"ON RRP award rate": v("onrrp_rate"), "Target range lower bound": v("fed_lower")},
                    f"SRF rate = top of the target range, the FOMC implementation-note rule ({FED_SRF_RULE_URL})."))
    sonia, sonia_d = value_on("sonia", day, long)
    rows.append(row("Bank of England", "Bank Rate (reserves remuneration)", v("bank_rate"),
                    "Short-Term Repo (Bank Rate + 0 bp)", v("bank_rate") + BOE_STR_SPREAD, "SONIA", sonia, sonia_d,
                    note=f"STR priced at Bank Rate ({BOE_STR_RULE_URL})."))
    tona, tona_d = value_on("tona", day, long)
    rows.append(row("Bank of Japan", "Policy rate (current account remuneration)", v("boj_policy"),
                    "Complementary lending facility (basic loan rate)", v("boj_loan_rate"), "TONA", tona, tona_d,
                    note="Since August 2024 the project's policy rate is the basic loan rate minus 0.25, so the gap is "
                         "25 bp by construction (the BoJ's own rule)."))
    return rows


def run(long: pd.DataFrame | None = None, path: Path = OUT_PATH) -> dict:
    """Write results/desk/facilities.json."""
    out = {"data_as_of": str(data.as_of(long).date()), "rows": table(long)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
