"""Chapter IV at daily frequency (U1): the OAT-Bund spread from Banque de France Webstat and the Bundesbank.

Every rule is fixed in docs/METHODOLOGY.md, "Upgrade U1", before any daily result was computed:
Rule 1 (blowout) and Rule 2 (gradual deterioration) on the daily French spread, Rule 2 also on the
monthly 10-country panel for base rates, the daily decomposition and the daily event study. The
monthly chapter IV (src/france.py) is kept as the robustness check. `run()` writes results/france/daily_*.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import collateral
import data
import events
import france
import survival

OUT_DIR = france.OUT_DIR
SMOOTH_BD = 5                     # days in the moving average of the daily spread
BASELINE_BD = 250                 # trailing window of the daily baseline (about 12 months)
BD_PER_MONTH = 21
BLOWOUT_BP = 30.0                 # Rule 1, as the monthly rule
BLOWOUT_SENSITIVITY = (20.0, 50.0)
GRADUAL_BP = 15.0                 # Rule 2: excess over the trailing mean ...
GRADUAL_MONTHS = 6                # ... held for this many consecutive months
GRADUAL_SENSITIVITY = ((10.0, 6), (20.0, 6), (15.0, 3), (15.0, 9))
RETRACE = france.RETRACE
DISSOLUTION = pd.Timestamp("2024-06-09")
EVENT_STUDY_FROM = "2010-01-01"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def daily_spread(long: pd.DataFrame | None = None) -> pd.Series:
    """FR - DE 10-year spread in bp on days both yields exist."""
    both = pd.concat([data.get("oat10_daily", long), data.get("bund10_daily", long)], axis=1,
                     keys=["oat", "bund"], sort=True).dropna()
    return ((both["oat"] - both["bund"]) * 100).rename("spread")


def daily_frame(long: pd.DataFrame | None = None, smooth: int = SMOOTH_BD, baseline: int = BASELINE_BD) -> pd.DataFrame:
    """Daily spread, its `smooth`-day mean and the trailing `baseline`-day mean (excluding the current day)."""
    s = daily_spread(long)
    return pd.DataFrame({"spread": s, "smoothed": s.rolling(smooth).mean(),
                         "baseline": s.rolling(baseline).mean().shift(1)})


# --------------------------------------------------------------------------- #
# Episode detection (both rules, any frequency)
# --------------------------------------------------------------------------- #
def find_episodes(values: pd.Series, baseline: pd.Series, threshold: float, min_run: int = 1,
                  start_from: pd.Timestamp | None = None, retrace: float = RETRACE) -> list[dict]:
    """Episodes: a run of at least `min_run` periods with values >= baseline + threshold.

    The episode starts in the run's first period (baseline fixed there); it is confirmed once the run
    reaches `min_run` periods. Peak: running maximum from the start. Recovery: the first period after
    confirmation with value <= peak - retrace x (peak - baseline). With min_run = 1 this is Rule 1,
    identical to the monthly blowout rule of src/france.py.
    """
    v, b = values.to_numpy(dtype=float), baseline.reindex(values.index).to_numpy(dtype=float)
    idx = values.index
    above = np.where(np.isnan(v) | np.isnan(b), False, v >= b + threshold)
    out, i, n = [], 0, len(v)
    while i < n:
        if not above[i] or (start_from is not None and idx[i] < start_from):
            i += 1
            continue
        j = i
        while j < n and above[j]:
            j += 1
        if j - i < min_run:
            i = j
            continue
        confirm = i + min_run - 1
        base = float(b[i])
        peak_pos = i + int(np.argmax(v[i:confirm + 1]))
        peak = float(v[peak_pos])
        recovery = None
        k = confirm + 1
        while k < n:
            if v[k] > peak:
                peak, peak_pos = float(v[k]), k
            if v[k] <= peak - retrace * (peak - base):
                recovery = k
                break
            k += 1
        end = recovery if recovery is not None else n - 1
        out.append({"start": idx[i], "confirmed": idx[confirm], "baseline": base, "peak": peak,
                    "peak_date": idx[peak_pos], "widening": peak - base,
                    "recovery": idx[recovery] if recovery is not None else None,
                    "periods": int(end - i), "observed": recovery is not None,
                    "half_retrace_level": peak - retrace * (peak - base)})
        i = k + 1 if recovery is not None else n
    return out


def status(eps: list[dict], last: pd.Timestamp, per_month: float = 1.0) -> dict:
    """Is there an ongoing (censored) episode at the last period, and its age?"""
    ongoing = [e for e in eps if not e["observed"]]
    if not ongoing:
        return {"in_episode": False}
    e = ongoing[-1]
    return {"in_episode": True, "start": str(e["start"].date()), "confirmed": str(e["confirmed"].date()),
            "age_periods": e["periods"], "age_months": e["periods"] / per_month, "baseline": e["baseline"],
            "peak": e["peak"], "peak_date": str(e["peak_date"].date()), "half_retrace_level": e["half_retrace_level"],
            "as_of": str(last.date())}


# --------------------------------------------------------------------------- #
# Rules on the daily French spread
# --------------------------------------------------------------------------- #
def daily_rules(frame: pd.DataFrame) -> dict:
    """Rule 1 (30 bp; 20/50) and Rule 2 (15 bp x 6 months; sensitivity) on the smoothed daily spread."""
    sm, base = frame["smoothed"], frame["baseline"]
    last = frame.index[-1]
    start = pd.Timestamp("2008-01-01")
    out = {"blowout": {}, "gradual": {}}
    for x in (BLOWOUT_BP, *BLOWOUT_SENSITIVITY):
        eps = find_episodes(sm, base, x, 1, start)
        out["blowout"][str(int(x))] = {"n_episodes": len(eps), "status": status(eps, last, BD_PER_MONTH),
                                       "episodes": [_episode_json(e, BD_PER_MONTH) for e in eps]}
    for x, months in ((GRADUAL_BP, GRADUAL_MONTHS), *GRADUAL_SENSITIVITY):
        eps = find_episodes(sm, base, x, months * BD_PER_MONTH, start)
        out["gradual"][f"{int(x)}bp_{months}m"] = {"n_episodes": len(eps), "status": status(eps, last, BD_PER_MONTH),
                                                    "episodes": [_episode_json(e, BD_PER_MONTH) for e in eps]}
    now = frame.dropna().iloc[-1]
    out["now"] = {"date": str(last.date()), "spread": float(frame["spread"].iloc[-1]),
                  "smoothed": float(now["smoothed"]),
                  "baseline": float(now["baseline"]), "excess": float(now["smoothed"] - now["baseline"]),
                  "gap_to_blowout": float(now["baseline"] + BLOWOUT_BP - now["smoothed"])}
    return out


def _episode_json(e: dict, per_month: float) -> dict:
    return {"start": str(e["start"].date()), "confirmed": str(e["confirmed"].date()), "baseline": e["baseline"],
            "peak": e["peak"], "peak_date": str(e["peak_date"].date()),
            "recovery": str(e["recovery"].date()) if e["recovery"] is not None else None,
            "months": e["periods"] / per_month, "observed": e["observed"]}


# --------------------------------------------------------------------------- #
# Rule 2 on the monthly panel: base rates
# --------------------------------------------------------------------------- #
def gradual_panel(long: pd.DataFrame | None = None, threshold: float = GRADUAL_BP,
                  months: int = GRADUAL_MONTHS) -> pd.DataFrame:
    """Rule 2 episodes in the 10-country monthly panel (trailing 12-month mean, from Jan 2008)."""
    spreads = collateral.monthly_spreads(long, list(france.EPISODE_COUNTRIES))
    rows = []
    for c in france.EPISODE_COUNTRIES:
        s = spreads[c].dropna()
        base = s.rolling(france.BASELINE_MONTHS).mean().shift(1)
        for e in find_episodes(s, base, threshold, months, france.EPISODES_FROM):
            rows.append({"country": c, **e, "duration": e["periods"]})
    return pd.DataFrame(rows)


def gradual_base_rates(eps: pd.DataFrame) -> dict:
    """Kaplan-Meier base rates of Rule 2 episodes (months from start to half retracement)."""
    if eps.empty:
        return {"n_episodes": 0}
    km = survival.kaplan_meier(eps["duration"], eps["observed"])
    out = {"n_episodes": int(len(eps)), "n_recovered": int(eps["observed"].sum()),
           "n_countries": int(eps["country"].nunique()), "median_months": survival.median_time(km),
           "at": {h: survival.survival_at(km, h) for h in france.HORIZONS}, "km": km}
    fr = eps[(eps["country"] == "FR") & ~eps["observed"]]
    if len(fr):
        e = fr.iloc[-1]
        out["france"] = {"start": str(e["start"].date())[:7], "age_months": int(e["duration"]),
                         "baseline": float(e["baseline"]), "peak": float(e["peak"]),
                         "half_retrace_level": float(e["half_retrace_level"]),
                         "p_recover_next_12m": france.conditional_recovery(km, e["duration"])}
    return out


# --------------------------------------------------------------------------- #
# Decomposition and events
# --------------------------------------------------------------------------- #
def daily_decomposition(long: pd.DataFrame | None = None) -> dict:
    """OAT leg and Bund leg of the change in the spread since the last business day before the dissolution."""
    both = pd.concat([data.get("oat10_daily", long), data.get("bund10_daily", long)], axis=1,
                     keys=["oat", "bund"], sort=True).dropna()
    base_day = both.index[both.index < DISSOLUTION][-1]
    base, last = both.loc[base_day], both.iloc[-1]
    oat_leg, bund_move = (last["oat"] - base["oat"]) * 100, (last["bund"] - base["bund"]) * 100
    return {"base_day": str(base_day.date()), "last_day": str(both.index[-1].date()),
            "spread_base": float((base["oat"] - base["bund"]) * 100),
            "spread_last": float((last["oat"] - last["bund"]) * 100),
            "oat_leg": float(oat_leg), "bund_contribution": float(-bund_move),
            "spread_change": float(oat_leg - bund_move)}


def daily_event_study(spread: pd.Series, event_list: list[dict] | None = None) -> list[dict]:
    """Two-day change (close before the event day to close after it) against every two-day change since 2010."""
    s = spread.dropna()
    two_day = (s.shift(-1) - s.shift(1)).loc[EVENT_STUDY_FROM:].dropna()   # centred on each day
    out = []
    for ev in (event_list if event_list is not None else events.EVENTS):
        day = pd.Timestamp(ev["date"])
        on_or_after = two_day.index[two_day.index >= day]
        if len(on_or_after) == 0:
            continue
        d = on_or_after[0]
        change = float(two_day[d])
        out.append({**{k: v for k, v in ev.items() if k in ("date", "event", "kind")}, "event_day": str(d.date()),
                    "change_bp": change, "percentile": float((two_day < change).mean()),
                    "z": float((change - two_day.mean()) / two_day.std(ddof=1)), "n_windows": int(len(two_day))})
    return out


def events_summary(rows: list[dict]) -> dict:
    """How many events moved the spread by an unusually large amount (90th percentile or above)."""
    if not rows:
        return {"n": 0}
    changes = [r["change_bp"] for r in rows]
    return {"n": len(rows), "n_unusual": sum(r["percentile"] >= 0.9 for r in rows),
            "n_widened": sum(c > 0 for c in changes), "mean_change": float(np.mean(changes))}


# --------------------------------------------------------------------------- #
# Everything
# --------------------------------------------------------------------------- #
def _json(obj: object) -> object:
    return france._json(obj)


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/france/daily_summary.json and daily_spread.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = daily_frame(long)
    frame.to_csv(out_dir / "daily_spread.csv", float_format="%.3f")
    rules = daily_rules(frame)
    km_blowout = france.survival_summary(france.all_episodes(long))["km"]
    st1 = rules["blowout"][str(int(BLOWOUT_BP))]["status"]
    if st1["in_episode"]:
        st1["p_recover_next_12m"] = france.conditional_recovery(km_blowout, st1["age_months"])
        st1["p_recover_12m_unconditional"] = 1 - survival.survival_at(km_blowout, 12)["survival"]
    panel = gradual_panel(long)
    base_rates = gradual_base_rates(panel)
    if "km" in base_rates:
        base_rates["km"].to_csv(out_dir / "kaplan_meier_gradual.csv", index=False, float_format="%.4f")
    panel.to_csv(out_dir / "episodes_gradual.csv", index=False)
    sens = {}
    for x, months in GRADUAL_SENSITIVITY:
        br = gradual_base_rates(gradual_panel(long, x, months))
        sens[f"{int(x)}bp_{months}m"] = {k: br.get(k) for k in ("n_episodes", "median_months")} | \
            {"france_ongoing": "france" in br}
    summary = {"data_as_of": str(data.as_of(long).date()), "first_day": str(frame.index[0].date()),
               "last_day": str(frame.index[-1].date()), "n_days": int(len(frame)),
               "rules": rules, "gradual_panel": {k: v for k, v in base_rates.items() if k != "km"},
               "gradual_panel_sensitivity": sens, "decomposition": daily_decomposition(long),
               "events": daily_event_study(frame["spread"])}
    summary["events_summary"] = events_summary(summary["events"])
    (out_dir / "daily_summary.json").write_text(json.dumps(_json(summary), indent=1), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    """The saved daily summary, or None."""
    path = out_dir / "daily_summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
