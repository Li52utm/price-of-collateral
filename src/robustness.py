"""Robustness of every headline finding (U3; the alternatives are fixed in docs/METHODOLOGY.md).

Each finding R1-R8 is re-derived under 3-6 alternative specifications, everything else unchanged.
`run()` writes results/robustness/table.json (rows and a per-finding summary) and table.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import collateral
import data
import desk_note
import features as F
import forecast as fc
import france
import france_daily as fd
import inference
import stats_tools as st
import wording as w

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results" / "robustness"
FINDINGS = {
    "R1": ("calendar", "The winning regression beats the naive baseline on test-period turn days (USD and EUR)"),
    "R2": ("calendar", "Dollar year-ends push the spread up, euro year-ends push it down"),
    "R3": ("corridors", "SOFR rises relative to IOR as reserves fall (slope below zero, interval excludes zero)"),
    "R4": ("collateral", "Italy: too close to call; France: neither clearly credit nor scarcity"),
    "R5": ("france", "France is in a blowout now (daily rule)"),
    "R6": ("france", "The widening since June 2024 is mainly France-specific"),
    "R7": ("japan", "Gaps close faster after the exit than under negative rates"),
    "R8": ("desk_note", "Client verdict: stay overnight in both currencies"),
}


def _row(finding: str, spec: str, holds: bool | None, value: str) -> dict:
    """One alternative; holds=None means it could not be computed (excluded from n, listed in the table)."""
    return {"finding": finding, "chapter": FINDINGS[finding][0], "spec": spec,
            "holds": None if holds is None else bool(holds), "value": value}


# --------------------------------------------------------------------------- #
# R1 and R2: the calendar
# --------------------------------------------------------------------------- #
def beats_baseline(ev: dict) -> tuple[bool, str]:
    rows = {m["model"]: m["pinball_turn"] for m in ev["models"]}
    best = min(rows["calendar"], rows["state"])
    return best < rows["baseline"], f"{ev['currency']} best {best:.2f} vs baseline {rows['baseline']:.2f}"


def r1(long: pd.DataFrame | None = None) -> list[dict]:
    specs = {"horizon 20 business days": {"horizon": 20}, "horizon 60 business days": {"horizon": 60},
             "train end 2021 (test 2022 on)": {"train_end": pd.Timestamp("2021-12-31"),
                                               "test_start": pd.Timestamp("2022-01-01")},
             "train end 2023 (test 2024 on)": {"train_end": pd.Timestamp("2023-12-31"),
                                               "test_start": pd.Timestamp("2024-01-01")},
             "test without 10-31 Mar 2023": {"exclude": ("2023-03-10", "2023-03-31")}}
    out = []
    for name, kw in specs.items():
        results = [beats_baseline(fc.evaluate_currency(c, long, **kw)) for c in ("USD", "EUR")]
        out.append(_row("R1", name, all(h for h, _ in results), "; ".join(v for _, v in results)))
    return out


def r2(long: pd.DataFrame | None = None) -> list[dict]:
    def stat(effects: pd.DataFrame, how: str = "mean", drop_first: bool = False) -> float:
        ye = effects[effects["type"] == "ye"]["effect"]
        ye = ye.iloc[1:] if drop_first else ye
        return float(ye.median() if how == "median" else ye.mean())

    out = []
    for name, kw in {"lookback 5 business days": dict(lookback=5), "lookback 20 business days": dict(lookback=20)}.items():
        u, e = stat(fc.turn_effects("USD", long, **kw)), stat(fc.turn_effects("EUR", long, **kw))
        out.append(_row("R2", name, u > 0 > e, f"USD {u:+.1f} bp, EUR {e:+.1f} bp"))
    base = {c: fc.turn_effects(c, long) for c in ("USD", "EUR")}
    u, e = stat(base["USD"], "median"), stat(base["EUR"], "median")
    out.append(_row("R2", "median instead of mean", u > 0 > e, f"USD {u:+.1f} bp, EUR {e:+.1f} bp"))
    u, e = stat(base["USD"], drop_first=True), stat(base["EUR"], drop_first=True)
    out.append(_row("R2", "drop each series' first year-end", u > 0 > e, f"USD {u:+.1f} bp, EUR {e:+.1f} bp"))
    return out


# --------------------------------------------------------------------------- #
# R3: reserves slope
# --------------------------------------------------------------------------- #
def pairs_ahead(weeks_ahead: int, long: pd.DataFrame | None = None) -> pd.DataFrame:
    """Weekly reserves against the mean USD spread over week `weeks_ahead` after the observation."""
    import corridors
    name, scale, _ = corridors.LIQUIDITY["USD"]
    liq = (data.get(name, long) / scale).dropna()
    y = F.target("USD", long)
    rows = []
    for day, level in liq.items():
        lo, hi = day + pd.Timedelta(days=7 * (weeks_ahead - 1)), day + pd.Timedelta(days=7 * weeks_ahead)
        nxt = y[(y.index > lo) & (y.index <= hi)]
        if len(nxt) >= 3:
            rows.append({"date": day, "liq": float(level), "spread": float(nxt.mean())})
    return pd.DataFrame(rows).set_index("date")


def r3(long: pd.DataFrame | None = None) -> list[dict]:
    pairs = pd.read_csv(ROOT / "results" / "corridors" / "reserves_pairs_USD.csv", index_col=0, parse_dates=True)
    specs = {"bootstrap block 4 weeks": (pairs, 4), "bootstrap block 16 weeks": (pairs, 16),
             "train weeks only (to 2022)": (pairs.loc[:"2022-12-31"], 8),
             "test weeks only (2023 on)": (pairs.loc["2023-01-01":], 8),
             "spread two weeks ahead": (pairs_ahead(2, long), 8)}
    out = []
    for name, (p, block) in specs.items():
        s = inference.slope_interval(p, block)
        out.append(_row("R3", name, s["slope"] < 0 and s["upper"] < 0,
                        f"slope {s['slope']:+.2f} ({s['lower']:+.2f} to {s['upper']:+.2f}) bp per trillion"))
    return out


# --------------------------------------------------------------------------- #
# R4: credit vs scarcity
# --------------------------------------------------------------------------- #
def final_verdicts(panel: pd.DataFrame, block: int = inference.BLOCK_PERIODS,
                   hac_lags: int = collateral.HAC_LAGS) -> dict:
    """Chapter III final verdicts (Holm-adjusted decision rule + the U2 'too close to call' rule)."""
    results = {c: collateral.regression(panel, c, hac_lags) for c in collateral.REGRESSION_COUNTRIES}
    collateral.apply_holm(results)
    out = {}
    for c, reg in results.items():
        ci = inference.credit_scarcity_intervals(panel, c, block)
        out[c] = w.final_verdict(reg["verdict"], ci["too_close_to_call"])
    return out


def r4(long: pd.DataFrame | None = None) -> list[dict]:
    base_panel = collateral.period_panel(long)
    baseline = final_verdicts(base_panel)
    specs = {"MMSR overnight instead of spot-next": (collateral.period_panel(long, tenor="MA"), {}),
             "borrowing side instead of lending": (collateral.period_panel(long, side="bo"), {}),
             "bootstrap block 2 periods": (base_panel, {"block": 2}),
             "bootstrap block 8 periods": (base_panel, {"block": 8}),
             "Newey-West lags 6": (base_panel, {"hac_lags": 6})}
    out = []
    for name, (panel, kw) in specs.items():
        v = final_verdicts(panel, **kw)
        out.append(_row("R4", name, v == baseline, f"IT {v['IT']}; FR {v['FR']}"))
    return out


# --------------------------------------------------------------------------- #
# R5 and R6: France
# --------------------------------------------------------------------------- #
def daily_in_episode(frame: pd.DataFrame, threshold: float) -> tuple[bool, str]:
    eps = fd.find_episodes(frame["smoothed"], frame["baseline"], threshold, 1, pd.Timestamp("2008-01-01"))
    s = fd.status(eps, frame.index[-1], fd.BD_PER_MONTH)
    return s["in_episode"], (f"in an episode since {s['start']}" if s["in_episode"] else "not in an episode")


def r5(long: pd.DataFrame | None = None) -> list[dict]:
    base = fd.daily_frame(long)
    specs = {"threshold 20 bp": (base, 20.0), "threshold 50 bp": (base, 50.0),
             "no smoothing (1 day)": (fd.daily_frame(long, smooth=1), 30.0),
             "10-day smoothing": (fd.daily_frame(long, smooth=10), 30.0),
             "baseline 125 business days": (fd.daily_frame(long, baseline=125), 30.0)}
    out = [_row("R5", name, *daily_in_episode(frame, x)) for name, (frame, x) in specs.items()]
    eps = france.all_episodes(long)
    now = france.france_now(eps, long)
    out.append(_row("R5", "monthly rule (ECB data to the last month)", now["in_episode"],
                    f"{'in' if now['in_episode'] else 'not in'} an episode at {now['last_month']} "
                    f"({now['spread_now']:.0f} bp)"))
    return out


def r6(long: pd.DataFrame | None = None) -> list[dict]:
    spreads = collateral.monthly_spreads(long)
    specs = {"fit window 2015-2023": dict(fit_window=("2015-01-01", "2023-12-01")),
             "fit window 2010-2019": dict(fit_window=("2010-01-01", "2019-12-01")),
             "regressors IT, ES and PT": dict(regressors=("IT", "ES", "PT")),
             "cumulate from July 2024": dict(since="2024-07-01")}
    out = []
    for name, kw in specs.items():
        s = inference.france_split_intervals(spreads, with_ci=False, **kw)
        out.append(_row("R6", name, abs(s["france_specific"]) > abs(s["euro_wide"]),
                        f"France-specific {s['france_specific']:+.0f} bp, euro-wide {s['euro_wide']:+.0f} bp"))
    return out


# --------------------------------------------------------------------------- #
# R7: Japan
# --------------------------------------------------------------------------- #
def r7() -> list[dict]:
    daily = pd.read_csv(ROOT / "results" / "japan" / "japan_daily.csv", index_col=0, parse_dates=True)
    neg, ex = inference.JAPAN_SAMPLES["negative"], inference.JAPAN_SAMPLES["exit"]
    specs = {"exit sample from 1 Aug 2024": ({"negative": neg, "exit": ("2024-08-01", None)}, {}),
             "negative sample from 1 Oct 2016": ({"negative": ("2016-10-01", neg[1]), "exit": ex}, {}),
             "no same-day pass-through term": (None, {"same_day": False}),
             "bootstrap block 10 days": (None, {"block": 10}),
             "bootstrap block 40 days": (None, {"block": 40})}
    out = []
    for name, (samples, kw) in specs.items():
        j = inference.japan_intervals(daily, samples, **kw)
        e, n = j["exit"], j["negative"]
        holds = e["half_life"] < n["half_life"]
        if "block" in kw:
            holds = holds and e["upper"] < n["lower"]
        out.append(_row("R7", name, holds, f"exit {e['half_life']:.1f} ({e['lower']:.1f}-{e['upper']:.1f}) vs "
                                           f"negative {n['half_life']:.1f} ({n['lower']:.1f}-{n['upper']:.1f}) days"))
    return out


# --------------------------------------------------------------------------- #
# R8: the desk note verdict
# --------------------------------------------------------------------------- #
def excess(fcast: dict, start_bd: int = desk_note.WINDOW_START_BD, nights: bool = True) -> float:
    """Expected excess over the 14-night window starting `start_bd` business days before 31 Dec 2026."""
    days = sorted(pd.Timestamp(d) for d in fcast["path"])
    before = [d for d in days if d <= desk_note.YEAR_END]
    if len(before) <= start_bd:  # the frozen path starts on 21 December: earlier windows cannot be computed
        return float("nan")
    start = before[-(start_bd + 1)]
    end = start + pd.Timedelta(days=desk_note.WINDOW_DAYS)
    window = pd.DatetimeIndex([d for d in days if start <= d < end])
    medians = np.array([fcast["path"][str(d.date())]["q50"] for d in window])
    weights = st.night_weights(window, end) if nights else np.ones(len(window))
    return st.weighted_mean(medians, weights) - fcast["latest_level"]


def r8() -> list[dict]:
    frozen = fc.load_frozen()
    tvo = json.loads((ROOT / "results" / "forecast" / "summary.json").read_text(encoding="utf-8"))[
        "term_vs_overnight"]["USD"]
    premium, _ = desk_note.usd_hurdle(tvo)
    usd_h = premium if premium is not None else desk_note.EUR_HURDLE_BP
    u, e = frozen["currencies"]["USD"], frozen["currencies"]["EUR"]
    base_verdict = w.client_verdict(excess(u) > usd_h, excess(e) > desk_note.EUR_HURDLE_BP)[0]
    specs = {"business-day weights (pre-U0 rule)": (dict(nights=False), desk_note.EUR_HURDLE_BP),
             "window from 5 business days before": (dict(start_bd=5), desk_note.EUR_HURDLE_BP),
             "window from 10 business days before": (dict(start_bd=10), desk_note.EUR_HURDLE_BP),
             "euro hurdle 0 bp": ({}, 0.0), "euro hurdle 2 bp": ({}, 2.0)}
    out = []
    for name, (kw, eur_h) in specs.items():
        xu, xe = excess(u, **kw), excess(e, **kw)
        if xu != xu or xe != xe:
            out.append(_row("R8", name, None, "not computable: the frozen path starts on 21 December 2026"))
            continue
        v = w.client_verdict(xu > usd_h, xe > eur_h)[0]
        out.append(_row("R8", name, v == base_verdict,
                        f"verdict {v}; USD {xu:+.1f} vs {usd_h:+.1f} bp, EUR {xe:+.2f} vs {eur_h:+.1f} bp"))
    return out


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def summarise(rows: list[dict]) -> dict:
    """Per finding: k of n alternatives in which the conclusion holds."""
    out = {}
    for f, (chapter, text) in FINDINGS.items():
        sub = [r for r in rows if r["finding"] == f and r["holds"] is not None]
        skipped = sum(1 for r in rows if r["finding"] == f and r["holds"] is None)
        out[f] = {"chapter": chapter, "finding": text, "n": len(sub), "holds": sum(r["holds"] for r in sub),
                  "not_computable": skipped}
    return out


def run(long: pd.DataFrame | None = None, out_dir: Path = OUT_DIR) -> dict:
    """Write results/robustness/table.json and table.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [*r1(long), *r2(long), *r3(long), *r4(long), *r5(long), *r6(long), *r7(), *r8()]
    table = {"data_as_of": str(data.as_of(long).date()), "summary": summarise(rows), "rows": rows}
    (out_dir / "table.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
    pd.DataFrame(rows).to_csv(out_dir / "table.csv", index=False)
    return table


def load(out_dir: Path = OUT_DIR) -> dict | None:
    """The saved robustness table, or None."""
    path = out_dir / "table.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
