"""Uncertainty and multiple testing for every headline number (U2; choices fixed in docs/METHODOLOGY.md).

Reads only the results files written by the chapter modules (no refitting of the forecast models) and
writes results/inference/: `bootstrap.json` (moving-block 95% intervals), `tests.json` (every hypothesis
test with raw and Holm-adjusted p-values, by family) and `calibration.json` (coverage per quantile with
exact binomial intervals, PIT histograms and a verdict per currency).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import stats_tools as st

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT_DIR = RESULTS / "inference"

N_BOOT, SEED = 1000, 42
BLOCK_TEST_DAYS = 40          # = the forecast horizon
BLOCK_WEEKS = 8
BLOCK_PERIODS = 4             # maintenance periods
BLOCK_MONTHS = 6
BLOCK_JAPAN_DAYS = 20
QUANTILES = ("q05", "q50", "q90", "q95")
TAUS = {"q05": 0.05, "q50": 0.5, "q90": 0.9, "q95": 0.95}
TURN_TYPES = ("me", "qe", "ye")
PIT_BINS = ("below q05", "q05-q50", "q50-q90", "q90-q95", "above q95")
PIT_EXPECTED = (0.05, 0.45, 0.40, 0.05, 0.05)
NOMINAL_INTERVAL = 0.90
FIT_SPLIT = ("2010-01-01", "2023-12-01")      # France euro-wide beta (Phase 4 IV(a))
POLITICAL_MONTH = "2024-06-01"


def _read_json(rel: str) -> dict | None:
    path = RESULTS / rel
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _csv(rel: str, **kwargs) -> pd.DataFrame | None:
    path = RESULTS / rel
    return pd.read_csv(path, **kwargs) if path.exists() else None


# --------------------------------------------------------------------------- #
# Forecast losses and coverage
# --------------------------------------------------------------------------- #
def daily_losses(pred: pd.DataFrame, model: str) -> np.ndarray:
    """Per-day pinball loss averaged over the four quantiles."""
    y = pred["actual"].to_numpy()
    return np.mean([st.pinball(y, pred[f"{model}_{q}"].to_numpy(), TAUS[q]) for q in QUANTILES], axis=0)


def forecast_intervals(pred: pd.DataFrame, models: list[str]) -> dict:
    """Bootstrap intervals of the mean loss difference vs the baseline (all and turn days) and of coverage."""
    turn = pred["day_type"].isin(TURN_TYPES).to_numpy()
    base = daily_losses(pred, "baseline")
    y = pred["actual"].to_numpy()
    out = {}
    for m in models:
        loss = daily_losses(pred, m)
        diff = loss - base
        inside = ((y >= pred[f"{m}_q05"].to_numpy()) & (y <= pred[f"{m}_q95"].to_numpy())).astype(float)

        def turn_mean(idx, d=diff):
            sel = idx[turn[idx]]
            return float(d[sel].mean()) if len(sel) else float("nan")

        row = {"mean_diff_all": float(diff.mean()), "mean_diff_turn": float(diff[turn].mean()),
               "coverage": float(inside.mean())}
        if m != "baseline":
            row["ci_diff_all"] = st.block_bootstrap_ci(lambda i, d=diff: float(d[i].mean()), len(diff),
                                                       BLOCK_TEST_DAYS, N_BOOT, SEED)
            row["ci_diff_turn"] = st.block_bootstrap_ci(turn_mean, len(diff), BLOCK_TEST_DAYS, N_BOOT, SEED)
        row["ci_coverage"] = st.block_bootstrap_ci(lambda i, v=inside: float(v[i].mean()), len(inside),
                                                   BLOCK_TEST_DAYS, N_BOOT, SEED)
        out[m] = row
    return out


def calibration(pred: pd.DataFrame, model: str) -> dict:
    """Coverage per quantile (Clopper-Pearson), 5-95 coverage, PIT bins, and the verdict."""
    y = pred["actual"].to_numpy()
    n = len(y)
    per_q = {}
    for q in QUANTILES:
        k = int((y <= pred[f"{model}_{q}"].to_numpy()).sum())
        lo, hi = st.clopper_pearson(k, n)
        per_q[q] = {"nominal": TAUS[q], "share_below": k / n, "lower": lo, "upper": hi,
                    "verdict": "consistent" if lo <= TAUS[q] <= hi else ("too low" if hi < TAUS[q] else "too high")}
    q = {name: pred[f"{model}_{name}"].to_numpy() for name in QUANTILES}
    bins = np.select([y < q["q05"], y < q["q50"], y < q["q90"], y <= q["q95"]], [0, 1, 2, 3], default=4)
    observed = [float((bins == b).mean()) for b in range(5)]
    k_in = int(((y >= q["q05"]) & (y <= q["q95"])).sum())
    lo, hi = st.clopper_pearson(k_in, n)
    verdict = ("well calibrated" if lo <= NOMINAL_INTERVAL <= hi else
               "too narrow" if hi < NOMINAL_INTERVAL else "too wide")
    # Exact two-sided binomial test of 90% coverage (family F8)
    from scipy import stats as sps
    p_cov = float(sps.binomtest(k_in, n, NOMINAL_INTERVAL).pvalue)
    return {"model": model, "n": n, "per_quantile": per_q, "interval_coverage": k_in / n,
            "interval_lower": lo, "interval_upper": hi, "verdict": verdict, "p_coverage": p_cov,
            "pit": {"bins": list(PIT_BINS), "observed": observed, "expected": list(PIT_EXPECTED)}}


# --------------------------------------------------------------------------- #
# Reserves slope
# --------------------------------------------------------------------------- #
def slope_interval(pairs: pd.DataFrame, block: int = BLOCK_WEEKS) -> dict:
    x, y = pairs["liq"].to_numpy(), pairs["spread"].to_numpy()

    def slope(idx):
        return float(np.polyfit(x[idx], y[idx], 1)[0])

    return {"slope": slope(np.arange(len(x))), **st.block_bootstrap_ci(slope, len(x), block, N_BOOT, SEED)}


# --------------------------------------------------------------------------- #
# Credit vs scarcity
# --------------------------------------------------------------------------- #
def std_effects(df: pd.DataFrame, country: str) -> dict:
    """Standardised OLS effects (coefficient x sd of the regressor) and |credit| - (|liq| + |holdings|)."""
    cols = [f"credit_{country}", "liquidity", "de_holdings"]
    X = np.column_stack([np.ones(len(df)), df[cols].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, df[f"repo_{country}"].to_numpy(), rcond=None)
    sd = df[cols].std(ddof=1).to_numpy()
    eff = dict(zip(("credit", "liquidity", "de_holdings"), beta[1:] * sd))
    eff["difference"] = abs(eff["credit"]) - (abs(eff["liquidity"]) + abs(eff["de_holdings"]))
    return {k: float(v) for k, v in eff.items()}


def credit_scarcity_intervals(panel: pd.DataFrame, country: str, block: int = BLOCK_PERIODS) -> dict:
    df = panel[[f"repo_{country}", f"credit_{country}", "liquidity", "de_holdings"]].dropna()
    point = std_effects(df, country)
    out = {"point": point}
    for k in point:
        out[k] = st.block_bootstrap_ci(lambda i, key=k: std_effects(df.iloc[i], country)[key], len(df),
                                       block, N_BOOT, SEED)
    d = out["difference"]
    out["too_close_to_call"] = bool(d["lower"] <= 0 <= d["upper"]) if d["lower"] == d["lower"] else True
    return out


# --------------------------------------------------------------------------- #
# France-specific vs euro-wide
# --------------------------------------------------------------------------- #
def france_split_intervals(spreads: pd.DataFrame, fit_window: tuple[str, str] = FIT_SPLIT,
                           regressors: tuple[str, ...] = ("IT", "ES"), since: str = POLITICAL_MONTH,
                           with_ci: bool = True) -> dict:
    """Euro-wide vs France-specific split since `since` with bootstrap intervals over the fit sample."""
    d = spreads[["FR", *regressors]].dropna().diff().dropna()
    fit = d.loc[fit_window[0]:fit_window[1]]
    post = d.loc[since:]

    def split(idx):
        f = fit.iloc[idx]
        X = np.column_stack([np.ones(len(f)), f[list(regressors)].to_numpy()])
        b, *_ = np.linalg.lstsq(X, f["FR"].to_numpy(), rcond=None)
        euro = float((b[0] + post[list(regressors)].to_numpy() @ b[1:]).sum())
        total = float(post["FR"].sum())
        return euro, total - euro, (total - euro) / total if total else float("nan")

    e, f_, share = split(np.arange(len(fit)))
    out = {"cum_change": float(post["FR"].sum()), "euro_wide": e, "france_specific": f_, "share_france": share,
           "since": since[:7], "n_fit": int(len(fit))}
    if not with_ci:
        return out
    for j, name in enumerate(("euro_wide", "france_specific", "share_france")):
        out[f"ci_{name}"] = st.block_bootstrap_ci(lambda i, jj=j: split(i)[jj], len(fit), BLOCK_MONTHS, N_BOOT, SEED)
    return out


# --------------------------------------------------------------------------- #
# Japan half-lives
# --------------------------------------------------------------------------- #
def ecm_rows(daily: pd.DataFrame, start: str, end: str | None) -> pd.DataFrame:
    sub = daily.loc[start:end].dropna(subset=["tona", "policy"])
    return pd.DataFrame({"d_tona": sub["tona"].diff(), "gap_lag": (sub["tona"] - sub["policy"]).shift(1),
                         "d_policy": sub["policy"].diff()}).dropna()


def half_life(rows: pd.DataFrame, same_day: bool = True) -> float:
    """ln(0.5) / ln(1 + g) from the OLS error-correction coefficient g (NaN outside -1 < g < 0)."""
    cols = ["gap_lag", "d_policy"] if same_day and rows["d_policy"].abs().sum() > 0 else ["gap_lag"]
    X = np.column_stack([np.ones(len(rows)), rows[cols].to_numpy()])
    b, *_ = np.linalg.lstsq(X, rows["d_tona"].to_numpy(), rcond=None)
    g = b[1]
    return float(np.log(0.5) / np.log(1 + g)) if -1 < g < 0 else float("nan")


JAPAN_SAMPLES = {"negative": ("2016-02-16", "2024-03-20"), "exit": ("2024-03-21", None)}


def japan_intervals(daily: pd.DataFrame, samples: dict | None = None, block: int = BLOCK_JAPAN_DAYS,
                    same_day: bool = True) -> dict:
    """Half-life and its bootstrap interval for each sample (defaults: the Phase 5 sub-samples)."""
    out = {}
    for name, (start, end) in (samples or JAPAN_SAMPLES).items():
        rows = ecm_rows(daily, start, end)
        out[name] = {"half_life": half_life(rows, same_day), **st.block_bootstrap_ci(
            lambda i, r=rows: half_life(r.iloc[i], same_day), len(rows), block, N_BOOT, SEED)}
    return out


# --------------------------------------------------------------------------- #
# Every hypothesis test, by family, with Holm
# --------------------------------------------------------------------------- #
def test_registry(r: dict, calib: dict) -> list[dict]:
    """Every hypothesis test in the project (METHODOLOGY.md, U2), with its family and raw p-value."""
    tests = []
    fc, col, fr, jp = r.get("forecast"), r.get("collateral"), r.get("france"), r.get("japan")
    if fc:
        for c, cur in fc["currencies"].items():
            for m in cur["models"]:
                if m["model"] == "baseline":
                    continue
                tests.append({"family": "F1", "id": f"dm_turn_{c}_{m['model']}", "p": m.get("dm_turn_p"),
                              "what": f"{c} {m['model']} vs baseline, turn days (Diebold-Mariano)"})
                tests.append({"family": "F2", "id": f"dm_all_{c}_{m['model']}", "p": m.get("dm_all_p"),
                              "what": f"{c} {m['model']} vs baseline, all days (Diebold-Mariano)"})
    if col:
        for c, reg in col["regressions"].items():
            for k in ("credit", "liquidity", "de_holdings"):
                tests.append({"family": "F3", "id": f"coef_{c}_{k}", "p": reg["pvalues"][k],
                              "what": f"{c} collateral: {k} coefficient = 0 (HAC)"})
                for s, part in reg["sub_periods"].items():
                    tests.append({"family": "F4", "id": f"coef_{c}_{s}_{k}", "p": part["pvalues"][k],
                                  "what": f"{c} collateral, {s.replace('_', ' ')}: {k} coefficient = 0 (HAC)"})
            tests.append({"family": "F5", "id": f"chow_qt_{c}", "p": reg["chow"]["p_value"],
                          "what": f"{c} collateral regression: break at the start of QT (Chow)"})
    if fr:
        tests.append({"family": "F5", "id": "chow_june2024_fr_de", "p": fr["repo"]["chow_fr_de"]["p_value"],
                      "what": "FR-DE repo spread: break in June 2024 (Chow)"})
        tests.append({"family": "F5", "id": "chow_june2024_it_fr", "p": fr["repo"]["chow_it_fr"]["p_value"],
                      "what": "IT-FR repo gap: break in June 2024 (Chow)"})
        for k in ("IT", "ES"):
            tests.append({"family": "F6", "id": f"euro_beta_{k}", "p": fr["euro_wide"]["pvalues"][k],
                          "what": f"Euro-wide split: beta on {k} = 0 (HAC)"})
    if jp:
        for k in ("full", "negative", "exit"):
            tests.append({"family": "F7", "id": f"ecm_gamma_{k}", "p": jp[f"ecm_{k}"]["gamma_p"],
                          "what": f"Japan error correction ({k}): gap coefficient = 0 (HAC)"})
    for c, cal in calib.items():
        tests.append({"family": "F8", "id": f"coverage_{c}", "p": cal["p_coverage"],
                      "what": f"{c} {cal['model']}: 5-95% interval covers 90% (exact binomial)"})
    for fam in sorted({t["family"] for t in tests}):
        members = [t for t in tests if t["family"] == fam]
        adj = st.holm([np.nan if t["p"] is None else t["p"] for t in members])
        for t, a in zip(members, adj):
            t["p_holm"] = None if a != a else float(a)
            t["m"] = len(members)
    return tests


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def load_all() -> dict:
    """Every chapter summary this module reads."""
    return {"forecast": _read_json("forecast/summary.json"), "collateral": _read_json("collateral/summary.json"),
            "france": _read_json("france/summary.json"), "japan": _read_json("japan/summary.json"),
            "corridors": _read_json("corridors/summary.json")}


def run(out_dir: Path = OUT_DIR) -> dict:
    """Write results/inference/{bootstrap,tests,calibration}.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    r = load_all()
    boot, calib = {"settings": {"n_boot": N_BOOT, "seed": SEED, "level": 0.95}}, {}
    if r["forecast"]:
        boot["forecast"] = {}
        for c, cur in r["forecast"]["currencies"].items():
            pred = _csv(f"forecast/test_predictions_{c}.csv", index_col=0)
            models = [m["model"] for m in cur["models"]]
            boot["forecast"][c] = {"winner": cur["winner"], "block": BLOCK_TEST_DAYS,
                                   "models": forecast_intervals(pred, models)}
            calib[c] = calibration(pred, cur["winner"])
            calib[c]["by_model"] = {m: calibration(pred, m) for m in models}
    if r["corridors"]:
        boot["reserves_slope"] = {c: slope_interval(_csv(f"corridors/reserves_pairs_{c}.csv", index_col=0))
                                  for c in r["corridors"]["reserves"]}
    if r["collateral"]:
        panel = _csv("collateral/period_panel.csv", index_col=0)
        boot["credit_scarcity"] = {c: credit_scarcity_intervals(panel, c) for c in r["collateral"]["regressions"]}
    spreads = _csv("collateral/yield_spreads_monthly.csv", index_col=0, parse_dates=True)
    if spreads is not None:
        boot["france_split"] = france_split_intervals(spreads)
    jd = _csv("japan/japan_daily.csv", index_col=0, parse_dates=True)
    if jd is not None:
        boot["japan_half_life"] = japan_intervals(jd)
    tests = test_registry(r, {c: {k: v for k, v in cal.items() if k != "by_model"} for c, cal in calib.items()})
    (out_dir / "bootstrap.json").write_text(json.dumps(boot, indent=1), encoding="utf-8")
    (out_dir / "tests.json").write_text(json.dumps({"tests": tests}, indent=1), encoding="utf-8")
    (out_dir / "calibration.json").write_text(json.dumps(calib, indent=1), encoding="utf-8")
    return {"bootstrap": boot, "tests": tests, "calibration": calib}


def load(out_dir: Path = OUT_DIR) -> dict | None:
    """The three inference files, or None if missing."""
    files = {k: out_dir / f"{k}.json" for k in ("bootstrap", "tests", "calibration")}
    if not all(p.exists() for p in files.values()):
        return None
    return {k: json.loads(p.read_text(encoding="utf-8")) for k, p in files.items()}


if __name__ == "__main__":  # pragma: no cover
    run()
