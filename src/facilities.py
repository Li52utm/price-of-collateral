"""D6: where each central bank's repo backstop sits relative to its floor, and how much headroom the market
overnight rate has below it. One row per central bank.

Every row is read on ONE date: the latest date on which the floor, the backstop, the market rate and any
extra rate are all published (data.latest_common_date). A policy rate announced for a later day than the
market rate's last publication is reported separately as a later change, never differenced against an older
market rate (corrected 2026-11-07, docs/METHODOLOGY.md corrections log).

Rates come from the snapshot; two prices are rules rather than series and are documented with their source
(see docs/METHODOLOGY.md, "Desk upgrade D6"). `run()` writes results/desk/facilities.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data
import paths

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = paths.RESULTS / "desk" / "facilities.json"
FED_SRF_RULE_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a1.htm"
BOE_STR_RULE_URL = ("https://www.bankofengland.co.uk/markets/market-notices/2022/august/"
                    "short-term-repo-facility-provisional-market-notice-4-august-2022")
BOE_STR_SPREAD = 0.0   # Short-Term Repo priced at Bank Rate + 0 bp

# One entry per central bank: (label, series) for the floor, the backstop (plus a fixed spread in percentage
# points where the backstop is a rule on another rate), the market rate and any extra rates shown beside them.
BANKS: list[dict] = [
    {"bank": "ECB", "floor": ("Deposit facility rate", "dfr"),
     "backstop": ("Main refinancing operations (full allotment)", "mro", 0.0), "market": ("€STR", "estr"),
     "extra": {"Marginal lending facility": "mlf"}, "note": ""},
    {"bank": "Federal Reserve", "floor": ("Interest on reserve balances", "usd_ior"),
     "backstop": ("Standing repo facility (top of the target range)", "fed_upper", 0.0), "market": ("SOFR", "sofr"),
     "extra": {"ON RRP award rate": "onrrp_rate", "Target range lower bound": "fed_lower"},
     "note": f"SRF rate = top of the target range, the FOMC implementation-note rule ({FED_SRF_RULE_URL})."},
    {"bank": "Bank of England", "floor": ("Bank Rate (reserves remuneration)", "bank_rate"),
     "backstop": ("Short-Term Repo (Bank Rate + 0 bp)", "bank_rate", BOE_STR_SPREAD), "market": ("SONIA", "sonia"),
     "extra": {}, "note": f"STR priced at Bank Rate ({BOE_STR_RULE_URL})."},
    {"bank": "Bank of Japan", "floor": ("Policy rate (current account remuneration)", "boj_policy"),
     "backstop": ("Complementary lending facility (basic loan rate)", "boj_loan_rate", 0.0),
     "market": ("TONA", "tona"), "extra": {},
     "note": "Since August 2024 the project's policy rate is the basic loan rate minus 0.25, so the gap is 25 bp by "
             "construction (the BoJ's own rule)."},
]


def later_changes(spec: dict, day: pd.Timestamp, long: pd.DataFrame | None = None) -> list[dict]:
    """Floor or backstop settings published for a day after the comparison date that differ from it."""
    out = []
    for label, name in (spec["floor"], spec["backstop"][:2]):
        if any(c["series"] == name for c in out):
            continue  # the BoE floor and backstop are the same series
        last_day, last = data.latest(data.get(name, long))
        if last_day > day and abs(last - data.value_at(name, day, long)) > 1e-9:
            changed = data.get(name, long).dropna()
            first = changed[(changed.index > day) & ((changed - last).abs() < 1e-9)].index.min()
            out.append({"series": name, "name": label, "previous": data.value_at(name, day, long), "value": last,
                        "from": str(first.date())})
    return out


def row(bank: str, floor_name: str, floor: float, backstop_name: str, backstop: float, market_name: str,
        market: float, date: str, extra: dict | None = None, note: str = "",
        later: list[dict] | None = None) -> dict:
    """One table row; every rate is read on `date`; differences in bp."""
    return {"bank": bank, "date": date, "floor_name": floor_name, "floor": floor, "backstop_name": backstop_name,
            "backstop": backstop, "backstop_minus_floor_bp": round((backstop - floor) * 100, 4),
            "market_name": market_name, "market": market,
            "headroom_bp": round((backstop - market) * 100, 4), "extra": extra or {}, "note": note,
            "later_changes": later or []}


def bank_row(spec: dict, long: pd.DataFrame | None = None) -> dict:
    """One table row on the latest date on which all of the bank's series are published."""
    floor_s, (backstop_s, spread), market_s = spec["floor"][1], spec["backstop"][1:], spec["market"][1]
    day = data.latest_common_date([floor_s, backstop_s, market_s, *spec["extra"].values()], long)
    at = lambda n: data.value_at(n, day, long)  # noqa: E731
    return row(spec["bank"], spec["floor"][0], at(floor_s), spec["backstop"][0], at(backstop_s) + spread,
               spec["market"][0], at(market_s), str(day.date()), {k: at(v) for k, v in spec["extra"].items()},
               spec["note"], later_changes(spec, day, long))


def table(long: pd.DataFrame | None = None) -> list[dict]:
    """The four rows (ECB, Fed, Bank of England, Bank of Japan), each on its own common date."""
    return [bank_row(spec, long) for spec in BANKS]


def run(long: pd.DataFrame | None = None, path: Path = OUT_PATH) -> dict:
    """Write results/desk/facilities.json."""
    out = {"data_as_of": str(data.as_of(long).date()), "rows": table(long)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
