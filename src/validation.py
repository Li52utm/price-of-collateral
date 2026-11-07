"""Data validation: PASS / WARN / FAIL checks on the snapshot (or on a fresh download before it is written).

    PASS  the data agrees with the reference or the expected property holds
    WARN  a documented difference with no material effect on results
    FAIL  the data is wrong: scripts/refresh_snapshots.py stops before writing anything

Each check is a pure function of the long frame (date, series, value) and returns a dict
{"name", "status", "detail"}. Thresholds are constants below. Tests: tests/test_validation.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import data
import sources

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
STATUS_ORDER = {PASS: 0, WARN: 1, FAIL: 2}

COVERAGE_PASS, COVERAGE_WARN = 0.98, 0.95   # share of the calendar's business days present
RATE_RANGE = (-1.5, 12.0)                   # money-market and policy rates, percent
YIELD_RANGE = (-1.5, 40.0)                  # 10-year sovereign yields (Greece reached 29% in 2012)
MMSR_RANGE = (-5.0, 12.0)                   # collateral-specific repo: bonds trading special can go deeply
                                            # negative (Dutch 1-week repo -2.66% in April 2019)
JPY_COVERAGE_PASS = 0.95                    # moving Japanese holidays (about 6 a year) count as gaps
NEGATIVE_DFR = ("2014-06-11", "2022-07-26")  # ECB deposit rate below zero (inclusive)
NEGATIVE_BOJ = ("2016-02-16", "2024-03-20")  # BoJ negative interest rate policy
EONIA_SPREAD = 0.085                        # EONIA = €STR + 8.5 bp from 2 Oct 2019
BUND_MONTHLY_PASS, BUND_MONTHLY_WARN = 0.10, 0.25  # mean |daily-average - IRS| in pp
OAT_MONTHLY_PASS, OAT_MONTHLY_WARN = 0.10, 0.25    # same yardstick for the Webstat TEC10 vs ECB IRS France
LIQUIDITY_GAP = 25.0                        # EUR bn: |proxy - excess liquidity - reserve requirements|
TONA_POLICY_PASS = 0.10                     # median |TONA - policy| after 2016, pp
STALE_EXTRA_BD = 7                          # tolerated business days beyond the publication lag
DISCONTINUED = {"eonia", "ioer", "y10_GR"}  # not expected to be recent (y10_GR may lag a month)
SPOT_CHECKS = [  # (series, date, value, tolerance): published values checked by hand
    ("estr", "2019-10-01", -0.549, 0.0005),   # first €STR publication
    ("sofr", "2019-09-17", 5.25, 0.005),      # September 2019 repo spike
    ("dfr", "2023-09-20", 4.00, 0.0001),      # peak of the 2022-23 hiking cycle
    ("dfr", "2019-09-18", -0.50, 0.0001),
    ("iorb", "2021-07-29", 0.15, 0.0001),     # first IORB day
]


def result(name: str, status: str, detail: str) -> dict:
    """One check result {name, status, detail}; the status must be PASS, WARN or FAIL."""
    if status not in STATUS_ORDER:
        raise ValueError(f"status must be one of {list(STATUS_ORDER)}, got {status!r}")
    return {"name": name, "status": status, "detail": detail}


def worst(statuses: list[str]) -> str:
    """The most severe status in a list (FAIL over WARN over PASS)."""
    return max(statuses, key=STATUS_ORDER.get) if statuses else PASS


def _s(long: pd.DataFrame, name: str) -> pd.Series:
    return data.get(name, long)


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def coverage_share(s: pd.Series, currency: str) -> tuple[float, int]:
    """(share of business days present, longest run of missing business days) between first and last date."""
    days = data.business_days(currency, s.index.min(), s.index.max())
    present = days.isin(s.index)
    gaps, run = 0, 0
    for p in present:
        run = 0 if p else run + 1
        gaps = max(gaps, run)
    return float(present.mean()), gaps


def check_calendar(long: pd.DataFrame,
                   names: tuple[str, ...] = ("estr", "sofr", "tona", "dfr", "bund10_daily", "oat10_daily")) -> dict:
    """Share of business days present and the longest gap, per key daily series."""
    lines, statuses = [], []
    for name in names:
        share, gap = coverage_share(_s(long, name), data.currency_of(name))
        need = JPY_COVERAGE_PASS if data.currency_of(name) == "JPY" else COVERAGE_PASS
        status = PASS if share >= need else WARN if share >= need - 0.03 else FAIL
        statuses.append(status)
        lines.append(f"{name} {share:.1%} of business days (longest gap {gap})")
    detail = "; ".join(lines) + ". The Japanese calendar omits moving holidays, so a few count as gaps."
    return result("Calendar coverage", worst(statuses), detail)


def check_ranges(long: pd.DataFrame) -> dict:
    """Every rate and yield inside its plausible range; no negative volumes."""
    rate_names = [s.name for s in sources.ALL_SERIES if s.unit == "%"]
    bad = []
    for name in rate_names:
        s = _s(long, name)
        low, high = YIELD_RANGE if name.startswith(("y10_", "bund", "oat")) else RATE_RANGE
        if s.empty:
            bad.append(f"{name} empty")
        elif s.min() < low or s.max() > high:
            bad.append(f"{name} {s.min():.2f}..{s.max():.2f}")
    mmsr = long[long["series"].str.startswith("mmsr_rate")]["value"]
    if len(mmsr) and (mmsr.min() < MMSR_RANGE[0] or mmsr.max() > MMSR_RANGE[1]):
        bad.append(f"MMSR rates {mmsr.min():.2f}..{mmsr.max():.2f}")
    volumes = long[long["series"].str.contains("volume")]["value"]
    if (volumes < 0).any():
        bad.append("negative volume")
    if bad:
        return result("Ranges", FAIL, "; ".join(bad))
    return result("Ranges", PASS, f"{len(rate_names)} rate series within {RATE_RANGE[0]}%..{RATE_RANGE[1]}% "
                                  f"(yields {YIELD_RANGE[0]}%..{YIELD_RANGE[1]}%); MMSR collateral-specific rates "
                                  f"{mmsr.min():.2f}%..{mmsr.max():.2f}% (specials allowed down to {MMSR_RANGE[0]}%); "
                                  "no negative volumes.")


def check_negative_rates(long: pd.DataFrame) -> dict:
    """DFR and BoJ policy rate negative exactly in their known negative-rate periods."""
    dfr = _s(long, "dfr")
    inside = dfr.loc[NEGATIVE_DFR[0]:NEGATIVE_DFR[1]]
    outside = dfr[(dfr.index < "2014-06-11") | (dfr.index > NEGATIVE_DFR[1])]
    boj = _s(long, "boj_policy")
    b_in = boj.loc[NEGATIVE_BOJ[0]:NEGATIVE_BOJ[1]]
    b_out = boj[boj.index > NEGATIVE_BOJ[1]]
    tona = _s(long, "tona").loc[NEGATIVE_BOJ[0]:NEGATIVE_BOJ[1]]
    ok = [(inside < 0).all(), (outside >= 0).all(), (b_in < 0).all(), (b_out >= 0).all(), tona.median() < 0]
    detail = (f"DFR negative on {(inside < 0).mean():.0%} of days {NEGATIVE_DFR[0]}..{NEGATIVE_DFR[1]} and "
              f"non-negative on {(outside >= 0).mean():.0%} of other days; BoJ policy rate negative on "
              f"{(b_in < 0).mean():.0%} of days {NEGATIVE_BOJ[0]}..{NEGATIVE_BOJ[1]}; median TONA in that window "
              f"{tona.median():.3f}%.")
    return result("Negative-rate periods", PASS if all(ok) else FAIL, detail)


def check_spot_values(long: pd.DataFrame, checks: list[tuple[str, str, float, float]] = SPOT_CHECKS) -> dict:
    """Published values checked by hand (e.g. SOFR 5.25% on 17 Sep 2019)."""
    bad, n = [], 0
    for name, day, value, tol in checks:
        s = _s(long, name)
        ts = pd.Timestamp(day)
        if ts not in s.index:
            bad.append(f"{name} {day} missing")
            continue
        n += 1
        if abs(s[ts] - value) > tol:
            bad.append(f"{name} {day} = {s[ts]} (expected {value})")
    return result("Spot checks", FAIL if bad else PASS,
                  "; ".join(bad) if bad else f"{n} published values match (e.g. SOFR 5.25% on 17 Sep 2019).")


def check_eonia_estr(long: pd.DataFrame) -> dict:
    """EONIA equals €STR + 8.5 bp after 2 October 2019."""
    e, s = _s(long, "eonia"), _s(long, "estr")
    both = pd.concat([e, s], axis=1, keys=["eonia", "estr"]).dropna().loc["2019-10-02":]
    diff = (both["eonia"] - both["estr"] - EONIA_SPREAD).abs()
    status = PASS if diff.max() < 0.0015 else WARN if diff.quantile(0.99) < 0.0015 else FAIL
    return result("EONIA vs €STR + 8.5 bp", status,
                  f"{len(both)} common days; largest deviation {diff.max() * 100:.2f} bp.")


def check_bund(long: pd.DataFrame) -> dict:
    """Monthly mean of the Bundesbank daily Bund against the ECB monthly German yield."""
    daily = _s(long, "bund10_daily").resample("MS").mean()
    monthly = _s(long, "y10_DE")
    both = pd.concat([daily, monthly], axis=1).dropna()
    gap = (both.iloc[:, 0] - both.iloc[:, 1]).abs().mean()
    status = PASS if gap <= BUND_MONTHLY_PASS else WARN if gap <= BUND_MONTHLY_WARN else FAIL
    return result("Bund: Bundesbank daily vs ECB monthly", status,
                  f"{len(both)} months; mean absolute difference {gap * 100:.1f} bp (the ECB convergence series "
                  "uses a benchmark basket, the Bundesbank the current 10-year bond).")


def check_oat(long: pd.DataFrame) -> dict:
    """Webstat daily TEC10 averaged by month against the ECB IRS monthly French 10-year yield (U1)."""
    daily = _s(long, "oat10_daily")
    if daily.empty:
        return result("OAT: Webstat daily vs ECB monthly", FAIL, "the daily French 10-year series is missing")
    both = pd.concat([daily.resample("MS").mean(), _s(long, "y10_FR")], axis=1, sort=True).dropna()
    diff = both.iloc[:, 0] - both.iloc[:, 1]
    gap = diff.abs().mean()
    spread_daily = (daily - _s(long, "bund10_daily")).dropna().resample("MS").mean()
    spread_monthly = (_s(long, "y10_FR") - _s(long, "y10_DE")).dropna()
    s = pd.concat([spread_daily, spread_monthly], axis=1, sort=True).dropna()
    corr = s.diff().corr().iloc[0, 1] if len(s) > 12 else float("nan")
    status = PASS if gap <= OAT_MONTHLY_PASS else WARN if gap <= OAT_MONTHLY_WARN else FAIL
    return result("OAT: Webstat daily vs ECB monthly", status,
                  f"{len(both)} months; mean absolute difference {gap * 100:.1f} bp (mean {diff.mean() * 100:+.1f} bp; "
                  "TEC10 is a constant-maturity interpolation, the ECB series a benchmark basket). Monthly changes "
                  f"of the daily-based OAT-Bund spread correlate {corr:.2f} with the ECB-based spread.")


def check_liquidity(long: pd.DataFrame) -> dict:
    """The weekly liquidity proxy against excess liquidity plus reserve requirements."""
    proxy = _s(long, "eur_liquidity")
    exliq = _s(long, "excess_liquidity") / 1e3
    mrr = _s(long, "min_reserves") / 1e3
    both = pd.concat([proxy, exliq, mrr], axis=1, keys=["p", "x", "m"]).dropna()
    if both.empty:
        return result("Euro liquidity proxy", WARN, "no overlap with the daily excess-liquidity series")
    gap = (both["p"] - both["x"] - both["m"]).abs()
    status = PASS if gap.median() < LIQUIDITY_GAP else WARN if gap.median() < 3 * LIQUIDITY_GAP else FAIL
    return result("Euro liquidity proxy", status,
                  f"{len(both)} weeks; median |proxy - excess liquidity - reserve requirements| EUR {gap.median():.0f} "
                  "bn.")


def check_corridors(long: pd.DataFrame) -> dict:
    """EFFR inside the Fed range, TONA near the BoJ policy rate, MMSR repo near the DFR."""
    effr = _s(long, "effr")
    lo, hi = _s(long, "fed_lower"), _s(long, "fed_upper")
    f = pd.concat([effr, lo, hi], axis=1, keys=["e", "l", "h"]).dropna()
    inside = ((f["e"] >= f["l"] - 1e-9) & (f["e"] <= f["h"] + 1e-9)).mean()
    tona, policy = _s(long, "tona"), _s(long, "boj_policy")
    j = pd.concat([tona, policy], axis=1, keys=["t", "p"]).dropna().loc["2016-03-01":]
    tona_gap = (j["t"] - j["p"]).abs().median()
    mmsr = _s(long, "mmsr_rate_le_KS_ALL")
    dfr = _s(long, "dfr").reindex(mmsr.index, method="ffill")
    mmsr_gap = (mmsr - dfr).abs().median()
    ok = inside >= 0.99 and tona_gap <= TONA_POLICY_PASS and mmsr_gap < 0.3
    return result("Market rates vs policy corridors", PASS if ok else WARN,
                  f"EFFR inside the Fed target range on {inside:.1%} of days; median |TONA - BoJ policy rate| "
                  f"since Mar 2016 {tona_gap * 100:.1f} bp; median |MMSR S/N repo - DFR| {mmsr_gap * 100:.1f} bp.")


def check_publication_lags(long: pd.DataFrame, fetched: pd.Timestamp) -> dict:
    """Nothing dated after the fetch; daily series within their lag (plus tolerance)."""
    stale, future = [], []
    for spec in sources.ALL_SERIES:
        s = _s(long, spec.name)
        if s.empty or spec.name in DISCONTINUED:
            continue
        if s.index.max() > fetched.normalize():
            ahead = s[s.index > fetched.normalize()]
            future.append(f"{spec.name} ({len(ahead)} observations dated {ahead.index.min().date()} to "
                          f"{ahead.index.max().date()}, lag {spec.lag_bd} business days)")
        if spec.freq == "daily":
            cal = data.currency_of(spec.name)
            age = len(data.business_days(cal, s.index.max(), fetched.normalize())) - 1
            if age > spec.lag_bd + STALE_EXTRA_BD:
                stale.append(f"{spec.name} ({age} business days old, lag {spec.lag_bd})")
    if future:
        return result("Publication lags", FAIL,
                      f"observations dated after the fetch date {fetched.normalize().date()}: " + "; ".join(future)
                      + ". A value cannot be observed before its date unless it is an announced policy rate "
                        "(those are trimmed by pipeline.trim_announced); check the source's dates.")
    if stale:
        return result("Publication lags", WARN, "older than the publication lag allows: " + "; ".join(stale))
    return result("Publication lags", PASS, "every daily series is within its publication lag (plus "
                                            f"{STALE_EXTRA_BD} business days) of the fetch date; nothing is dated in "
                                            "the future.")


def run_all(long: pd.DataFrame, fetched: pd.Timestamp) -> dict:
    """Every check on a long frame, with counts per status."""
    checks = [check_calendar(long), check_ranges(long), check_negative_rates(long), check_spot_values(long),
              check_eonia_estr(long), check_bund(long), check_oat(long), check_liquidity(long), check_corridors(long),
              check_publication_lags(long, fetched)]
    counts = {k: sum(c["status"] == k for c in checks) for k in (PASS, WARN, FAIL)}
    return {"as_of": str(data.as_of(long).date()), "fetched_at": str(fetched), "counts": counts, "checks": checks}


class ValidationFailed(RuntimeError):
    """At least one check is FAIL: the refresh must not write anything."""


def write_reports(rep: dict, json_path: Path, md_path: Path) -> None:
    """Write the validation report as JSON and as the Markdown table in docs/."""
    json_path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    lines = ["# Data validation", "",
             f"Generated by `scripts/refresh_snapshots.py` for data as of {rep['as_of']} (fetched "
             f"{rep['fetched_at']}). "
             "PASS: the data agrees with the reference; WARN: a documented difference with no material effect; "
             "FAIL: the refresh stops before writing.", "",
             f"Summary: {rep['counts'][PASS]} passed, {rep['counts'][WARN]} warnings, {rep['counts'][FAIL]} "
             "failed.", "",
             "| Check | Status | Detail |", "|---|---|---|"]
    lines += [f"| {c['name']} | {c['status']} | {c['detail']} |" for c in rep["checks"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def demo_long(values: dict[str, pd.Series]) -> pd.DataFrame:
    """Build a long frame from {name: series} (used by tests)."""
    return pd.concat([pd.DataFrame({"date": s.index, "series": k, "value": np.asarray(s, dtype=float)})
                      for k, s in values.items()], ignore_index=True)
