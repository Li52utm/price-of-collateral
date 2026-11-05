"""Small statistical tools shared by several chapters (pure functions; tests/test_stats_tools.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def pinball(y: np.ndarray, q_forecast: np.ndarray, tau: float) -> np.ndarray:
    """Pinball (quantile) loss per observation: tau*(y-q) if y >= q else (1-tau)*(q-y)."""
    diff = np.asarray(y, dtype=float) - np.asarray(q_forecast, dtype=float)
    return np.where(diff >= 0, tau * diff, (tau - 1) * diff)


def newey_west_variance(x: np.ndarray, lags: int) -> float:
    """Long-run variance of the mean of x (Bartlett kernel)."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    lags = min(lags, n - 1)
    gamma0 = np.dot(x, x) / n
    total = gamma0
    for k in range(1, lags + 1):
        weight = 1 - k / (lags + 1)
        total += 2 * weight * np.dot(x[k:], x[:-k]) / n
    return total


def diebold_mariano(loss_model: np.ndarray, loss_base: np.ndarray, horizon: int) -> dict:
    """DM test of equal predictive accuracy, with the Harvey-Leybourne-Newbold correction.

    d = loss_model - loss_base: a negative mean means the model is more accurate than the base.
    Variance: Newey-West with horizon - 1 lags. Two-sided p-value from Student t with n - 1 df.
    """
    d = np.asarray(loss_model, dtype=float) - np.asarray(loss_base, dtype=float)
    d = d[~np.isnan(d)]
    n = len(d)
    if n < 10:
        return {"n": n, "mean_diff": float("nan"), "stat": float("nan"), "p_value": float("nan")}
    var = newey_west_variance(d, horizon - 1)
    if var <= 0:
        return {"n": n, "mean_diff": float(d.mean()), "stat": float("nan"), "p_value": float("nan")}
    stat = d.mean() / np.sqrt(var / n)
    h = horizon
    correction = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n) if n + 1 - 2 * h > 0 else 1.0
    stat *= correction
    p = 2 * stats.t.sf(abs(stat), df=n - 1)
    return {"n": n, "mean_diff": float(d.mean()), "stat": float(stat), "p_value": float(p)}


def chow_test(y: np.ndarray, X: np.ndarray, split: int) -> dict:
    """Chow test for a break after observation `split` (X includes the constant). F and p-value."""
    y, X = np.asarray(y, float), np.asarray(X, float)
    k = X.shape[1]

    def ssr(yy, XX):
        beta, *_ = np.linalg.lstsq(XX, yy, rcond=None)
        r = yy - XX @ beta
        return float(r @ r)

    n = len(y)
    if split <= k or n - split <= k:
        return {"F": float("nan"), "p_value": float("nan"), "n1": split, "n2": n - split}
    s_all, s1, s2 = ssr(y, X), ssr(y[:split], X[:split]), ssr(y[split:], X[split:])
    F = ((s_all - s1 - s2) / k) / ((s1 + s2) / (n - 2 * k))
    return {"F": float(F), "p_value": float(stats.f.sf(F, k, n - 2 * k)), "n1": split, "n2": n - split}


def bootstrap_indices(n: int, n_boot: int, seed: int = 42, block: int = 1) -> np.ndarray:
    """(n_boot, n) resampling indices; moving blocks of length `block` (1 = iid)."""
    rng = np.random.default_rng(seed)
    if block <= 1:
        return rng.integers(0, n, size=(n_boot, n))
    starts = rng.integers(0, max(n - block + 1, 1), size=(n_boot, int(np.ceil(n / block))))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    return np.minimum(idx, n - 1)


def night_weights(days: pd.DatetimeIndex, end: pd.Timestamp) -> np.ndarray:
    """Calendar nights each business day's overnight rate applies for, up to `end` (exclusive).

    A rate set on a business day applies until the next business day (weekends and holidays accrue at
    the last rate), so Thursday 31 December 2026 covers four nights to Monday 4 January 2027.
    `days` must be every business day of the window, in order.
    """
    days = pd.DatetimeIndex(days)
    if len(days) == 0:
        return np.array([])
    stops = list(days[1:]) + [pd.Timestamp(end)]
    return np.array([max((b - a).days, 0) for a, b in zip(days, stops)], dtype=float)


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted mean; NaN when the weights sum to zero."""
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    total = weights.sum()
    return float((values * weights).sum() / total) if total > 0 else float("nan")


def summary_quantiles(x: pd.Series | np.ndarray, qs=(0.05, 0.5, 0.95)) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    return {f"q{int(q * 100):02d}": float(np.quantile(x, q)) for q in qs} if len(x) else {}


def holm(p_values) -> np.ndarray:
    """Holm step-down adjusted p-values (same order as the input; NaN stays NaN).

    Sort the m valid p-values ascending; adjusted p_(i) = max over j <= i of min(1, (m - j + 1) p_(j)).
    """
    p = np.asarray(p_values, dtype=float)
    out = np.full(p.shape, np.nan)
    valid = np.where(~np.isnan(p))[0]
    m = len(valid)
    if m == 0:
        return out
    order = valid[np.argsort(p[valid], kind="mergesort")]
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


def block_bootstrap_ci(statistic, n: int, block: int, n_boot: int = 1000, seed: int = 42,
                       level: float = 0.95) -> dict:
    """Percentile interval of `statistic(idx)` over moving-block resamples of 0..n-1.

    `statistic` takes an index array and returns a float (NaN results are dropped and counted).
    """
    draws = np.array([statistic(idx) for idx in bootstrap_indices(n, n_boot, seed, block)], dtype=float)
    ok = draws[~np.isnan(draws)]
    tail = (1 - level) / 2
    if len(ok) < max(20, n_boot // 10):
        return {"lower": float("nan"), "upper": float("nan"), "n_boot": n_boot, "n_valid": int(len(ok)),
                "block": block}
    return {"lower": float(np.quantile(ok, tail)), "upper": float(np.quantile(ok, 1 - tail)), "n_boot": n_boot,
            "n_valid": int(len(ok)), "block": block}


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact binomial confidence interval for a proportion k / n."""
    if n == 0:
        return float("nan"), float("nan")
    a = (1 - level) / 2
    lower = 0.0 if k == 0 else float(stats.beta.ppf(a, k, n - k + 1))
    upper = 1.0 if k == n else float(stats.beta.ppf(1 - a, k + 1, n - k))
    return lower, upper
