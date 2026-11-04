"""Chapter IV: Italy then, France now. Monthly, because daily OAT yields are not free (CLAUDE.md).

Fixed in docs/METHODOLOGY.md, Phase 4 (IV a-d). `run()` writes results/france/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import collateral
import data
import events
import stats_tools as st
import survival

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "france"
EPISODE_COUNTRIES = ("IT", "ES", "PT", "FR", "BE", "GR", "IE", "AT", "NL", "FI")
EPISODES_FROM = pd.Timestamp("2008-01-01")
THRESHOLD_BP = 30.0
SENSITIVITY_BP = (20.0, 50.0)
BASELINE_MONTHS = 12
RETRACE = 0.5
EURO_WIDE_FIT = ("2010-01-01", "2023-12-01")
POLITICAL_START = pd.Timestamp("2024-06-09")      # dissolution of the National Assembly
DECOMP_BASE_MONTH = pd.Timestamp("2024-05-01")    # the month before the dissolution
CONDITION_MONTHS = 6
EVENT_STUDY_FROM = "2010-01-01"
HORIZONS = (6, 12, 24)


# --------------------------------------------------------------------------- #
# (a) Decomposition and France-specific stress
# --------------------------------------------------------------------------- #
def yields(long: pd.DataFrame | None = None) -> pd.DataFrame:
    import sources
    return pd.DataFrame({c: data.get(f"y10_{c}", long) for c in sources.YIELD_COUNTRIES})


def decomposition(long: pd.DataFrame | None = None) -> dict:
    y = yields(long)[["FR", "DE"]].dropna()
    spread = (y["FR"] - y["DE"]) * 100
    base = y.loc[DECOMP_BASE_MONTH]
    last = y.iloc[-1]
    oat_leg, bund_leg = (last["FR"] - base["FR"]) * 100, (last["DE"] - base["DE"]) * 100
    monthly = pd.DataFrame({"spread": spread, "oat_leg": y["FR"].diff() * 100, "bund_leg": -y["DE"].diff() * 100})
    return {"base_month": str(DECOMP_BASE_MONTH.date())[:7], "last_month": str(y.index[-1].date())[:7],
            "spread_base": float(spread.loc[DECOMP_BASE_MONTH]), "spread_last": float(spread.iloc[-1]),
            "spread_change": float(oat_leg - bund_leg), "oat_leg": float(oat_leg), "bund_leg": float(-bund_leg),
            "monthly": monthly}


def euro_wide_split(long: pd.DataFrame | None = None) -> dict:
    s = collateral.monthly_spreads(long, ["FR", "IT", "ES"]).dropna()
    d = s.diff().dropna()
    fit = d.loc[EURO_WIDE_FIT[0]:EURO_WIDE_FIT[1]]
    X = sm.add_constant(fit[["IT", "ES"]])
    res = sm.OLS(fit["FR"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    fitted = res.params["const"] + res.params["IT"] * d["IT"] + res.params["ES"] * d["ES"]
    residual = d["FR"] - fitted
    out = pd.DataFrame({"fr_change": d["FR"], "euro_wide": fitted, "france_specific": residual})
    since = out.loc[POLITICAL_START.to_period("M").to_timestamp():]
    return {"params": {k: float(v) for k, v in res.params.items()}, "pvalues": {k: float(v) for k, v in res.pvalues.items()},
            "r2": float(res.rsquared), "n_fit": int(len(fit)),
            "since": str(since.index[0].date())[:7] if len(since) else None,
            "cum_change": float(since["fr_change"].sum()), "cum_euro_wide": float(since["euro_wide"].sum()),
            "cum_france_specific": float(since["france_specific"].sum()),
            "series": out}


# --------------------------------------------------------------------------- #
# (b) Blowout episodes and survival
# --------------------------------------------------------------------------- #
def episodes(spread: pd.Series, country: str, threshold: float = THRESHOLD_BP) -> list[dict]:
    """Blowouts: start when spread >= trailing-12m mean + threshold; recovered at half retracement."""
    s = spread.dropna()
    baseline = s.rolling(BASELINE_MONTHS).mean().shift(1)
    out, i, n = [], 0, len(s)
    idx = s.index
    while i < n:
        day = idx[i]
        if day < EPISODES_FROM or np.isnan(baseline.iloc[i]) or s.iloc[i] < baseline.iloc[i] + threshold:
            i += 1
            continue
        base, peak, peak_day = float(baseline.iloc[i]), float(s.iloc[i]), day
        recovery = None
        j = i + 1
        while j < n:
            if s.iloc[j] > peak:
                peak, peak_day = float(s.iloc[j]), idx[j]
            if s.iloc[j] <= peak - RETRACE * (peak - base):
                recovery = idx[j]
                break
            j += 1
        end = recovery if recovery is not None else idx[-1]
        months = (end.year - day.year) * 12 + end.month - day.month
        out.append({"country": country, "start": day, "baseline": base, "peak": peak, "peak_date": peak_day,
                    "widening": peak - base, "recovery": recovery, "duration": months,
                    "observed": recovery is not None, "end_index": j})
        i = j + 1 if recovery is not None else n
    return out


def all_episodes(long: pd.DataFrame | None = None, threshold: float = THRESHOLD_BP) -> pd.DataFrame:
    spreads = collateral.monthly_spreads(long, list(EPISODE_COUNTRIES))
    rows = []
    for c in EPISODE_COUNTRIES:
        rows += episodes(spreads[c], c, threshold)
    return pd.DataFrame(rows)


def survival_summary(eps: pd.DataFrame) -> dict:
    km = survival.kaplan_meier(eps["duration"], eps["observed"])
    return {"n_episodes": int(len(eps)), "n_recovered": int(eps["observed"].sum()),
            "n_countries": int(eps["country"].nunique()), "median_months": survival.median_time(km),
            "at": {h: survival.survival_at(km, h) for h in HORIZONS}, "km": km}


def recovery_conditions(eps: pd.DataFrame, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """For each recovered episode: ECB cut during the episode, peers tightening, Eurosystem net buying."""
    spreads = collateral.monthly_spreads(long, list(EPISODE_COUNTRIES))
    dfr = data.get("dfr", long)
    rows = []
    for _, e in eps[eps["observed"]].iterrows():
        rows.append({"country": e["country"], "start": e["start"], "recovery": e["recovery"],
                     **conditions_at(e["country"], e["start"], e["recovery"], spreads, dfr, long)})
    return pd.DataFrame(rows)


def conditions_at(country: str, start: pd.Timestamp, at: pd.Timestamp, spreads: pd.DataFrame, dfr: pd.Series,
                  long: pd.DataFrame | None = None) -> dict:
    before = at - pd.DateOffset(months=CONDITION_MONTHS)
    dfr_start = dfr[dfr.index <= start].iloc[-1]
    dfr_at = dfr[dfr.index <= at + pd.offsets.MonthEnd(0)].iloc[-1]
    peers = spreads.drop(columns=country)
    peer_change = float(peers.loc[:at].iloc[-1].mean() - peers.loc[:before].iloc[-1].mean())
    try:
        held = data.get(f"pspp_{country}", long)
    except Exception:
        held = pd.Series(dtype=float)
    buying = np.nan
    if len(held) and held.index[0] <= before:
        buying = float(held[held.index <= at + pd.offsets.MonthEnd(0)].iloc[-1] - held[held.index <= before + pd.offsets.MonthEnd(0)].iloc[-1])
    return {"ecb_cut": bool(dfr_at < dfr_start - 1e-9), "dfr_change": float(dfr_at - dfr_start),
            "peers_tightening": bool(peer_change < 0), "peer_change_bp": peer_change,
            "eurosystem_buying": (bool(buying > 0) if buying == buying else None), "net_purchases_bn": buying / 1e3
            if buying == buying else None}


# --------------------------------------------------------------------------- #
# (c) Repo treatment of French collateral
# --------------------------------------------------------------------------- #
def repo_treatment(long: pd.DataFrame | None = None) -> dict:
    panel = collateral.period_panel(long)
    p = panel[["repo_FR", "repo_IT"]].dropna()
    pos = (p["repo_FR"] / p["repo_IT"]).where(p["repo_IT"].abs() >= 1)
    split = int((p.index > POLITICAL_START).argmax())
    ones = np.ones((len(p), 1))
    chow_fr = st.chow_test(p["repo_FR"].to_numpy(), ones, split)
    chow_gap = st.chow_test((p["repo_IT"] - p["repo_FR"]).to_numpy(), ones, split)
    before, after = p.iloc[:split], p.iloc[split:]
    return {"split_period": str(p.index[split].date()), "n_before": int(len(before)), "n_after": int(len(after)),
            "fr_de_before": float(before["repo_FR"].mean()), "fr_de_after": float(after["repo_FR"].mean()),
            "it_de_before": float(before["repo_IT"].mean()), "it_de_after": float(after["repo_IT"].mean()),
            "position_before": float(pos.iloc[:split].median()), "position_after": float(pos.iloc[split:].median()),
            "chow_fr_de": chow_fr, "chow_it_fr": chow_gap, "latest": {"end": str(p.index[-1].date()),
                                                                     "fr_de": float(p["repo_FR"].iloc[-1]),
                                                                     "it_de": float(p["repo_IT"].iloc[-1])},
            "position": pos}


# --------------------------------------------------------------------------- #
# (d) Event study
# --------------------------------------------------------------------------- #
def event_study(long: pd.DataFrame | None = None) -> list[dict]:
    s = collateral.monthly_spreads(long, ["FR"])["FR"].dropna()
    d = s.diff().loc[EVENT_STUDY_FROM:].dropna()
    out = []
    for ev in events.EVENTS:
        month = pd.Timestamp(ev["date"]).to_period("M").to_timestamp()
        if month not in d.index:
            continue
        change = float(d[month])
        out.append({**ev, "month": str(month.date())[:7], "change_bp": change,
                    "percentile": float((d < change).mean()), "z": float((change - d.mean()) / d.std(ddof=1)),
                    "n_months": int(len(d))})
    return out


# --------------------------------------------------------------------------- #
# Everything
# --------------------------------------------------------------------------- #
def france_now(eps: pd.DataFrame, long: pd.DataFrame | None = None) -> dict:
    """France's current state: in an episode or not, its age, and the three recovery conditions now."""
    spreads = collateral.monthly_spreads(long, list(EPISODE_COUNTRIES))
    fr = eps[(eps["country"] == "FR")]
    ongoing = fr[~fr["observed"]]
    last = spreads.index[-1]
    start = ongoing["start"].iloc[0] if len(ongoing) else last - pd.DateOffset(months=BASELINE_MONTHS)
    cond = conditions_at("FR", start, last, spreads, data.get("dfr", long), long)
    out = {"in_episode": bool(len(ongoing)), "last_month": str(last.date())[:7],
           "spread_now": float(spreads["FR"].iloc[-1]), "conditions": cond}
    if len(ongoing):
        e = ongoing.iloc[0]
        out.update({"start": str(e["start"].date())[:7], "age_months": int(e["duration"]), "baseline": float(e["baseline"]),
                    "peak": float(e["peak"]), "peak_date": str(e["peak_date"].date())[:7],
                    "half_retrace_level": float(e["peak"] - RETRACE * e["widening"])})
    else:
        baseline = spreads["FR"].rolling(BASELINE_MONTHS).mean().shift(1).iloc[-1]
        out.update({"trailing_baseline": float(baseline), "gap_to_threshold": float(baseline + THRESHOLD_BP - spreads["FR"].iloc[-1])})
    return out


def conditional_recovery(km: pd.DataFrame, age: float, ahead: float = 12) -> float:
    """P(half-retrace within `ahead` more months | the episode has already lasted `age` months)."""
    s_age = survival.survival_at(km, age)["survival"]
    s_later = survival.survival_at(km, age + ahead)["survival"]
    return float(1 - s_later / s_age) if s_age > 0 else float("nan")


def ongoing_france(eps: pd.DataFrame, km: pd.DataFrame) -> dict:
    e = eps[(eps["country"] == "FR") & ~eps["observed"]].iloc[0]
    return {"start": str(e["start"].date())[:7], "age_months": int(e["duration"]), "baseline": float(e["baseline"]),
            "peak": float(e["peak"]), "peak_date": str(e["peak_date"].date())[:7],
            "half_retrace_level": float(e["peak"] - RETRACE * e["widening"]),
            "p_recover_next_12m": conditional_recovery(km, e["duration"]),
            "survival_at_age": survival.survival_at(km, e["duration"])["survival"]}


def _json(obj):
    if isinstance(obj, dict):
        return {str(k): _json(v) for k, v in obj.items() if not isinstance(v, (pd.DataFrame, pd.Series))}
    if isinstance(obj, list):
        return [_json(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return str(obj.date())
    if isinstance(obj, (float, np.floating)):
        return None if obj != obj else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dec = decomposition(long)
    dec["monthly"].to_csv(out_dir / "decomposition_monthly.csv", float_format="%.3f")
    split = euro_wide_split(long)
    split["series"].to_csv(out_dir / "france_specific_monthly.csv", float_format="%.3f")
    eps = all_episodes(long)
    eps.drop(columns="end_index").to_csv(out_dir / "episodes.csv", index=False)
    surv = survival_summary(eps)
    surv["km"].to_csv(out_dir / "kaplan_meier.csv", index=False, float_format="%.4f")
    sens = {}
    for x in SENSITIVITY_BP:
        e = all_episodes(long, x)
        s = survival_summary(e)
        fr_ongoing = bool(((e["country"] == "FR") & ~e["observed"]).any()) if len(e) else False
        sens[str(int(x))] = {"n_episodes": s["n_episodes"], "median_months": s["median_months"],
                             "s12": s["at"][12]["survival"], "france_ongoing": fr_ongoing}
        if fr_ongoing:
            sens[str(int(x))]["france"] = ongoing_france(e, s["km"])
    cond = recovery_conditions(eps, long)
    cond.to_csv(out_dir / "recovery_conditions.csv", index=False)
    repo = repo_treatment(long)
    repo["position"].to_csv(out_dir / "repo_position.csv", float_format="%.3f")
    summary = {
        "data_as_of": str(data.as_of(long).date()), "threshold_bp": THRESHOLD_BP, "retrace": RETRACE,
        "decomposition": dec, "euro_wide": split,
        "survival": {k: v for k, v in surv.items() if k != "km"}, "sensitivity": sens,
        "conditions_share": {k: (float(cond[k].dropna().astype(bool).mean()) if cond[k].notna().any() else None,
                                 int(cond[k].notna().sum())) for k in ("ecb_cut", "peers_tightening", "eurosystem_buying")}
        if len(cond) else {},
        "france_now": france_now(eps, long), "repo": repo, "events": event_study(long),
        "excluded_events": events.EXCLUDED, "events_checked_on": events.CHECKED_ON,
    }
    (out_dir / "summary.json").write_text(json.dumps(_json(summary), indent=1), encoding="utf-8")
    return summary


def load_summary(out_dir: Path = OUT_DIR) -> dict | None:
    path = out_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
