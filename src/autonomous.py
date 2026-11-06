"""D2: autonomous factors. Do swings in Treasury cash at the central bank move overnight funding?

Euro: liabilities to other euro area residents at the Eurosystem (mostly government deposits; see
docs/METHODOLOGY.md, "Desk upgrade D2", for why the parent item is used). Dollar: the Treasury General
Account. Weekly changes in the spread to the policy rate are regressed on weekly changes in Treasury cash,
controlling for the change in liquidity (euro proxy) or reserve balances. Train to 2022, test 2023 on.
`run()` writes results/desk/autonomous.json and autonomous_weekly_<CUR>.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import data
import features as F
import stats_tools as st

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "desk"
TRAIN_END = pd.Timestamp("2022-12-31")
HAC_LAGS = 4
BOOT_N, BOOT_BLOCK, BOOT_SEED = 1000, 8, 42
MIN_DAYS = 3
SCALE = 1e5          # USD mn / EUR mn -> 100 bn
CASH = {"EUR": "ea_resident_liab", "USD": "tga_weekly"}
LIQ = {"EUR": "eur_liquidity", "USD": "reserves"}
LIQ_SCALE = {"EUR": 100.0, "USD": SCALE}     # eur_liquidity is already in EUR bn
POLICY = {"EUR": "dfr", "USD": "usd_ior"}
COLUMNS = ["d_spread", "d_cash", "d_liq"]


def weekly_spread(y: pd.Series, week_ends: pd.DatetimeIndex, min_days: int = MIN_DAYS) -> pd.Series:
    """Mean of the daily spread over the days after the previous week end up to and including each week end."""
    out = {}
    for prev, end in zip(week_ends[:-1], week_ends[1:], strict=True):
        days = y[(y.index > prev) & (y.index <= end)]
        if len(days) >= min_days:
            out[end] = float(days.mean())
    return pd.Series(out, dtype=float)


def weekly_dataset(currency: str, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per statement week: levels and week-on-week changes (spread bp, cash and liquidity in 100 bn).

    Every value in row w is dated on or before the week end w (tests/test_point_in_time.py).
    """
    cash = data.get(CASH[currency], long).dropna() / SCALE
    liq = data.get(LIQ[currency], long).dropna() / LIQ_SCALE[currency]
    y = F.target(currency, long)
    weeks = cash.index.intersection(liq.index)
    weeks = weeks[weeks >= y.index[0] - pd.Timedelta(days=7)]
    spread = weekly_spread(y, weeks)
    frame = pd.DataFrame({"spread": spread, "cash": cash.reindex(spread.index), "liq": liq.reindex(spread.index)})
    # Changes only between consecutive statement weeks (a missing week would otherwise give a two-week change).
    gap = frame.index.to_series().diff().dt.days
    frame["d_spread"] = frame["spread"].diff()
    frame["d_cash"] = frame["cash"].diff()
    frame["d_liq"] = frame["liq"].diff()
    frame = frame[gap.between(5, 9)]
    return frame.dropna()


def ols(frame: pd.DataFrame, lags: int = HAC_LAGS) -> dict:
    """d_spread on d_cash and d_liq with Newey-West errors."""
    X = sm.add_constant(frame[["d_cash", "d_liq"]].to_numpy())
    res = sm.OLS(frame["d_spread"].to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    names = ["const", "cash", "liq"]
    return {"n": int(len(frame)), "coef": dict(zip(names, map(float, res.params), strict=True)),
            "se": dict(zip(names, map(float, res.bse), strict=True)),
            "p": dict(zip(names, map(float, res.pvalues), strict=True)), "r2": float(res.rsquared)}


def coef_vector(frame: pd.DataFrame) -> np.ndarray:
    """OLS coefficients [const, cash, liq] (plain least squares, for the bootstrap)."""
    X = np.column_stack([np.ones(len(frame)), frame["d_cash"].to_numpy(), frame["d_liq"].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, frame["d_spread"].to_numpy(), rcond=None)
    return beta


def bootstrap_ci(frame: pd.DataFrame, n_boot: int = BOOT_N, block: int = BOOT_BLOCK, seed: int = BOOT_SEED) -> dict:
    """95% moving-block bootstrap intervals of the cash and liquidity coefficients."""
    draws = np.array([coef_vector(frame.iloc[idx]) for idx in st.bootstrap_indices(len(frame), n_boot, seed, block)])
    return {name: [float(np.quantile(draws[:, i], 0.025)), float(np.quantile(draws[:, i], 0.975))]
            for i, name in ((1, "cash"), (2, "liq"))}


def out_of_sample(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Train-fitted predictions of d_spread on test weeks against the no-change baseline (d_spread = 0)."""
    beta = coef_vector(train)
    pred = beta[0] + beta[1] * test["d_cash"] + beta[2] * test["d_liq"]
    sse_model = float(((test["d_spread"] - pred) ** 2).sum())
    sse_base = float((test["d_spread"] ** 2).sum())
    return {"n_test": int(len(test)), "rmse_model": float(np.sqrt(sse_model / len(test))),
            "rmse_no_change": float(np.sqrt(sse_base / len(test))),
            "r2_oos": float(1 - sse_model / sse_base) if sse_base else float("nan")}


def verdict(ci: list[float], r2_oos: float) -> str:
    """'matters', 'some evidence' or 'no clear effect' (pre-registered rule, METHODOLOGY.md D2)."""
    excludes = ci[0] > 0 or ci[1] < 0
    beats = r2_oos > 0
    if excludes and beats:
        return "matters"
    if excludes or beats:
        return "some evidence"
    return "no clear effect"


def policy_change_weeks(currency: str, weeks: pd.DatetimeIndex, long: pd.DataFrame | None = None) -> pd.DatetimeIndex:
    """Statement weeks that contain a change in the policy rate (for the sensitivity)."""
    policy = data.get(POLICY[currency], long).dropna()
    changes = policy.index[policy.diff().abs() > 1e-9]
    out = []
    for prev, end in zip(weeks[:-1], weeks[1:], strict=True):
        if ((changes > prev) & (changes <= end)).any():
            out.append(end)
    return pd.DatetimeIndex(out)


def analyse_currency(currency: str, long: pd.DataFrame | None = None) -> tuple[dict, pd.DataFrame]:
    """Train and full-sample fits, bootstrap intervals, the out-of-sample comparison and the sensitivity."""
    frame = weekly_dataset(currency, long)
    train, test = frame[frame.index <= TRAIN_END], frame[frame.index > TRAIN_END]
    full = ols(frame)
    full["ci"] = bootstrap_ci(frame)
    tr = ols(train)
    tr["ci"] = bootstrap_ci(train)
    oos = out_of_sample(train, test)
    drop = policy_change_weeks(currency, frame.index, long)
    sens = ols(frame[~frame.index.isin(drop)])
    latest = frame.iloc[-1]
    return ({"currency": currency, "cash_series": CASH[currency], "liq_series": LIQ[currency],
             "first_week": str(frame.index[0].date()), "last_week": str(frame.index[-1].date()),
             "train": tr, "full": full, "oos": oos, "verdict": verdict(full["ci"]["cash"], oos["r2_oos"]),
             "without_policy_weeks": {**sens, "n_dropped": int(len(drop))},
             "latest": {"week": str(frame.index[-1].date()), "cash_100bn": float(latest["cash"]),
                        "d_cash_100bn": float(latest["d_cash"]), "spread_bp": float(latest["spread"])},
             "cash_sd_100bn": float(frame["d_cash"].std(ddof=1))}, frame)


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/desk/autonomous.json and the weekly data sets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {"data_as_of": str(data.as_of(long).date()), "currencies": {}}
    for cur in ("EUR", "USD"):
        res, frame = analyse_currency(cur, long)
        out["currencies"][cur] = res
        frame.to_csv(out_dir / f"autonomous_weekly_{cur}.csv", float_format="%.4f", index_label="date")
    # Holm family F9 (METHODOLOGY.md D2): the two full-sample HAC tests of the Treasury-cash coefficient.
    curs = list(out["currencies"])
    adj = st.holm([out["currencies"][c]["full"]["p"]["cash"] for c in curs])
    for c, p_adj in zip(curs, adj, strict=True):
        out["currencies"][c]["full"]["p_cash_holm"] = float(p_adj)
    gov = data.get("gov_deposits", long).dropna()
    if len(gov):
        out["eur_government_deposits"] = {"date": str(gov.index[-1].date()), "eur_bn": float(gov.iloc[-1] / 1e3)}
    tga = data.get("tga_daily", long).dropna()
    if len(tga):
        out["usd_tga_daily"] = {"date": str(tga.index[-1].date()), "usd_bn": float(tga.iloc[-1] / 1e3)}
    (out_dir / "autonomous.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
