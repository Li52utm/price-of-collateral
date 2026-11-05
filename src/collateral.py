"""Chapter III: is the extra repo cost of Italian and French collateral credit risk or scarcity?

Fixed in docs/METHODOLOGY.md, Phase 4 (III). Frequency: ECB maintenance periods (MMSR).
`run()` writes results/collateral/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import data
import stats_tools as st

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "collateral"
SIDE, TENOR = "le", "KS"
COUNTRIES = ("IT", "FR", "ES")
REGRESSION_COUNTRIES = ("IT", "FR")
QT_START = pd.Timestamp("2023-03-01")
HAC_LAGS = 3
ROLL_WINDOW = 24
ALPHA = 0.05
CREDIT, SCARCITY = "credit", ("liquidity", "de_holdings")
LABELS = {"credit": "10-year yield spread to Germany (bp)", "liquidity": "euro liquidity (EUR trillion)",
          "de_holdings": "Eurosystem holdings of German bonds (EUR 100 billion)"}


def repo_rate(country: str, long: pd.DataFrame | None = None) -> pd.Series:
    return data.get(f"mmsr_rate_{SIDE}_{TENOR}_{country}", long)


def monthly_spreads(long: pd.DataFrame | None = None, countries=None) -> pd.DataFrame:
    """10-year yield spreads to Germany (bp), monthly, from the ECB IRS series."""
    import sources
    countries = countries or [c for c in sources.YIELD_COUNTRIES if c != "DE"]
    de = data.get("y10_DE", long)
    return pd.DataFrame({c: (data.get(f"y10_{c}", long) - de) * 100 for c in countries}).dropna(how="all")


def period_panel(long: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per maintenance period: repo spreads to German collateral and the explanatory variables."""
    de = repo_rate("DE", long)
    ends = de.index
    starts = [ends[0] - pd.Timedelta(days=42)] + [e + pd.Timedelta(days=1) for e in ends[:-1]]
    spreads = monthly_spreads(long, list(COUNTRIES))
    liquidity = data.get("eur_liquidity", long) / 1e3
    holdings = data.get("pspp_DE", long) / 1e5
    rows = []
    for start, end in zip(starts, ends):
        row = {"end": end, "start": start, "de_rate": float(de[end])}
        for c in COUNTRIES:
            rate = repo_rate(c, long)
            row[f"repo_{c}"] = float((rate.get(end, np.nan) - de[end]) * 100)
            months = spreads.loc[start.to_period("M").to_timestamp():end, c]
            row[f"credit_{c}"] = float(months.mean()) if len(months) else np.nan
        liq = liquidity.loc[start:end]
        row["liquidity"] = float(liq.mean()) if len(liq) else np.nan
        held = holdings[holdings.index <= end]
        row["de_holdings"] = float(held.iloc[-1]) if len(held) else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("end")


def regression(panel: pd.DataFrame, country: str) -> dict:
    """spread = a + b credit + c liquidity + d de_holdings, Newey-West errors."""
    df = panel[[f"repo_{country}", f"credit_{country}", "liquidity", "de_holdings"]].dropna()
    y = df[f"repo_{country}"]
    X = sm.add_constant(df.drop(columns=f"repo_{country}").rename(columns={f"credit_{country}": "credit"}))
    res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    std_effect = {k: float(res.params[k] * X[k].std(ddof=1)) for k in ("credit", *SCARCITY)}
    pvals = {k: float(res.pvalues[k]) for k in ("credit", *SCARCITY)}
    verdict = decide(std_effect, pvals)
    split = int((df.index > QT_START).argmax())
    chow = st.chow_test(y.to_numpy(), X.to_numpy(), split)
    rolling = []
    for i in range(ROLL_WINDOW, len(df) + 1):
        sub = df.iloc[i - ROLL_WINDOW:i]
        Xs = sm.add_constant(sub.drop(columns=f"repo_{country}").rename(columns={f"credit_{country}": "credit"}))
        r = sm.OLS(sub[f"repo_{country}"], Xs).fit()
        rolling.append({"end": sub.index[-1], **{k: float(r.params[k]) for k in ("credit", *SCARCITY)}})
    before = df[df.index <= QT_START]
    after = df[df.index > QT_START]
    sub_verdicts = {}
    for name, part in (("before_qt", before), ("after_qt", after)):
        if len(part) >= 8:
            Xp = sm.add_constant(part.drop(columns=f"repo_{country}").rename(columns={f"credit_{country}": "credit"}))
            rp = sm.OLS(part[f"repo_{country}"], Xp).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
            eff = {k: float(rp.params[k] * Xp[k].std(ddof=1)) for k in ("credit", *SCARCITY)}
            pv = {k: float(rp.pvalues[k]) for k in eff}
            sub_verdicts[name] = {"n": len(part), "verdict": decide(eff, pv), "pvalues": pv,
                                  "std_effect": eff, "mean_spread": float(part[f"repo_{country}"].mean())}
    return {"country": country, "n": int(len(df)), "first": str(df.index[0].date()), "last": str(df.index[-1].date()),
            "params": {k: float(v) for k, v in res.params.items()}, "pvalues": {k: float(v) for k, v in res.pvalues.items()},
            "r2": float(res.rsquared), "std_effect": std_effect, "verdict": verdict,
            "chow": chow, "qt_split_period": str(df.index[split].date()), "sub_periods": sub_verdicts,
            "mean_spread": float(y.mean()), "latest_spread": float(y.iloc[-1]),
            "rolling": rolling}


def decide(std_effect: dict, pvals: dict) -> str:
    """The decision rule fixed in METHODOLOGY.md (III)."""
    credit = abs(std_effect["credit"])
    scarcity = sum(abs(std_effect[k]) for k in SCARCITY)
    if pvals["credit"] < ALPHA and credit > scarcity:
        return "credit"
    if any(pvals[k] < ALPHA for k in SCARCITY) and scarcity > credit:
        return "scarcity"
    return "both / unclear"


TERMS = ("credit", *SCARCITY)


def apply_holm(results: dict) -> None:
    """Holm-adjust the coefficient p-values (F3: full sample; F4: sub-periods) and re-apply the decision
    rule with the adjusted values (METHODOLOGY.md, U2). The raw-p verdict is kept as `verdict_raw`."""
    keys = [(c, k) for c in results for k in TERMS]
    adjusted = st.holm([results[c]["pvalues"][k] for c, k in keys])
    for (c, k), p in zip(keys, adjusted):
        results[c].setdefault("pvalues_holm", {})[k] = float(p)
    for c, r in results.items():
        r["verdict_raw"] = r["verdict"]
        r["verdict"] = decide(r["std_effect"], r["pvalues_holm"])
    sub_keys = [(c, s, k) for c in results for s in results[c]["sub_periods"] for k in TERMS]
    adjusted = st.holm([results[c]["sub_periods"][s]["pvalues"][k] for c, s, k in sub_keys])
    for (c, s, k), p in zip(sub_keys, adjusted):
        results[c]["sub_periods"][s].setdefault("pvalues_holm", {})[k] = float(p)
    for c in results:
        for part in results[c]["sub_periods"].values():
            part["verdict_raw"] = part["verdict"]
            part["verdict"] = decide(part["std_effect"], part["pvalues_holm"])


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = period_panel(long)
    panel.to_csv(out_dir / "period_panel.csv", float_format="%.4f")
    monthly_spreads(long).to_csv(out_dir / "yield_spreads_monthly.csv", float_format="%.2f")
    results = {}
    for c in REGRESSION_COUNTRIES:
        r = regression(panel, c)
        pd.DataFrame(r.pop("rolling")).to_csv(out_dir / f"rolling_{c}.csv", index=False, float_format="%.4f")
        results[c] = r
    apply_holm(results)
    summary = {"data_as_of": str(data.as_of(long).date()), "n_periods": int(len(panel)),
               "qt_start": str(QT_START.date()), "regressions": results, "labels": LABELS}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    path = out_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
