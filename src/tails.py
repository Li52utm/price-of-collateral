"""Why the frozen forecast's 90th and 95th percentiles are almost identical (diagnosis only).

The frozen file results/forecasts/yearend_2026.json is never read for writing here. This module refits
the winning model with the current code on the same data, recomputes the 31 December 2026 quantiles
WITHOUT sorting, and records which year-end days pin the upper quantiles (docs/METHODOLOGY.md, U0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import data
import features as F
import forecast as fc

OUT_PATH = fc.OUT_DIR / "tail_diagnosis.json"
ZERO_TOL = 1e-6           # a residual this small means the quantile fit passes through the observation


def raw_turn_quantiles(model: dict, currency: str, long: pd.DataFrame | None = None) -> dict[float, float]:
    """31 December 2026 quantiles from the fitted model, before the per-day sorting step."""
    days = data.business_days(currency, *fc.YE_WINDOW)
    Xf = F.build(currency, days, long, cap=data.as_of(long))
    D = fc._design(Xf.loc[[fc.YEAR_END]], model["columns"])
    return {tau: float((D.to_numpy() @ model["params"][tau].to_numpy())[0]) for tau in fc.QUANTILES}


def diagnose(currency: str, model_name: str = "state", long: pd.DataFrame | None = None) -> dict:
    """Year-end count, raw quantiles, crossing, and the year-ends each upper quantile passes through."""
    X, y = fc.dataset(currency, long)
    model = fc.fit(model_name, currency, X, y)
    raw = raw_turn_quantiles(model, currency, long)
    ye = (X["ye"] == 1).to_numpy()
    D = fc._design(X, model["columns"]).to_numpy()
    pinned, above = {}, {}
    for tau in (0.9, 0.95):
        resid = y.to_numpy() - D @ model["params"][tau].to_numpy()
        ye_resid = resid[ye]
        pinned[tau] = [str(d.date()) for d, r in zip(X.index[ye], ye_resid) if abs(r) < ZERO_TOL]
        above[tau] = int((ye_resid > ZERO_TOL).sum())
    n_ye = int(ye.sum())
    return {
        "currency": currency, "model": model_name, "n_year_ends": n_ye,
        "year_ends": [str(d.date()) for d in X.index[ye]],
        "raw_q": {f"q{int(t * 100):02d}": round(v, 2) for t, v in raw.items()},
        "crossing_90_95": bool(raw[0.9] > raw[0.95]),
        "gap_90_95_raw": round(raw[0.95] - raw[0.9], 2),
        "pinned_q90": pinned[0.9], "pinned_q95": pinned[0.95],
        "same_pins": pinned[0.9] == pinned[0.95],
        "year_end_params": 2,                         # `ye` and `ye_liq` are fitted on year-end days only
        "n_above_q90": above[0.9], "n_above_q95": above[0.95],
        # With n year-ends, a quantile above (n-1)/n leaves no year-end above the fit: both tails hit the top.
        "max_separable_tau": round((n_ye - 1) / n_ye, 3) if n_ye else float("nan"),
    }


def run(long: pd.DataFrame | None = None, path: Path = OUT_PATH) -> dict:
    """Write results/forecast/tail_diagnosis.json for the desk note's two currencies."""
    frozen = fc.load_frozen()
    out = {"data_as_of": str(data.as_of(long).date()), "currencies": {}}
    for currency in fc.FORECAST_CURRENCIES:
        model_name = frozen["currencies"][currency]["model"] if frozen else "state"
        d = diagnose(currency, model_name, long)
        if frozen:
            f = frozen["currencies"][currency]
            d["frozen_q"] = {k: f[k] for k in ("q05", "q50", "q90", "q95")}
        out["currencies"][currency] = d
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load(path: Path = OUT_PATH) -> dict | None:
    """The saved diagnosis, or None."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(run(), indent=1))
