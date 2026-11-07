"""Chapter II: policy corridors, regimes from the data, Markov regime switching, reserves vs spreads.

Choices are fixed in docs/METHODOLOGY.md, Phase 3. `run()` writes results/corridors/.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

import data
import features as F
import paths
import stats_tools as st

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = paths.RESULTS / "corridors"
TRAIN_END = pd.Timestamp("2022-12-31")
TEST_START = pd.Timestamp("2023-01-01")
PRESSURE_BP = 2.0
MARKOV_SEED = 0
BOOT_N, BOOT_BLOCK, BOOT_SEED = 500, 8, 42
KINK_GRID_N = 60          # grid points between the 5th and 95th percentile of reserves
KINK_EDGE_STEPS = 2       # a kink within this many grid steps of either end is at the boundary (U0)
KINK_EDGE_SHARE = 0.10    # more bootstrap kinks than this at the boundary: not identified (U0)
CASES = {"September 2019": ("2019-09-02", "2019-09-30"), "March 2020": ("2020-03-02", "2020-03-31"),
         "Year-end 2025": ("2025-12-01", "2026-01-09")}
LIQUIDITY = {"USD": ("reserves", 1e6, "reserve balances (USD trillion)"),
             "EUR": ("eur_liquidity", 1e3, "liquidity (EUR trillion)")}


# --------------------------------------------------------------------------- #
# Corridors and regime annotations
# --------------------------------------------------------------------------- #
def corridor_frame(currency: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily policy corridor and market rates (percent), from 2008."""
    if currency == "EUR":
        cols = {"floor": "dfr", "mro": "mro", "ceiling": "mlf", "market": "estr", "eonia": "eonia"}
    elif currency == "USD":
        cols = {"floor": "fed_lower", "ceiling": "fed_upper", "ior": "usd_ior", "market": "sofr", "effr": "effr"}
    else:
        cols = {"floor": "boj_policy", "ceiling": "boj_loan_rate", "market": "tona"}
    frame = pd.concat({k: data.get(v, long) for k, v in cols.items()}, axis=1).sort_index()
    policy_cols = [c for c in frame if c not in ("market", "eonia", "effr")]
    frame[policy_cols] = frame[policy_cols].ffill()
    return frame.loc["2008-01-01":]


def runs(mask: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """(start, end) of each run of True in a boolean daily series."""
    out, start, prev = [], None, None
    for day, flag in mask.items():
        if flag and start is None:
            start = day
        if not flag and start is not None:
            out.append((start, prev))
            start = None
        prev = day
    if start is not None:
        out.append((start, prev))
    return out


def policy_phases(policy: pd.Series) -> list[dict]:
    """Hiking and cutting phases: maximal runs of policy changes in one direction."""
    changes = policy.dropna().diff()
    changes = changes[changes.abs() > 1e-9]
    phases, current = [], None
    for day, change in changes.items():
        direction = "hiking" if change > 0 else "cutting"
        if current and current["kind"] == direction:
            current["end"], current["total"] = day, current["total"] + change
            current["n"] += 1
        else:
            if current:
                phases.append(current)
            current = {"kind": direction, "start": day, "end": day, "total": change, "n": 1}
    if current:
        phases.append(current)
    return phases


def regimes(currency: str, long: pd.DataFrame | None = None) -> list[dict]:
    """Regime annotations generated from the data."""
    frame = corridor_frame(currency, long)
    floor = frame["floor"].dropna()
    out = []
    policy = floor if currency != "USD" else frame["ior"].dropna()
    for start, end in runs(policy < 0):
        out.append({"kind": "negative rates", "start": start, "end": end})
    if currency == "USD":
        for start, end in runs(frame["ceiling"].dropna() <= 0.25):
            out.append({"kind": "zero lower bound", "start": start, "end": end})
    for phase in policy_phases(policy):
        if phase["n"] >= 2:
            out.append({"kind": phase["kind"], "start": phase["start"], "end": phase["end"],
                        "total_pp": float(phase["total"])})
    return sorted(out, key=lambda r: r["start"])


def corridor_stats(currency: str, long: pd.DataFrame | None = None, recent_days: int = 250) -> dict:
    """How tightly the market rate is held: share of days inside the corridor, spread to the floor."""
    frame = corridor_frame(currency, long).dropna(subset=["market", "floor", "ceiling"])
    inside = (frame["market"] >= frame["floor"] - 1e-9) & (frame["market"] <= frame["ceiling"] + 1e-9)
    y = F.target(currency, long)
    recent = y.iloc[-recent_days:]
    below = frame["market"] < frame["floor"] - 1e-9
    return {"start": str(frame.index[0].date()), "n_days": int(len(frame)), "inside_share": float(inside.mean()),
            "below_floor_share": float(below.mean()),
            "recent_median_bp": float(recent.median()), "recent_p95_bp": float(recent.quantile(0.95)),
            "recent_iqr_bp": float(recent.quantile(0.75) - recent.quantile(0.25)),
            "corridor_width_bp": float((frame["ceiling"] - frame["floor"]).iloc[-1] * 100),
            "latest_spread_bp": float(y.iloc[-1]), "latest_date": str(y.index[-1].date())}


# --------------------------------------------------------------------------- #
# Markov regime switching
# --------------------------------------------------------------------------- #
def fit_markov(y: pd.Series) -> dict:
    """Two-regime switching mean and variance, fitted on the train period, filtered on all days."""
    y = y.astype(float)
    train = y[y.index <= TRAIN_END]
    np.random.seed(MARKOV_SEED)  # search_reps draws random starting values: fix them for reproducibility
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_train = MarkovRegression(train.to_numpy(), k_regimes=2, trend="c", switching_variance=True)
        res = model_train.fit(search_reps=20, disp=False, maxiter=500, rng=MARKOV_SEED)
        params = res.params
        full = MarkovRegression(y.to_numpy(), k_regimes=2, trend="c", switching_variance=True)
        filtered = full.filter(params)
    # Parameter order: p[0->0], p[1->0], const0, const1, sigma2_0, sigma2_1
    names = full.param_names
    p = dict(zip(names, params, strict=False))
    var = [p["sigma2[0]"], p["sigma2[1]"]]
    stressed = int(np.argmax(var))
    probs = pd.Series(filtered.filtered_marginal_probabilities[:, stressed], index=y.index)
    llf_obs = pd.Series(filtered.llf_obs, index=y.index)
    test = y.index >= TEST_START
    mu, sd = train.mean(), train.std(ddof=1)
    normal_ll = stats.norm.logpdf(y[test], mu, sd)
    by_year = (probs[test] > 0.5).groupby(probs[test].index.year).mean()
    return {
        "stressed_regime": stressed,
        "mean_bp": {"calm": float(p[f"const[{1 - stressed}]"]), "stressed": float(p[f"const[{stressed}]"])},
        "sd_bp": {"calm": float(np.sqrt(var[1 - stressed])), "stressed": float(np.sqrt(var[stressed]))},
        "test_ll_per_day": float(llf_obs[test].mean()), "normal_ll_per_day": float(normal_ll.mean()),
        "share_stressed_train": float((probs[~test] > 0.5).mean()),
        "share_stressed_test": float((probs[test] > 0.5).mean()),
        "share_stressed_by_year": {int(k): float(v) for k, v in by_year.items()},
        "latest_probability": float(probs.iloc[-1]), "latest_date": str(probs.index[-1].date()),
        "probabilities": probs,
    }


# --------------------------------------------------------------------------- #
# Reserves vs spread
# --------------------------------------------------------------------------- #
def weekly_pairs(currency: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Weekly liquidity level and the mean spread over the following week."""
    name, scale, _ = LIQUIDITY[currency]
    liq = (data.get(name, long) / scale).dropna()
    y = F.target(currency, long)
    rows = []
    for day, level in liq.items():
        nxt = y[(y.index > day) & (y.index <= day + pd.Timedelta(days=7))]
        if len(nxt) >= 3:
            rows.append({"date": day, "liq": float(level), "spread": float(nxt.mean())})
    return pd.DataFrame(rows).set_index("date")


def fit_linear(x: np.ndarray, y: np.ndarray) -> dict:
    """Least-squares line spread = a + b x (params [a, b])."""
    b, a = np.polyfit(x, y, 1)
    return {"kind": "linear", "params": [float(a), float(b)]}


def predict_linear(m: dict, x: np.ndarray) -> np.ndarray:
    """Fitted spread of a linear model at x."""
    a, b = m["params"]
    return a + b * x


def fit_piecewise(x: np.ndarray, y: np.ndarray) -> dict:
    """y = a + b*x + c*max(k - x, 0): an extra slope below the kink k (scarcity)."""
    grid = kink_grid(x)
    best = None
    for k in grid:
        X = np.column_stack([np.ones_like(x), x, np.maximum(k - x, 0)])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        ssr = float(np.sum((y - X @ beta) ** 2))
        if best is None or ssr < best[0]:
            best = (ssr, k, beta)
    _, k, beta = best
    return {"kind": "piecewise", "params": [float(v) for v in beta], "kink": float(k)}


def kink_grid(x: np.ndarray) -> np.ndarray:
    """Candidate kinks: KINK_GRID_N points from the 5th to the 95th percentile of x."""
    return np.linspace(np.quantile(x, 0.05), np.quantile(x, 0.95), KINK_GRID_N)


def at_grid_edge(kink: float, x: np.ndarray) -> bool:
    """True if `kink` is within KINK_EDGE_STEPS grid steps of either end of x's grid."""
    grid = kink_grid(x)
    tol = KINK_EDGE_STEPS * (grid[1] - grid[0]) + 1e-12
    return bool(kink <= grid[0] + tol or kink >= grid[-1] - tol)


def predict_piecewise(m: dict, x: np.ndarray) -> np.ndarray:
    """Fitted spread of a one-kink piecewise model at x."""
    a, b, c = m["params"]
    return a + b * x + c * np.maximum(m["kink"] - x, 0)


def _logistic(x: np.ndarray, low: float, high: float, mid: float, scale: float) -> np.ndarray:
    return low + (high - low) / (1 + np.exp((x - mid) / scale))


def fit_logistic(x: np.ndarray, y: np.ndarray) -> dict:
    """S-shape: high spread when reserves are scarce, a plateau (low) when they are abundant."""
    p0 = [np.quantile(y, 0.1), np.quantile(y, 0.95), np.median(x), max(np.std(x) / 4, 1e-3)]
    try:
        params, _ = optimize.curve_fit(_logistic, x, y, p0=p0, maxfev=20000,
                                       bounds=([-50, -50, x.min() - 2, 1e-3], [50, 400, x.max() + 2, 5]))
    except Exception:
        params = np.array(p0)
    return {"kind": "logistic", "params": [float(v) for v in params]}


def predict_logistic(m: dict, x: np.ndarray) -> np.ndarray:
    """Fitted spread of the S-shaped model at x."""
    return _logistic(x, *m["params"])


FITS = {"linear": (fit_linear, predict_linear), "piecewise": (fit_piecewise, predict_piecewise),
        "logistic": (fit_logistic, predict_logistic)}


def pressure_point(m: dict) -> float:
    """Reserve level where pressure starts (see METHODOLOGY.md)."""
    if m["kind"] == "piecewise":
        return m["kink"]
    if m["kind"] == "logistic":
        low, high, mid, scale = m["params"]
        if high - low <= PRESSURE_BP:
            return float("nan")
        # low + (high-low)/(1+e^z) = low + PRESSURE_BP  ->  e^z = (high-low)/PRESSURE_BP - 1
        return float(mid + scale * np.log((high - low) / PRESSURE_BP - 1))
    return float("nan")


def reserves_analysis(currency: str, long: pd.DataFrame | None = None) -> dict:
    """Linear, piecewise and logistic fits chosen out of sample, the slope and the kink.

    The kink comes with its bootstrap band and the U0 identification check.
    """
    pairs = weekly_pairs(currency, long)
    name, scale, _ = LIQUIDITY[currency]
    latest_day, latest_liq = data.latest(data.get(name, long) / scale)
    train = pairs[pairs.index <= TRAIN_END]
    test = pairs[pairs.index >= TEST_START]
    results = {}
    for name, (fitter, predictor) in FITS.items():
        m = fitter(train["liq"].to_numpy(), train["spread"].to_numpy())
        rmse = float(np.sqrt(np.mean((predictor(m, test["liq"].to_numpy()) - test["spread"].to_numpy()) ** 2)))
        results[name] = {"train_model": m, "test_rmse": rmse}
    winner = min(results, key=lambda k: results[k]["test_rmse"])
    fitter, predictor = FITS[winner]
    x, y = pairs["liq"].to_numpy(), pairs["spread"].to_numpy()
    full = fitter(x, y)
    # Where pressure starts: from the winning threshold model; if the linear fit wins, the piecewise
    # kink is still reported as a reference (the out-of-sample test did not support a threshold).
    threshold_kind = winner if winner != "linear" else "piecewise"
    threshold_model = full if winner != "linear" else fit_piecewise(x, y)
    point = pressure_point(threshold_model)
    boot, edge = [], []
    for idx in st.bootstrap_indices(len(x), BOOT_N, BOOT_SEED, BOOT_BLOCK):
        b = pressure_point(FITS[threshold_kind][0](x[idx], y[idx]))
        boot.append(b)
        if threshold_kind == "piecewise" and b == b:
            edge.append(at_grid_edge(b, x[idx]))
    boot = np.array([b for b in boot if b == b])
    # Identification (METHODOLOGY.md, U0): a kink at the edge of the search grid is not a threshold.
    edge_share = float(np.mean(edge)) if edge else 0.0
    point_at_edge = threshold_kind == "piecewise" and point == point and at_grid_edge(point, x)
    identified = bool(point == point and not point_at_edge and edge_share <= KINK_EDGE_SHARE)
    grid = np.linspace(x.min(), x.max(), 80)
    curve = pd.DataFrame({"liq": grid, "fit": predictor(full, grid),
                          "threshold_fit": FITS[threshold_kind][1](threshold_model, grid)})
    return {"currency": currency, "label": LIQUIDITY[currency][2], "n_weeks": len(pairs),
            "n_train": len(train), "n_test": len(test),
            "test_rmse": {k: v["test_rmse"] for k, v in results.items()}, "winner": winner,
            "full_model": full, "pressure_point": point, "pressure_from": threshold_kind,
            "slope_per_unit": float(fit_linear(x, y)["params"][1]),
            "pressure_band": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))] if len(boot) > 20
            else [float("nan"), float("nan")],
            "kink_identified": identified, "kink_at_grid_edge": bool(point_at_edge),
            "boot_edge_share": edge_share, "kink_grid": [float(kink_grid(x)[0]), float(kink_grid(x)[-1])],
            # "latest" = the latest published value (data.latest), the same number as the desk overview; the
            # regression's last week (it needs a following week of spreads) is kept separately.
            "latest_liq": latest_liq, "latest_date": str(latest_day.date()),
            "last_pair_liq": float(x[-1]), "last_pair_date": str(pairs.index[-1].date()),
            "pairs": pairs, "curve": curve}


# --------------------------------------------------------------------------- #
# Case studies
# --------------------------------------------------------------------------- #
def case_studies(long: pd.DataFrame | None = None) -> list[dict]:
    """Peak spread, its date and the pre-window level for each fixed episode and currency."""
    out = []
    for name, (start, end) in CASES.items():
        for currency in ("USD", "EUR", "JPY"):
            y = F.target(currency, long)
            window = y.loc[start:end]
            if window.empty:
                continue
            before = y[y.index < start].iloc[-10:]
            row = {"case": name, "currency": currency, "start": start, "end": end,
                   "peak_bp": float(window.max()), "peak_date": str(window.idxmax().date()),
                   "trough_bp": float(window.min()), "before_bp": float(before.mean()),
                   "peak_vs_before_bp": float(window.max() - before.mean())}
            if currency in LIQUIDITY:
                lname, scale, label = LIQUIDITY[currency]
                liq = data.get(lname, long) / scale
                row["liquidity"] = float(liq[liq.index <= start].iloc[-1]) if (liq.index <= start).any() else None
                row["liquidity_label"] = label
            out.append(row)
    return out


def _clean(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items() if not isinstance(v, (pd.DataFrame, pd.Series))}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return str(obj.date())
    if isinstance(obj, (float, np.floating)):
        return None if obj != obj else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/corridors/ (corridor frames, regimes, Markov probabilities, reserves curves, summary)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"data_as_of": str(data.as_of(long).date()), "regimes": {}, "markov": {}, "reserves": {}}
    probs = {}
    for currency in ("EUR", "USD", "JPY"):
        frame = corridor_frame(currency, long)
        frame.to_csv(out_dir / f"corridor_{currency}.csv", float_format="%.4f")
        summary["regimes"][currency] = regimes(currency, long)
        summary.setdefault("stats", {})[currency] = corridor_stats(currency, long)
        mk = fit_markov(F.target(currency, long))
        probs[currency] = mk["probabilities"]
        summary["markov"][currency] = mk
    pd.DataFrame(probs).to_csv(out_dir / "stress_probability.csv", float_format="%.4f")
    for currency in LIQUIDITY:
        ra = reserves_analysis(currency, long)
        ra["pairs"].to_csv(out_dir / f"reserves_pairs_{currency}.csv", float_format="%.4f")
        ra["curve"].to_csv(out_dir / f"reserves_curve_{currency}.csv", index=False, float_format="%.4f")
        summary["reserves"][currency] = ra
    summary["cases"] = case_studies(long)
    (out_dir / "summary.json").write_text(json.dumps(_clean(summary), indent=1), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    """The saved chapter II summary, or None if it has not been written."""
    path = out_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
