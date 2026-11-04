"""Chapter VI: does Japanese overnight pricing follow the BoJ out of negative rates?

Fixed in docs/METHODOLOGY.md, Phase 5. `run()` writes results/japan/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import data

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "japan"
START = pd.Timestamp("2016-02-16")
EXIT = pd.Timestamp("2024-03-21")
PRE_DAYS = 10
MAX_DAYS = 60
HAC_LAGS = 10


def frame(long: pd.DataFrame | None = None) -> pd.DataFrame:
    tona = data.get("tona", long)
    policy = data.get("boj_policy", long)
    collat = data.get("call_collat_on", long)
    df = pd.DataFrame({"tona": tona})
    df["policy"] = policy.reindex(policy.index.union(df.index)).ffill().reindex(df.index)
    df["collat"] = collat.reindex(df.index)
    return df.loc["2008-01-01":]


def policy_changes(long: pd.DataFrame | None = None) -> list[dict]:
    p = data.get("boj_policy", long)
    d = p.diff()
    out = []
    for day, change in d[(d.abs() > 1e-9) & (d.index >= START)].items():
        out.append({"date": day, "change": float(change), "new_rate": float(p[day])})
    return out


def half_gap_days(series: pd.Series, day: pd.Timestamp, change: float) -> dict:
    """Business days after `day` until the rate is within half the change of its new target."""
    s = series.dropna()
    before = s[s.index < day].iloc[-PRE_DAYS:]
    after = s[s.index >= day].iloc[:MAX_DAYS]
    if len(before) < PRE_DAYS // 2 or after.empty:
        return {"available": False}
    target = before.mean() + change
    close = (after - target).abs() <= abs(change) / 2
    days = int(np.argmax(close.to_numpy())) if close.any() else None
    return {"available": True, "pre_mean": float(before.mean()), "target": float(target),
            "half_gap_days": days, "after_20d_mean": float(after.iloc[:20].mean()),
            "pass_through_20d": float((after.iloc[:20].mean() - before.mean()) / change)}


def ecm(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> dict:
    sub = df.loc[start:end].dropna(subset=["tona", "policy"])
    y = sub["tona"].diff()
    X = pd.DataFrame({"gap_lag": (sub["tona"] - sub["policy"]).shift(1), "d_policy": sub["policy"].diff()})
    data_ = pd.concat([y.rename("d_tona"), X], axis=1).dropna()
    # With no policy change inside the sample the same-day pass-through is not identified: drop it.
    regressors = ["gap_lag", "d_policy"] if data_["d_policy"].abs().sum() > 0 else ["gap_lag"]
    res = sm.OLS(data_["d_tona"], sm.add_constant(data_[regressors])).fit(
        cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    g = float(res.params["gap_lag"])
    half_life = float(np.log(0.5) / np.log(1 + g)) if -1 < g < 0 else float("nan")
    return {"start": str(data_.index[0].date()), "end": str(data_.index[-1].date()), "n": int(len(data_)),
            "gamma": g, "gamma_p": float(res.pvalues["gap_lag"]),
            "beta": float(res.params["d_policy"]) if "d_policy" in res.params else None,
            "beta_se": float(res.bse["d_policy"]) if "d_policy" in res.params else None, "half_life_days": half_life,
            "n_changes": int((data_["d_policy"].abs() > 1e-9).sum()),
            "mean_gap_bp": float((sub["tona"] - sub["policy"]).mean() * 100)}


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = frame(long)
    df.to_csv(out_dir / "japan_daily.csv", float_format="%.4f")
    changes = []
    for ch in policy_changes(long):
        row = {"date": str(ch["date"].date()), "change_bp": ch["change"] * 100, "new_rate": ch["new_rate"]}
        for col in ("tona", "collat"):
            row[col] = half_gap_days(df[col], ch["date"], ch["change"])
        changes.append(row)
    summary = {"data_as_of": str(data.as_of(long).date()), "changes": changes,
               "ecm_full": ecm(df, START), "ecm_negative": ecm(df, START, EXIT - pd.Timedelta(days=1)),
               "ecm_exit": ecm(df, EXIT),
               "latest": {"date": str(df["tona"].dropna().index[-1].date()),
                          "tona": float(df["tona"].dropna().iloc[-1]), "policy": float(df["policy"].dropna().iloc[-1])}}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    path = out_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
