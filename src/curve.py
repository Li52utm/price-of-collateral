"""D5: does France carry extra curve steepness relative to Germany? Daily 2s10s for both countries.

Main measure: constant-maturity yields on both sides (Webstat TEC2 and TEC10; the Bundesbank's Svensson 2-year
and 10-year), so the comparison is like for like (see D0). Sensitivity: the current German 2-year and 10-year
bonds. Choices: docs/METHODOLOGY.md, "Desk upgrade D5". `run()` writes results/france/curve.json and
curve_daily.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data
import paths

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = paths.RESULTS / "france"
REFERENCE = ("2010-01-01", "2023-12-31")
BASE_DAY = pd.Timestamp("2024-06-07")      # last business day before the dissolution (the daily decomposition base)
CHART_FROM = "2024-01-01"


def curve_frame(fr2: pd.Series, fr10: pd.Series, de2: pd.Series, de10: pd.Series) -> pd.DataFrame:
    """Daily 2s10s for France and Germany, the excess French steepness and its two legs (bp)."""
    f = pd.concat([fr2, fr10, de2, de10], axis=1, keys=["fr2", "fr10", "de2", "de10"], sort=True).dropna()
    out = pd.DataFrame(index=f.index)
    out["fr_2s10s"] = (f["fr10"] - f["fr2"]) * 100
    out["de_2s10s"] = (f["de10"] - f["de2"]) * 100
    out["excess"] = out["fr_2s10s"] - out["de_2s10s"]
    out["spread10"] = (f["fr10"] - f["de10"]) * 100
    out["spread2"] = (f["fr2"] - f["de2"]) * 100
    return out


def percentile_of(value: float, ref: pd.Series) -> float:
    """Share of reference values at or below `value` (0 to 1)."""
    ref = ref.dropna()
    return float((ref <= value).mean()) if len(ref) else float("nan")


def steepness_verdict(latest: float, ref_p95: float) -> str:
    """'unusual', 'within range' or 'none' (pre-registered rule, METHODOLOGY.md D5)."""
    if latest <= 0:
        return "none"
    return "unusual" if latest > ref_p95 else "within range"


def summarise(c: pd.DataFrame, reference: tuple[str, str] = REFERENCE, base_day: pd.Timestamp = BASE_DAY) -> dict:
    """Latest values, the reference distribution and the change since the base day."""
    ref = c.loc[reference[0]:reference[1], "excess"]
    last = c.iloc[-1]
    base = c[c.index <= base_day].iloc[-1]
    p95 = float(ref.quantile(0.95))
    change = {k: float(last[k] - base[k]) for k in ("excess", "spread10", "spread2", "fr_2s10s", "de_2s10s")}
    return {"latest_date": str(c.index[-1].date()), "latest": {k: float(v) for k, v in last.items()},
            "base_date": str(c[c.index <= base_day].index[-1].date()), "base": {k: float(v) for k, v in base.items()},
            "change_since_base": change,
            "reference": {"start": reference[0], "end": reference[1], "n": int(len(ref)), "mean": float(ref.mean()),
                          "p05": float(ref.quantile(0.05)), "p95": p95},
            "latest_percentile": percentile_of(float(last["excess"]), ref),
            "verdict": steepness_verdict(float(last["excess"]), p95),
            "larger_leg": "10-year" if abs(change["spread10"]) >= abs(change["spread2"]) else "2-year"}


def analyse(long: pd.DataFrame | None = None) -> tuple[dict, pd.DataFrame]:
    """Main (constant maturity) and sensitivity (current German bonds) summaries, and the main daily frame."""
    g = lambda n: data.get(n, long)  # noqa: E731
    main = curve_frame(g("oat2_daily"), g("oat10_daily"), g("bund2_cm"), g("bund10_cm"))
    sens = curve_frame(g("oat2_daily"), g("oat10_daily"), g("bund2_daily"), g("bund10_daily"))
    out = {"data_as_of": str(data.as_of(long).date()), "main": summarise(main),
           "sensitivity_current_bonds": summarise(sens)}
    return out, main


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/france/curve.json and curve_daily.csv (from CHART_FROM)."""
    out, main = analyse(long)
    out_dir.mkdir(parents=True, exist_ok=True)
    main.loc[CHART_FROM:].to_csv(out_dir / "curve_daily.csv", float_format="%.2f", index_label="date")
    (out_dir / "curve.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
