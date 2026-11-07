"""The challenger forecast v2 (U4): conformalised quantile regression plus a year-end analogue distribution.

Fixed in docs/METHODOLOGY.md, "Upgrade U4", before any v2 result was computed. v2 was designed AFTER
seeing v1's test-period calibration, so its test-period results are not a clean out-of-sample claim; its
clean test is the 31 December 2026 score. v1 (src/forecast.py) remains the pre-registered headline.

`run()` writes results/forecast/v2_summary.json (test period, labelled) and the past year-end turns;
`create_frozen_v2()` (only via scripts/freeze_forecast.py --version v2) writes the frozen file once.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import data
import features as F
import forecast as fc
import paths
import stats_tools as st

ROOT = fc.ROOT
FROZEN_V2_PATH = paths.RESULTS / "forecasts" / "yearend_2026_v2.json"
SCORE_V2_PATH = paths.RESULTS / "forecasts" / "yearend_2026_v2_score.json"
SUMMARY_PATH = fc.OUT_DIR / "v2_summary.json"
TURNS_PATH = fc.OUT_DIR / "past_year_ends.csv"
MODEL_VERSION = "forecast-v2"
FIT_END = pd.Timestamp("2021-12-31")
CALIBRATION = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31"))
TEST_START = fc.TEST_START
PRODUCTION_FIT_END = pd.Timestamp("2025-12-31")
CODE_FILES = ("src/data.py", "src/features.py", "src/forecast.py", "src/forecast_v2.py", "src/stats_tools.py")
LABEL = "Conformalised quantile regression (CQR), with a year-end analogue distribution for the turn"
CAVEAT = ("designed after seeing v1's test-period calibration, so these test-period results are not a clean "
          "out-of-sample claim; the clean test is the 31 December 2026 score")


# --------------------------------------------------------------------------- #
# (a) CQR
# --------------------------------------------------------------------------- #
def day_class(X: pd.DataFrame) -> np.ndarray:
    """'turn' for month-, quarter- and year-ends, else 'ordinary'."""
    return np.where(X["me"].to_numpy() == 1, "turn", "ordinary")


def conformal_offset(scores: np.ndarray, tau: float) -> float:
    """One-sided split-conformal adjustment for quantile `tau` (finite-sample corrected order statistic)."""
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    if n == 0:
        return 0.0
    if tau >= 0.5:
        k = math.ceil((n + 1) * tau)
        return float(s[min(k, n) - 1])
    k = math.floor((n + 1) * tau)
    return float(s[max(k, 1) - 1])


def fit_cqr(currency: str, X: pd.DataFrame, y: pd.Series, fit_end: pd.Timestamp,
            cal: tuple[pd.Timestamp, pd.Timestamp]) -> dict:
    """Base QR on days to `fit_end`; per-class, per-quantile offsets from the calibration days."""
    base = fc.fit("state", currency, X[X.index <= fit_end], y[y.index <= fit_end])
    in_cal = (X.index >= cal[0]) & (X.index <= cal[1])
    Xc, yc = X[in_cal], y[in_cal]
    raw = fc.predict(base, Xc)
    classes = day_class(Xc)
    offsets = {}
    for c in ("turn", "ordinary"):
        sel = classes == c
        offsets[c] = {tau: conformal_offset(yc[sel].to_numpy() - raw[tau].to_numpy()[sel], tau) for tau in fc.QUANTILES}
    return {"base": base, "offsets": offsets, "n_cal": {c: int((classes == c).sum()) for c in ("turn", "ordinary")}}


def predict_cqr(model: dict, X: pd.DataFrame) -> pd.DataFrame:
    """CQR quantiles: base forecasts plus the per-class conformal offsets (sorted per day)."""
    raw = fc.predict(model["base"], X)
    classes = day_class(X)
    adj = pd.DataFrame({tau: [model["offsets"][c][tau] for c in classes] for tau in fc.QUANTILES}, index=X.index)
    return fc._sort_quantiles(raw + adj)


# --------------------------------------------------------------------------- #
# (b) Year-end analogue
# --------------------------------------------------------------------------- #
def past_year_ends(currency: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every past year-end: the target, the level at its forecast origin, and the jump between them."""
    X, y = fc.dataset(currency, long)
    ye = X[X["ye"] == 1]
    out = pd.DataFrame({"currency": currency, "actual": y[ye.index], "level_at_origin": ye["level"]})
    out["jump"] = out["actual"] - out["level_at_origin"]
    return out


def analogue_quantiles(jumps: np.ndarray, level: float) -> dict[float, float]:
    """Latest level + the empirical quantiles of past jumps."""
    return {tau: float(level + np.quantile(np.asarray(jumps, dtype=float), tau)) for tau in fc.QUANTILES}


# --------------------------------------------------------------------------- #
# Test period (labelled: not a clean out-of-sample claim)
# --------------------------------------------------------------------------- #
def evaluate(currency: str, long: pd.DataFrame | None = None) -> dict:
    """CQR vs v1 (state) vs baseline on v1's test days; analogue on the 2023-2025 year-ends."""
    X, y = fc.dataset(currency, long)
    cqr = fit_cqr(currency, X, y, FIT_END, CALIBRATION)
    test = (X.index >= TEST_START) & X["baseline"].notna()
    Xt, yt = X[test], y[test]
    preds = {"cqr": predict_cqr(cqr, Xt),
             "v1_state": fc.predict(fc.fit("state", currency, X[X.index <= fc.TRAIN_END], y[y.index <= fc.TRAIN_END]),
                                    Xt),
             "baseline": fc.predict(fc.fit("baseline", currency, X[X.index <= fc.TRAIN_END],
                                           y[y.index <= fc.TRAIN_END]), Xt)}
    turn = (Xt["me"] == 1).to_numpy()
    rows = {}
    for name, p in preds.items():
        loss = np.mean([st.pinball(yt, p[t], t) for t in fc.QUANTILES], axis=0)
        inside = ((yt >= p[0.05]) & (yt <= p[0.95])).to_numpy()
        k, n = int(inside.sum()), len(inside)
        lo, hi = st.clopper_pearson(k, n)
        verdict = "well calibrated" if lo <= 0.9 <= hi else "too narrow" if hi < 0.9 else "too wide"
        rows[name] = {"pinball_all": float(loss.mean()), "pinball_turn": float(loss[turn].mean()),
                      "coverage": k / n, "coverage_lower": lo, "coverage_upper": hi, "verdict": verdict,
                      "coverage_turn": float(inside[turn].mean()),
                      "below": {f"q{int(t * 100):02d}": float((yt <= p[t]).mean()) for t in fc.QUANTILES}}
    turns = past_year_ends(currency, long)
    analogue = []
    for day in turns.index[turns.index >= TEST_START]:
        prior = turns[turns.index < day]
        q = analogue_quantiles(prior["jump"].to_numpy(), float(turns.loc[day, "level_at_origin"]))
        actual = float(turns.loc[day, "actual"])
        analogue.append({"date": str(day.date()), "n_prior": int(len(prior)), "actual": actual,
                         **{f"q{int(t * 100):02d}": v for t, v in q.items()},
                         "inside": bool(q[0.05] <= actual <= q[0.95]),
                         "pinball": float(np.mean([st.pinball(np.array([actual]), np.array([q[t]]), t)[0]
                                                   for t in fc.QUANTILES]))})
    return {"currency": currency, "label": LABEL, "caveat": CAVEAT, "fit_end": str(FIT_END.date()),
            "calibration": [str(CALIBRATION[0].date()), str(CALIBRATION[1].date())], "n_cal": cqr["n_cal"],
            "offsets": {c: {f"q{int(t * 100):02d}": v for t, v in o.items()} for c, o in cqr["offsets"].items()},
            "n_test": int(len(yt)), "n_test_turn": int(turn.sum()), "models": rows, "analogue_test": analogue}


# --------------------------------------------------------------------------- #
# The 2026 forecast
# --------------------------------------------------------------------------- #
def yearend_forecast_v2(currency: str, long: pd.DataFrame | None = None) -> dict:
    """v2 path for the year-end window: CQR, with the analogue quantiles on 31 December."""
    X, y = fc.dataset(currency, long)
    as_of = data.as_of(long)
    cqr = fit_cqr(currency, X, y, PRODUCTION_FIT_END, (PRODUCTION_FIT_END + pd.Timedelta(days=1), as_of))
    days = data.business_days(currency, *fc.YE_WINDOW)
    Xf = F.build(currency, days, long, cap=as_of)
    pred = predict_cqr(cqr, Xf)
    turns = past_year_ends(currency, long)
    level = float(Xf.loc[fc.YEAR_END, "level"])
    q_ye = analogue_quantiles(turns["jump"].to_numpy(), level)
    for t, v in q_ye.items():
        pred.loc[fc.YEAR_END, t] = v
    path = {str(d.date()): {f"q{int(t * 100):02d}": round(float(pred.loc[d, t]), 2) for t in fc.QUANTILES}
            for d in days}
    head = pred.loc[fc.YEAR_END]
    return {"model": "cqr+analogue", "model_label": LABEL, "target": F.TARGET_LABEL[currency], "unit": "bp",
            "turn_day": str(fc.YEAR_END.date()), "origin": str(Xf.loc[fc.YEAR_END, "origin"].date()),
            "q05": round(float(head[0.05]), 2), "q50": round(float(head[0.5]), 2),
            "q90": round(float(head[0.9]), 2), "q95": round(float(head[0.95]), 2),
            "latest_level": round(level, 2), "n_year_ends": int(len(turns)),
            "calibration_days": cqr["n_cal"], "path": path}


def code_hash() -> str:
    """SHA-256 of the files the v2 forecast depends on."""
    h = hashlib.sha256()
    for name in CODE_FILES:
        h.update((ROOT / name).read_bytes())
    return h.hexdigest()


def build_frozen_v2(long: pd.DataFrame | None = None) -> dict:
    """The frozen v2 forecast dictionary (metadata, caveat and each currency's path)."""
    return {"title": "Year-End 2026 funding forecast (challenger v2)", "model_version": MODEL_VERSION,
            "data_as_of": str(data.as_of(long).date()), "created_at": str(pd.Timestamp.now(tz="UTC").floor("s")),
            "git_commit": fc.git_commit(), "code_sha256": code_hash(), "code_files": list(CODE_FILES),
            "quantiles": list(fc.QUANTILES), "horizon_bd": F.HORIZON_BD,
            "status": "challenger: " + CAVEAT + "; v1 (yearend_2026.json) is the pre-registered headline",
            "currencies": {c: yearend_forecast_v2(c, long) for c in fc.FORECAST_CURRENCIES}}


def create_frozen_v2(path: Path = FROZEN_V2_PATH, long: pd.DataFrame | None = None) -> dict:
    """Write the frozen v2 forecast ONCE. Raises FileExistsError if it already exists."""
    if path.exists():
        raise FileExistsError(f"{path} is frozen and must never be overwritten")
    frozen = build_frozen_v2(long)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(frozen, handle, indent=1)
    return frozen


def load_frozen_v2(path: Path = FROZEN_V2_PATH) -> dict | None:
    """The frozen v2 forecast, or None if it does not exist."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def run(long: pd.DataFrame | None = None) -> dict:
    """Write the labelled test-period evaluation, the past year-end turns, and the v2 score once possible."""
    summary = {"model_version": MODEL_VERSION, "caveat": CAVEAT,
               "currencies": {c: evaluate(c, long) for c in fc.FORECAST_CURRENCIES}}
    pd.concat([past_year_ends(c, long) for c in ("USD", "EUR")]).to_csv(TURNS_PATH, float_format="%.3f")
    SUMMARY_PATH.write_text(json.dumps(fc._json_ready(summary), indent=1), encoding="utf-8")
    frozen = load_frozen_v2()
    if frozen is not None:
        score = fc.score_yearend(frozen, long)
        if score is not None:
            SCORE_V2_PATH.write_text(json.dumps(score, indent=1), encoding="utf-8")
    return summary


def load_summary(path: Path = SUMMARY_PATH) -> dict | None:
    """The saved v2 test-period summary, or None."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
