"""The forecasting engine (chapters V and VII): three quantile models, honest test-period evaluation,
the euro-vs-dollar turn comparison, the term-vs-overnight rule, and the frozen Year-End 2026 forecast.

Every choice here is fixed in docs/METHODOLOGY.md (Phase 2) before test results were computed.
Run `run()` (scripts/run_all.py does) to write results/forecast/. The frozen forecast is created
ONLY by scripts/freeze_forecast.py through `create_frozen_forecast`, which refuses to overwrite.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.regression.quantile_regression import QuantReg

import data
import features as F
import stats_tools as st

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "forecast"
FROZEN_PATH = ROOT / "results" / "forecasts" / "yearend_2026.json"
SCORE_PATH = ROOT / "results" / "forecasts" / "yearend_2026_score.json"

MODEL_VERSION = "forecast-v1"
QUANTILES = (0.05, 0.5, 0.9, 0.95)
TRAIN_END = pd.Timestamp("2022-12-31")
TEST_START = pd.Timestamp("2023-01-01")
MODELS = ("baseline", "calendar", "state")
MODEL_LABELS = {"baseline": "Baseline: same as the last comparable turn",
                "calendar": "Calendar-only quantile regression",
                "state": "Calendar + state quantile regression"}
FORECAST_CURRENCIES = ("EUR", "USD")      # the desk note's currencies
EVAL_CURRENCIES = ("USD", "EUR", "JPY")
YEAR_END = pd.Timestamp("2026-12-31")
YE_WINDOW = ("2026-12-21", "2027-01-08")
TURN_LOOKBACK = 10                        # business days before a turn used as its "normal" level
TERM_START_BD = 7                         # term trade starts 7 business days before the month-end
TERM_DAYS = 14                            # calendar days borrowed
NOTIONAL = 100e6


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def _design(X: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return pd.concat([pd.Series(1.0, index=X.index, name="const"), X[columns].astype(float)], axis=1)


def fit_qr(X: pd.DataFrame, y: pd.Series, columns: list[str], taus=QUANTILES) -> dict:
    """Quantile regression per tau. Columns constant on the fitting sample are dropped (not estimable)."""
    usable = [c for c in columns if X[c].nunique() > 1]
    D = _design(X, usable)
    params = {}
    for tau in taus:
        res = QuantReg(y.to_numpy(), D.to_numpy()).fit(q=tau, max_iter=5000)
        params[tau] = pd.Series(res.params, index=D.columns)
    return {"columns": usable, "params": params}


def predict_qr(model: dict, X: pd.DataFrame) -> pd.DataFrame:
    D = _design(X, model["columns"])
    out = pd.DataFrame({tau: D.to_numpy() @ model["params"][tau].to_numpy() for tau in model["params"]},
                       index=X.index)
    return _sort_quantiles(out)


def fit_baseline(X: pd.DataFrame, y: pd.Series, taus=QUANTILES) -> dict:
    errors = (y - X["baseline"]).dropna()  # days without an earlier comparable day are skipped
    return {"offsets": {tau: float(np.quantile(errors, tau)) for tau in taus}}


def predict_baseline(model: dict, X: pd.DataFrame) -> pd.DataFrame:
    return _sort_quantiles(pd.DataFrame({tau: X["baseline"] + off for tau, off in model["offsets"].items()},
                                        index=X.index))


def _sort_quantiles(pred: pd.DataFrame) -> pd.DataFrame:
    """Quantile forecasts that cross are sorted per day."""
    values = np.sort(pred.to_numpy(), axis=1)
    return pd.DataFrame(values, index=pred.index, columns=pred.columns)


def fit(model_name: str, currency: str, X: pd.DataFrame, y: pd.Series) -> dict:
    if model_name == "baseline":
        return {"kind": "baseline", **fit_baseline(X, y)}
    return {"kind": "qr", **fit_qr(X, y, F.feature_columns(currency, model_name))}


def predict(model: dict, X: pd.DataFrame) -> pd.DataFrame:
    return predict_baseline(model, X) if model["kind"] == "baseline" else predict_qr(model, X)


def dataset(currency: str, long: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """Features and target on every day where the regression inputs exist.

    The baseline column may be missing early on (no earlier comparable day yet); only the baseline
    model needs it, so only its fit drops those rows (corrected 2026-11-04, see METHODOLOGY.md).
    """
    y = F.target(currency, long)
    X = F.build(currency, y.index, long)
    keep = X[["level", "liq"]].notna().all(axis=1)
    return X[keep], y[keep]


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def is_turn(X: pd.DataFrame) -> pd.Series:
    return X["me"] == 1


def evaluate_currency(currency: str, long: pd.DataFrame | None = None) -> dict:
    X, y = dataset(currency, long)
    train = X.index <= TRAIN_END
    test = np.asarray((X.index >= TEST_START) & X["baseline"].notna())  # every model on the same test days
    preds, rows = {}, []
    for name in MODELS:
        model = fit(name, currency, X[train], y[train])
        preds[name] = predict(model, X[test])
    yt, Xt = y[test], X[test]
    turn = is_turn(Xt).to_numpy()
    losses = {}
    for name, p in preds.items():
        per_tau = {tau: st.pinball(yt, p[tau], tau) for tau in QUANTILES}
        mean_loss = np.mean(np.vstack(list(per_tau.values())), axis=0)
        losses[name] = mean_loss
        row = {"model": name, "label": MODEL_LABELS[name],
               "pinball_all": float(mean_loss.mean()), "pinball_turn": float(mean_loss[turn].mean())}
        for tau in QUANTILES:
            row[f"pinball_q{int(tau * 100):02d}"] = float(per_tau[tau].mean())
            row[f"pinball_turn_q{int(tau * 100):02d}"] = float(per_tau[tau][turn].mean())
            row[f"below_q{int(tau * 100):02d}"] = float((yt <= p[tau]).mean())
        row["interval_coverage"] = float(((yt >= p[0.05]) & (yt <= p[0.95])).mean())
        row["interval_coverage_turn"] = float(((yt >= p[0.05]) & (yt <= p[0.95]))[turn].mean())
        rows.append(row)
    for row in rows:
        if row["model"] == "baseline":
            continue
        dm_all = st.diebold_mariano(losses[row["model"]], losses["baseline"], F.HORIZON_BD)
        dm_turn = st.diebold_mariano(losses[row["model"]][turn], losses["baseline"][turn], 1)
        row.update({"dm_all_stat": dm_all["stat"], "dm_all_p": dm_all["p_value"],
                    "dm_turn_stat": dm_turn["stat"], "dm_turn_p": dm_turn["p_value"]})
    winner = min(rows, key=lambda r: r["pinball_turn"])["model"]
    test_pred = pd.concat({name: p for name, p in preds.items()}, axis=1)
    test_pred.columns = [f"{m}_q{int(t * 100):02d}" for m, t in test_pred.columns]
    test_pred.insert(0, "actual", yt)
    test_pred.insert(1, "day_type", Xt["day_type"])
    return {"currency": currency, "target": F.TARGET_LABEL[currency], "train_start": str(X.index[0].date()),
            "train_end": str(X.index[train][-1].date()), "test_start": str(X.index[test][0].date()),
            "test_end": str(X.index[-1].date()), "n_train": int(train.sum()), "n_test": int(test.sum()),
            "n_test_turn": int(turn.sum()), "models": rows, "winner": winner, "predictions": test_pred}


# --------------------------------------------------------------------------- #
# Turn effects: euro vs dollar
# --------------------------------------------------------------------------- #
def turn_effects(currency: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Target on each month-end minus the mean of the previous TURN_LOOKBACK published days (bp)."""
    y = F.target(currency, long)
    cal = F.calendar_features(y.index, currency, F._settlements_or_none() if currency == "USD" else None,
                              data.maintenance_period_ends(long) if currency == "EUR" else None)
    kinds = F.day_type(cal)
    rows = []
    positions = {d: i for i, d in enumerate(y.index)}
    for day in y.index[cal["me"] == 1]:
        i = positions[day]
        if i < TURN_LOOKBACK:
            continue
        normal = y.iloc[i - TURN_LOOKBACK:i].mean()
        rows.append({"date": day, "type": kinds[day], "turn": float(y.iloc[i]), "normal": float(normal),
                     "effect": float(y.iloc[i] - normal), "currency": currency})
    return pd.DataFrame(rows)


def turn_summary(effects: pd.DataFrame) -> dict:
    out = {}
    for kind in ("ye", "qe", "me"):
        sub = effects[effects["type"] == kind]["effect"]
        out[kind] = {"n": int(len(sub)), "mean": float(sub.mean()) if len(sub) else float("nan"),
                     "median": float(sub.median()) if len(sub) else float("nan"),
                     "share_up": float((sub > 0).mean()) if len(sub) else float("nan"),
                     "latest": float(sub.iloc[-1]) if len(sub) else float("nan")}
    return out


# --------------------------------------------------------------------------- #
# Term vs overnight (USD)
# --------------------------------------------------------------------------- #
def accrual(rate_pct: float, days: float) -> float:
    """USD interest on NOTIONAL at `rate_pct` (percent) for `days` calendar days, ACT/360."""
    return NOTIONAL * rate_pct / 100 * days / 360


def term_vs_overnight(evaluation: dict, long: pd.DataFrame | None = None) -> dict:
    on = data.get("repo_dvp_on", long)
    term = data.get("repo_dvp_term", long)
    lag = 1
    pred = evaluation["predictions"]
    winner = evaluation["winner"]
    median_col = f"{winner}_q50"
    y = F.target("USD", long)
    usd = data.bday("USD")
    month_ends = pred.index[pred["day_type"].isin(["me", "qe", "ye"])]
    rows = []
    for T in month_ends:
        S = T - TERM_START_BD * usd
        M = S + pd.Timedelta(days=TERM_DAYS)
        nights = on.loc[S:M - pd.Timedelta(days=1)]
        if len(nights) == 0 or S not in term.index or nights.index[0] != S:
            continue
        # Overnight cost: each night's rate applies until the next business day (weekends accrue).
        stops = list(nights.index[1:]) + [M]
        cost_on = sum(accrual(r, (b - a).days) for (a, r), b in zip(nights.items(), stops))
        cost_term = accrual(float(term[S]), TERM_DAYS)
        # Decision on S with data published by S.
        known_term = data.point_in_time(term, lag, pd.DatetimeIndex([S]), "USD").iloc[0]
        known_on = data.point_in_time(on, lag, pd.DatetimeIndex([S]), "USD").iloc[0]
        premium = (known_term - known_on) * 100
        window = pred.loc[S:M - pd.Timedelta(days=1), median_col]
        level = data.point_in_time(y, F.TARGET_LAG["USD"], pd.DatetimeIndex([S]), "USD").iloc[0]
        # Night-weighted, like the cost it is compared with (corrected 2026-11-05, METHODOLOGY.md U0).
        bdays = data.business_days("USD", S, M - pd.Timedelta(days=1))
        medians = window.reindex(bdays).ffill().bfill()
        weights = st.night_weights(bdays, M)
        spike = st.weighted_mean(medians.to_numpy(), weights) - level if len(window) else float("nan")
        lock = bool(spike > premium)
        rows.append({"turn": T, "start": S, "type": pred.loc[T, "day_type"], "premium_bp": float(premium),
                     "spike_bp": spike, "lock_term": lock, "cost_on": cost_on, "cost_term": cost_term,
                     "cost_rule": cost_term if lock else cost_on})
    df = pd.DataFrame(rows)
    totals = {k: float(df[f"cost_{k}"].sum()) for k in ("on", "term", "rule")} if len(df) else {}
    return {"model": winner, "n_windows": int(len(df)), "n_locked": int(df["lock_term"].sum()) if len(df) else 0,
            "totals": totals, "notional": NOTIONAL, "term_days": TERM_DAYS, "start_bd": TERM_START_BD,
            "saving_vs_on": totals.get("on", np.nan) - totals.get("rule", np.nan) if totals else float("nan"),
            "saving_vs_term": totals.get("term", np.nan) - totals.get("rule", np.nan) if totals else float("nan"),
            "windows": df}


STALE_TERM_BD = 20                        # METHODOLOGY.md, U0: older than this, the premium is stale


def term_staleness(term: pd.Series, as_of: pd.Timestamp) -> dict:
    """Date of the latest published term rate and its age in US business days at the as-of date."""
    last = term.dropna().index.max()
    age = max(len(data.business_days("USD", last, as_of)) - 1, 0)
    return {"latest_term_date": str(last.date()), "term_age_bd": int(age), "term_stale": bool(age > STALE_TERM_BD),
            "stale_after_bd": STALE_TERM_BD}


# --------------------------------------------------------------------------- #
# The Year-End 2026 forecast (frozen) and its score
# --------------------------------------------------------------------------- #
def yearend_forecast(currency: str, model_name: str, long: pd.DataFrame | None = None) -> dict:
    """Refit `model_name` on all data and forecast every business day of YE_WINDOW."""
    X, y = dataset(currency, long)
    model = fit(model_name, currency, X, y)
    as_of = data.as_of(long)
    days = data.business_days(currency, *YE_WINDOW)
    Xf = F.build(currency, days, long, cap=as_of)
    pred = predict(model, Xf)
    path = {str(d.date()): {f"q{int(t * 100):02d}": round(float(pred.loc[d, t]), 2) for t in QUANTILES} for d in days}
    head = pred.loc[YEAR_END] if YEAR_END in pred.index else pred.iloc[0]
    return {"model": model_name, "model_label": MODEL_LABELS[model_name],
            "target": F.TARGET_LABEL[currency], "unit": "bp",
            "turn_day": str(YEAR_END.date()), "origin": str(Xf.loc[YEAR_END, "origin"].date()),
            "q05": round(float(head[0.05]), 2), "q50": round(float(head[0.5]), 2),
            "q90": round(float(head[0.9]), 2), "q95": round(float(head[0.95]), 2),
            "latest_level": round(float(Xf.loc[YEAR_END, "level"]), 2), "path": path}


CODE_FILES = ("src/data.py", "src/features.py", "src/forecast.py", "src/stats_tools.py")


def code_hash() -> str:
    h = hashlib.sha256()
    for name in CODE_FILES:
        h.update((ROOT / name).read_bytes())
    return h.hexdigest()


def git_commit() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.strip()
        return commit + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def build_frozen(evaluations: dict, long: pd.DataFrame | None = None) -> dict:
    created = pd.Timestamp.now(tz="UTC").floor("s")
    return {
        "title": "Year-End 2026 funding forecast",
        "model_version": MODEL_VERSION,
        "data_as_of": str(data.as_of(long).date()),
        "created_at": str(created),
        "git_commit": git_commit(),
        "code_sha256": code_hash(),
        "quantiles": list(QUANTILES),
        "horizon_bd": F.HORIZON_BD,
        "selection_rule": "lowest mean pinball loss on test-period turn days",
        "currencies": {c: yearend_forecast(c, evaluations[c]["winner"], long) for c in FORECAST_CURRENCIES},
    }


def create_frozen_forecast(path: Path = FROZEN_PATH, long: pd.DataFrame | None = None) -> dict:
    """Write the frozen forecast ONCE. Raises FileExistsError if it already exists."""
    if path.exists():
        raise FileExistsError(f"{path} is frozen and must never be overwritten")
    evaluations = {c: evaluate_currency(c, long) for c in FORECAST_CURRENCIES}
    frozen = build_frozen(evaluations, long)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:  # "x": fails if the file appeared meanwhile
        json.dump(frozen, handle, indent=1)
    return frozen


def load_frozen(path: Path = FROZEN_PATH) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def score_yearend(frozen: dict, long: pd.DataFrame | None = None) -> dict | None:
    """Score each currency whose 31 Dec 2026 value is in the data; None if none is yet."""
    scores = {}
    for currency, fc in frozen["currencies"].items():
        y = F.target(currency, long)
        day = pd.Timestamp(fc["turn_day"])
        if day not in y.index:
            continue
        actual = float(y[day])
        losses = {f"q{int(t * 100):02d}": float(st.pinball(np.array([actual]), np.array([fc[f'q{int(t * 100):02d}']]),
                                                            t)[0]) for t in QUANTILES}
        scores[currency] = {"actual": round(actual, 2), "inside_interval": bool(fc["q05"] <= actual <= fc["q95"]),
                            "below_q90": bool(actual <= fc["q90"]), "pinball": losses,
                            "mean_pinball": float(np.mean(list(losses.values()))),
                            "error_vs_median": round(actual - fc["q50"], 2)}
    if not scores:
        return None
    return {"scored_at": str(pd.Timestamp.now(tz="UTC").floor("s")), "data_as_of": str(data.as_of(long).date()),
            "forecast_created_at": frozen["created_at"], "currencies": scores}


# --------------------------------------------------------------------------- #
# Run everything
# --------------------------------------------------------------------------- #
def _json_ready(obj):
    if isinstance(obj, dict):
        return {str(k): _json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_ready(v) for v in obj]
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    if isinstance(obj, (np.floating, float)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def adjust_dm(currencies: dict) -> None:
    """Holm-adjust the Diebold-Mariano p-values within F1 (turn days) and F2 (all days), in place (U2)."""
    for kind in ("turn", "all"):
        rows = [m for c in EVAL_CURRENCIES for m in currencies[c]["models"] if m["model"] != "baseline"]
        adjusted = st.holm([m[f"dm_{kind}_p"] for m in rows])
        for m, p in zip(rows, adjusted):
            m[f"dm_{kind}_p_holm"] = float(p)


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/forecast/* and, if the frozen forecast exists and can be scored, the score file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"model_version": MODEL_VERSION, "data_as_of": str(data.as_of(long).date()),
               "train_end": str(TRAIN_END.date()), "test_start": str(TEST_START.date()),
               "horizon_bd": F.HORIZON_BD, "currencies": {}}
    evaluations = {}
    for currency in EVAL_CURRENCIES:
        ev = evaluate_currency(currency, long)
        evaluations[currency] = ev
        ev["predictions"].to_csv(out_dir / f"test_predictions_{currency}.csv", float_format="%.3f")
        effects = turn_effects(currency, long)
        effects.to_csv(out_dir / f"turn_effects_{currency}.csv", index=False, float_format="%.3f")
        summary["currencies"][currency] = {k: v for k, v in ev.items() if k != "predictions"}
        summary["currencies"][currency]["turns"] = turn_summary(effects)
    adjust_dm(summary["currencies"])
    tvo = term_vs_overnight(evaluations["USD"], long)
    tvo["windows"].to_csv(out_dir / "term_vs_overnight_USD.csv", index=False, float_format="%.2f")
    as_of = data.as_of(long)
    day = pd.DatetimeIndex([as_of + data.bday("USD")])
    term_now = data.point_in_time(data.get("repo_dvp_term", long), 1, day, "USD").iloc[0]
    on_now = data.point_in_time(data.get("repo_dvp_on", long), 1, day, "USD").iloc[0]
    tvo["latest_premium_bp"] = float((term_now - on_now) * 100)
    tvo["latest_term_rate"], tvo["latest_on_rate"] = float(term_now), float(on_now)
    tvo.update(term_staleness(data.get("repo_dvp_term", long), as_of))
    summary["term_vs_overnight"] = {"USD": {k: v for k, v in tvo.items() if k != "windows"},
                                    "EUR": {"skipped": True,
                                            "reason": "no free daily euro term repo rate (see CLAUDE.md, Plan adjustments)"}}
    (out_dir / "summary.json").write_text(json.dumps(_json_ready(summary), indent=1), encoding="utf-8")
    frozen = load_frozen()
    if frozen is not None:
        score = score_yearend(frozen, long)
        if score is not None:
            SCORE_PATH.write_text(json.dumps(score, indent=1), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    path = out_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
