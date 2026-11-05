"""Kaplan-Meier survival curves with Greenwood confidence bands (lifelines would force pandas 2.x).

`kaplan_meier(durations, observed)` returns, at each distinct event time, the survival estimate
S(t) = prod over event times t_i <= t of (1 - d_i / n_i), its Greenwood standard error, and a 95%
band on the log(-log) scale (which stays inside [0, 1]). Tests: tests/test_france.py (hand-computed).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy import stats


def kaplan_meier(durations: Sequence[float] | np.ndarray | pd.Series,
                 observed: Sequence[bool] | np.ndarray | pd.Series, alpha: float = 0.05) -> pd.DataFrame:
    """Columns: time, at_risk, events, censored, survival, se, lower, upper (time 0 row first)."""
    t = np.asarray(durations, dtype=float)
    e = np.asarray(observed, dtype=bool)
    z = stats.norm.ppf(1 - alpha / 2)
    rows = [{"time": 0.0, "at_risk": len(t), "events": 0, "censored": 0, "survival": 1.0, "se": 0.0,
             "lower": 1.0, "upper": 1.0}]
    s, greenwood = 1.0, 0.0
    for time in np.unique(t):
        at_risk = int((t >= time).sum())
        d = int(((t == time) & e).sum())
        c = int(((t == time) & ~e).sum())
        if d:
            s *= 1 - d / at_risk
            greenwood += d / (at_risk * (at_risk - d)) if at_risk > d else np.inf
        se = s * np.sqrt(greenwood) if np.isfinite(greenwood) else np.nan
        if 0 < s < 1 and np.isfinite(greenwood) and greenwood > 0:
            # log(-log S) band (Kalbfleisch-Prentice)
            v = np.sqrt(greenwood) / abs(np.log(s))
            lower, upper = s ** np.exp(z * v), s ** np.exp(-z * v)
        else:
            lower = upper = s
        rows.append({"time": float(time), "at_risk": at_risk, "events": d, "censored": c, "survival": s,
                     "se": se, "lower": lower, "upper": upper})
    return pd.DataFrame(rows)


def survival_at(km: pd.DataFrame, time: float) -> dict:
    """S(t) and its band at `time` (step function: last row with time <= t)."""
    row = km[km["time"] <= time].iloc[-1]
    return {"time": time, "survival": float(row["survival"]), "lower": float(row["lower"]),
            "upper": float(row["upper"]), "at_risk": int(km[km["time"] >= time]["at_risk"].max())
            if (km["time"] >= time).any() else 0}


def median_time(km: pd.DataFrame) -> float:
    """First time at which S(t) <= 0.5 (NaN if never reached)."""
    below = km[km["survival"] <= 0.5]
    return float(below["time"].iloc[0]) if len(below) else float("nan")
