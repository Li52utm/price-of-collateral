"""D4: who holds the collateral. Shares of French, Italian, German and Spanish government debt by holder
sector, how they shifted after quantitative tightening began, and who absorbed France's new supply.

Data: Eurostat gov_10dd_ggd (annual, consolidated, face value), the closest public alternative to the ECB
securities holdings statistics (see docs/METHODOLOGY.md, "Desk upgrade D4", and CLAUDE.md plan adjustments).
`run()` writes results/desk/holders.json and holders_shares.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data
import paths
import sources

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = paths.RESULTS / "desk"
BASE_YEAR = 2022           # last year-end before the ECB's portfolio started to shrink (March 2023)
HOLDERS = {"S121": "Domestic central bank", "S122_S123": "Domestic banks",
           "S124-S129": "Domestic insurers, pension and investment funds", "S2": "Non-residents"}
OTHER = "Other domestic"


def holdings(country: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Year-end holdings (EUR bn) by holder, with 'Other domestic' = total minus the four sectors."""
    total = data.get(f"hold_{country}_S1_S2", long) / 1e3
    cols = {label: data.get(f"hold_{country}_{code}", long) / 1e3 for code, label in HOLDERS.items()}
    frame = pd.DataFrame(cols).reindex(total.index)
    frame[OTHER] = total - frame.sum(axis=1, min_count=len(HOLDERS))
    frame["Total"] = total
    return frame.dropna()


def shares(h: pd.DataFrame) -> pd.DataFrame:
    """Each holder's share of the total (percent)."""
    return h.drop(columns="Total").div(h["Total"], axis=0) * 100


def shift(sh: pd.DataFrame, base_year: int = BASE_YEAR) -> dict:
    """Change in each holder's share (pp) from the base year-end to the latest year-end."""
    base = sh[sh.index.year == base_year]
    if base.empty:
        return {}
    change = sh.iloc[-1] - base.iloc[0]
    return {"base": str(base.index[0].date()), "latest": str(sh.index[-1].date()),
            "base_shares": {k: float(v) for k, v in base.iloc[0].items()},
            "latest_shares": {k: float(v) for k, v in sh.iloc[-1].items()},
            "change_pp": {k: float(v) for k, v in change.items()},
            "largest_rise": str(change.idxmax()), "largest_fall": str(change.idxmin())}


def absorption(h: pd.DataFrame, base_year: int = BASE_YEAR) -> dict:
    """Change in holdings (EUR bn) by holder from the base year-end to the latest, and share of the debt increase."""
    base = h[h.index.year == base_year]
    if base.empty:
        return {}
    change = h.iloc[-1] - base.iloc[0]
    total = float(change["Total"])
    holders = change.drop("Total")
    absorbers = holders[holders > 0].sort_values(ascending=False)
    return {"base": str(base.index[0].date()), "latest": str(h.index[-1].date()), "total_change_bn": total,
            "change_bn": {k: float(v) for k, v in holders.items()},
            "share_of_increase": {k: float(v / total) if total else float("nan") for k, v in holders.items()},
            "absorbers": list(absorbers.index), "largest_absorber": str(absorbers.index[0]) if len(absorbers) else None}


def analyse(long: pd.DataFrame | None = None) -> tuple[dict, pd.DataFrame]:
    """Shares, shifts since the base year and France's absorption (dict), and every share in long format."""
    out = {"data_as_of": str(data.as_of(long).date()), "base_year": BASE_YEAR, "countries": {}}
    rows = []
    for c in sources.HOLDER_COUNTRIES:
        h = holdings(c, long)
        sh = shares(h)
        out["countries"][c] = {"first": str(h.index[0].date()), "last": str(h.index[-1].date()),
                               "total_bn": float(h["Total"].iloc[-1]), "shift": shift(sh)}
        for day, row in sh.iterrows():
            for holder, value in row.items():
                rows.append({"date": day, "country": c, "holder": holder, "share_pct": float(value),
                             "holding_bn": float(h.loc[day, holder])})
    out["france_absorption"] = absorption(holdings("FR", long))
    return out, pd.DataFrame(rows)


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/desk/holders.json and holders_shares.csv."""
    out, frame = analyse(long)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "holders_shares.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d")
    (out_dir / "holders.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
