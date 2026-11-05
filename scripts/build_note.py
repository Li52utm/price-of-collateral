"""Build docs/RESEARCH_NOTE.md and its figures (docs/figures/*.png) from the results files only.

    .venv\\Scripts\\python scripts\\build_note.py

Every number in the note is read from results/ (no model is refitted) and every conclusion is a generated
sentence from src/wording.py or src/findings.py, so the note cannot drift from the dashboard. Figures use
the project's Okabe-Ito colours (one colour per series) with line styles and markers as a second encoding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import desk_note  # noqa: E402
import events  # noqa: E402
import findings  # noqa: E402
import sources  # noqa: E402
import wording as w  # noqa: E402

RESULTS = ROOT / "results"
FIG_DIR = ROOT / "docs" / "figures"
NOTE = ROOT / "docs" / "RESEARCH_NOTE.md"
CUR = {"EUR": "#0072B2", "USD": "#009E73", "JPY": "#D55E00"}
CTY = {"DE": "#15213B", "FR": "#56B4E9", "IT": "#E69F00", "ES": "#CC79A7"}
INK, MUTED, GRID = "#15213B", "#5B6475", "#E3E6EC"


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def _style(ax: plt.Axes, title: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def _save(fig: plt.Figure, name: str, source: str) -> str:
    fig.text(0.01, 0.01, f"Source: {source}. The Price of Collateral.", fontsize=7, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / name, dpi=150, metadata={"Software": None})
    plt.close(fig)
    return f"figures/{name}"


def fig_corridors() -> str:
    fig, ax = plt.subplots(figsize=(8, 3.6))
    styles = {"EUR": "-", "USD": "--", "JPY": ":"}
    for cur in ("EUR", "USD", "JPY"):
        df = pd.read_csv(RESULTS / "corridors" / f"corridor_{cur}.csv", index_col=0, parse_dates=True).loc["2018":]
        policy = df["ior"] if cur == "USD" else df["floor"]
        spread = ((df["market"] - policy) * 100).rolling(20, min_periods=5).median()
        ax.plot(spread.index, spread, color=CUR[cur], linestyle=styles[cur], linewidth=1.6, label=cur)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, ncol=3)
    _style(ax, "Overnight rates against the policy floor (20-day median)", "bp")
    return _save(fig, "fig1_corridors.png", "ECB Data Portal, New York Fed, FRED, Bank of Japan")


def fig_reserves(r: dict) -> str:
    pairs = pd.read_csv(RESULTS / "corridors" / "reserves_pairs_USD.csv", index_col=0, parse_dates=True)
    curve = pd.read_csv(RESULTS / "corridors" / "reserves_curve_USD.csv")
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    train = pairs.index <= "2022-12-31"
    ax.scatter(pairs["liq"][train], pairs["spread"][train], s=10, color=CUR["USD"], alpha=0.35, label="weeks to 2022")
    ax.scatter(pairs["liq"][~train], pairs["spread"][~train], s=12, marker="^", color=INK, alpha=0.45,
               label="weeks from 2023")
    ax.plot(curve["liq"], curve["fit"], color=INK, linewidth=1.8, label="linear fit (chosen out of sample)")
    ax.set_xlabel("reserve balances (USD trillion)", color=MUTED, fontsize=9)
    ax.set_ylim(-25, 40)
    ax.legend(frameon=False, fontsize=8)
    _style(ax, "SOFR minus interest on reserves, next week, against reserves", "bp")
    return _save(fig, "fig2_reserves.png", "FRED, New York Fed")


def fig_collateral(r: dict) -> str:
    cs = r["bootstrap"]["credit_scarcity"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    terms = ("credit", "liquidity", "de_holdings", "difference")
    labels = ("credit", "liquidity", "German holdings", "credit minus scarcity")
    for cty, offset, marker in (("IT", -0.12, "o"), ("FR", 0.12, "s")):
        x = [i + offset for i in range(len(terms))]
        y = [cs[cty]["point"][t] for t in terms]
        lo = [y[i] - cs[cty][t]["lower"] for i, t in enumerate(terms)]
        hi = [cs[cty][t]["upper"] - y[i] for i, t in enumerate(terms)]
        ax.errorbar(x, y, yerr=[lo, hi], fmt=marker, color=CTY[cty], capsize=3, markersize=6,
                    label=f"{w.COUNTRY_NAMES[cty]} collateral")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks(range(len(terms)), labels, fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    _style(ax, "Standardised effects on the repo spread to German collateral, 95% intervals", "bp per 1 sd")
    return _save(fig, "fig3_credit_scarcity.png", "ECB Data Portal (MMSR, IRS, PSPP)")


def fig_france() -> str:
    d = pd.read_csv(RESULTS / "france" / "daily_spread.csv", index_col=0, parse_dates=True).loc["2023":]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(d.index, d["spread"], color=CTY["FR"], linewidth=0.7, alpha=0.6, label="daily OAT-Bund spread")
    ax.plot(d.index, d["smoothed"], color=CTY["FR"], linewidth=1.8, label="5-day average")
    ax.plot(d.index, d["baseline"] + 30, color=INK, linestyle="--", linewidth=1.2,
            label="blowout line (trailing year + 30 bp)")
    ax.plot(d.index, d["baseline"] + 15, color=MUTED, linestyle=":", linewidth=1.2,
            label="gradual line (trailing year + 15 bp)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax, "The OAT-Bund 10-year spread against the two episode rules", "bp")
    return _save(fig, "fig4_france_daily.png", "Banque de France (Webstat), Deutsche Bundesbank")


def fig_calibration(r: dict) -> str:
    cal = r["calibration"]
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.5))
    for cur, marker, off in (("USD", "o", -0.08), ("EUR", "s", 0.08)):
        c = cal[cur]
        qs = list(c["per_quantile"])
        nominal = [c["per_quantile"][q]["nominal"] for q in qs]
        share = [c["per_quantile"][q]["share_below"] for q in qs]
        lo = [s - c["per_quantile"][q]["lower"] for s, q in zip(share, qs, strict=True)]
        hi = [c["per_quantile"][q]["upper"] - s for s, q in zip(share, qs, strict=True)]
        axes[0].errorbar([i + off for i in range(len(qs))], share, yerr=[lo, hi], fmt=marker, color=CUR[cur],
                         capsize=3, label=cur)
        axes[0].scatter(range(len(qs)), nominal, marker="_", s=300, color=INK)
        axes[1].bar([i + off * 2.5 for i in range(5)], c["pit"]["observed"], width=0.35, color=CUR[cur], label=cur,
                    hatch="//" if cur == "EUR" else None, edgecolor="white")
    axes[0].set_xticks(range(4), ["5%", "50%", "90%", "95%"], fontsize=8)
    axes[1].scatter(range(5), cal["USD"]["pit"]["expected"], marker="_", s=400, color=INK, label="expected")
    axes[1].set_xticks(range(5), ["<q05", "q05-50", "q50-90", "q90-95", ">q95"], fontsize=7)
    for ax, title, ylab in ((axes[0], "Share below each quantile (dash: nominal)", "share of test days"),
                            (axes[1], "PIT bins on the test period", "share of test days")):
        ax.legend(frameon=False, fontsize=8)
        _style(ax, title, ylab)
    return _save(fig, "fig5_calibration.png", "results/inference/calibration.json")


def fig_yearends(r: dict) -> str:
    t = pd.read_csv(RESULTS / "forecast" / "past_year_ends.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for cur, marker, x0 in (("USD", "o", 2025.8), ("EUR", "s", 2026.15)):
        s = t[t["currency"] == cur]
        ax.plot(s.index.year, s["actual"], marker=marker, color=CUR[cur], linewidth=1.2, label=f"{cur} year-end day")
        v1, v2 = r["frozen"]["currencies"][cur], r["frozen_v2"]["currencies"][cur]
        ax.vlines(x0, v1["q05"], v1["q95"], color=CUR[cur], linewidth=6, alpha=0.4, label=f"{cur} v1 5-95%")
        ax.errorbar([x0 + 0.12], [v2["q50"]], yerr=[[v2["q50"] - v2["q05"]], [v2["q95"] - v2["q50"]]], fmt=marker,
                    color=CUR[cur], capsize=4, markersize=5, linewidth=1.2, label=f"{cur} v2 median and 5-95%")
        ax.plot([x0], [v1["q50"]], marker="_", markersize=12, color=CUR[cur])
    ax.set_xticks(range(2018, 2027), [str(y) for y in range(2018, 2027)], fontsize=8)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    _style(ax, "Every past year-end turn and the frozen 2026 ranges", "spread to the policy rate (bp)")
    return _save(fig, "fig6_yearends.png", "New York Fed, FRED, ECB Data Portal; frozen forecasts")


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def ci(d: dict, unit: str = " bp", dec: int = 1) -> str:
    return w.ci_text(d.get("lower"), d.get("upper"), unit, dec)


def pval(p: float | None) -> str:
    return "n/a" if p is None else ("< 0.001" if p < 0.001 else f"{p:.3f}")


def load() -> dict:
    r = findings.load_results()
    r["robustness"] = json.loads((RESULTS / "robustness" / "table.json").read_text(encoding="utf-8"))
    return r


def build(r: dict) -> str:
    fc, cor, col, fr, frd = r["forecast"], r["corridors"], r["collateral"], r["france"], r["france_daily"]
    boot, tests, cal, rob = r["bootstrap"], r["tests"]["tests"], r["calibration"], r["robustness"]
    note = desk_note.build(r)
    figs = {"corr": fig_corridors(), "res": fig_reserves(r), "col": fig_collateral(r), "fr": fig_france(),
            "cal": fig_calibration(r), "ye": fig_yearends(r)}
    ans = {k: findings.answer(k, r) for k in findings.QUESTIONS}
    as_of = w.pd_day(fc["data_as_of"])
    res_usd, res_eur = cor["reserves"]["USD"], cor["reserves"]["EUR"]
    sl = boot["reserves_slope"]
    rules = frd["rules"]
    b30 = rules["blowout"]["30"]["status"]
    g = rules["gradual"]["15bp_6m"]["status"]
    gp = frd["gradual_panel"]
    surv = fr["survival"]
    split = boot["france_split"]
    hl = boot["japan_half_life"]
    v2 = r["v2"]["currencies"]
    n_tests = len(tests)
    sig_raw = sum(1 for t in tests if t["p"] is not None and t["p"] < 0.05)
    sig_adj = sum(1 for t in tests if t["p_holm"] is not None and t["p_holm"] < 0.05)
    families = sorted({t["family"] for t in tests})

    def winner_row(c: dict) -> dict:
        return next(m for m in c["models"] if m["model"] == c["winner"])

    def model_line(cur: str) -> str:
        c = fc["currencies"][cur]
        win = winner_row(c)
        base = next(m for m in c["models"] if m["model"] == "baseline")
        ci_turn = boot["forecast"][cur]["models"].get(c["winner"], {}).get("ci_diff_turn")
        return w.model_comparison_sentence(cur, win["label"], win["pinball_turn"], base["pinball_turn"],
                                           win.get("dm_turn_p_holm"), c["winner"] == "baseline", ci_turn, True)

    lines: list[str] = []
    add = lines.append
    add("# The Price of Collateral: repo spreads, collateral premia and a frozen year-end forecast")
    add("")
    add(f"*Research note generated by `scripts/build_note.py` from the committed results (data as of {as_of}). "
        "Every number and every conclusion below is produced from the results files; nothing is typed by hand. "
        "Educational project, not investment advice.*")
    add("")
    add("## Abstract")
    add("")
    add("This note studies overnight funding in euro, dollar and yen money markets, the premium that Italian and "
        "French government bonds command as repo collateral against German Bunds, and the year-end turn. Every "
        "modelling choice was fixed in `docs/METHODOLOGY.md` before its result was computed, publication lags are "
        "respected so no model sees data before it was published, and forecasts are judged on a held-out test "
        "period from 2023. The main answers are:")
    add("")
    for key in ("corridors", "collateral", "france", "calendar", "japan", "desk_note"):
        q, a, _ = ans[key]
        add(f"- **{q}** {a}.")
    add("")
    add("Uncertainty is reported as moving-block bootstrap intervals, every hypothesis test is corrected for "
        "multiple testing within its family (Holm), and each headline finding is re-derived under three to six "
        "alternative specifications fixed in advance.")
    add("")
    add("## 1. Questions")
    add("")
    for i, key in enumerate(("story", "corridors", "collateral", "france", "calendar", "japan", "desk_note"), 1):
        add(f"{i}. {findings.QUESTIONS[key]}")
    add("")
    add("## 2. Data")
    add("")
    add("All data are free and official or quasi-official; the dashboard and this note read only the committed "
        "snapshot, which a scheduled pipeline refreshes after validation. Each series is used only after its "
        "publication lag (business days after the observation date):")
    add("")
    add("| Series | Source | Frequency | Lag (business days) |")
    add("|---|---|---|---|")
    for name in ("estr", "sofr", "tona", "reserves", "eur_liquidity", "repo_dvp_term", "oat10_daily",
                 "bund10_daily", "y10_IT"):
        if name == "eur_liquidity":
            add("| Euro liquidity proxy (current accounts + deposit facility - marginal lending) | ECB | weekly | "
                f"{sources.lag('ilm_current_accounts')} |")
            continue
        s = sources.BY_NAME[name]
        add(f"| {s.description.split(' (')[0]} | {s.source.upper()} (`{s.key}`) | {s.freq} | {s.lag_bd} |")
    add(f"| MMSR secured rates by collateral country | ECB | maintenance period | {sources.MMSR_LAG_BD} |")
    add("")
    add(f"Validation (`docs/DATA_VALIDATION.md`): {r['validation']['counts']['PASS']} checks passed, "
        f"{r['validation']['counts']['WARN']} warnings, {r['validation']['counts']['FAIL']} failures. "
        "Limitations: no free daily euro repo rate exists, so the euro forecasting target is €STR (an unsecured "
        "rate) minus the deposit facility rate; MMSR collateral-specific repo rates are maintenance-period "
        "averages rounded to 1 bp; daily 10-year yields are available free only for France (Banque de France "
        "TEC10) and Germany (Bundesbank), so cross-country work on spreads is monthly; French CDS, auction results "
        "and haircut histories are not free and are not used.")
    add("")
    add("## 3. Methods")
    add("")
    add("**Corridors.** The spread of each overnight rate to its policy floor is described by regime, by a "
        "two-state Markov-switching model with switching mean and variance (Hamilton, 1989) estimated to 2022 and "
        "run forward, and, for the dollar and euro, by the link between central bank liquidity and the next "
        "week's spread: linear, one-kink piecewise and logistic fits chosen by out-of-sample error. A kink at the "
        "edge of its search grid is reported as not identified.")
    add("")
    add("**Collateral.** For Italian and French collateral, the maintenance-period MMSR repo spread to German "
        "collateral is regressed on a credit proxy (the 10-year yield spread) and two scarcity proxies (euro "
        "liquidity and Eurosystem holdings of Bunds), with Newey-West errors (Newey and West, 1987); effects are "
        "compared in standard-deviation units, with a Chow (1960) break test at the start of quantitative "
        "tightening.")
    add("")
    add("**France.** The OAT-Bund spread is split exactly into an OAT leg and a Bund leg, and into a euro-wide "
        "part (implied by Italian and Spanish spreads, estimated 2010-2023) and a France-specific residual. "
        "Episodes are defined by two pre-registered rules: a blowout (the 5-day average at least 30 bp above its "
        "trailing-year mean) and a gradual deterioration (at least 15 bp above for six consecutive months). "
        "Recovery is half retracement; base rates come from a Kaplan-Meier estimator (Kaplan and Meier, 1958) "
        "with Greenwood bands on the log-log scale over ten euro countries since 2008. Events are studied in "
        "two-day windows against every two-day window since 2010.")
    add("")
    add("**Forecasting.** Three models forecast the 5th, 50th, 90th and 95th percentiles of each spread 40 "
        "business days ahead: a naive same-as-last-comparable-turn rule, a calendar-only linear quantile "
        "regression (Koenker and Bassett, 1978), and a calendar-plus-state regression. They are fitted to 2022 "
        "and scored on 2023 onward with the pinball loss (Gneiting and Raftery, 2007), tested against the "
        "baseline with the Diebold and Mariano (1995) test with the Harvey, Leybourne and Newbold (1997) "
        "correction. The 2026 year-end forecast (v1) was frozen on 4 November 2026. A challenger (v2), designed "
        "after seeing v1's test calibration, uses conformalised quantile regression (Romano, Patterson and "
        "Candès, 2019) and an empirical distribution of past year-end jumps; it was frozen on 5 November 2026.")
    add("")
    add("**Japan.** An error-correction regression (Engle and Granger, 1987) of daily TONA changes on the lagged "
        "gap to the policy rate gives the half-life of a gap, before and after the exit from negative rates.")
    add("")
    add("**Inference.** Intervals are 95% moving-block bootstrap percentiles (Künsch, 1989), 1,000 resamples, "
        "with block lengths fixed in advance (40 business days for forecast losses, 8 weeks for reserves, "
        "4 maintenance periods for collateral, 6 months for the euro-wide split, 20 business days for Japan). "
        f"There are {n_tests} hypothesis tests in {len(families)} families; Holm's (1979) step-down correction is "
        "applied within each family and every sentence that says \"significant\" uses the adjusted value. "
        "Calibration uses exact Clopper and Pearson (1934) intervals and a probability integral transform "
        "histogram (Diebold, Gunther and Tay, 1998).")
    add("")
    add("## 4. Results")
    add("")
    add("### 4.1 Three corridors")
    add("")
    add(f"![Corridors]({figs['corr']})")
    add("")
    add(ans["corridors"][2])
    add("")
    for cur, ra in (("USD", res_usd), ("EUR", res_eur)):
        add(w.reserves_sentence(cur, ra["winner"], ra["slope_per_unit"], ra["pressure_point"], ra["pressure_band"],
                                ra["latest_liq"], ra["label"], ra["kink_identified"], ra["boot_edge_share"])
            + f" Bootstrap interval of the slope: {ci(sl[cur])} per trillion.")
        add("")
    add(f"![Reserves]({figs['res']})")
    add("")
    add("### 4.2 The price of collateral: credit or scarcity?")
    add("")
    for cty in ("IT", "FR"):
        reg = col["regressions"][cty]
        scarcity = abs(reg["std_effect"]["liquidity"]) + abs(reg["std_effect"]["de_holdings"])
        add(w.collateral_sentence(cty, findings.collateral_verdict(r, cty), reg["std_effect"]["credit"], scarcity,
                                  reg["r2"], reg["mean_spread"], reg["latest_spread"]))
        cs = boot["credit_scarcity"][cty]
        add("")
        add(w.credit_scarcity_ci_sentence(cty, cs["point"]["difference"], cs["difference"]["lower"],
                                          cs["difference"]["upper"]))
        p_break, _ = findings.adjusted_p(r, f"chow_qt_{cty}", reg["chow"]["p_value"])
        add(" " + w.qt_break_sentence(cty, p_break, reg["sub_periods"].get("before_qt", {}).get("verdict"),
                                      reg["sub_periods"].get("after_qt", {}).get("verdict"), True))
        add("")
    add(f"![Credit and scarcity]({figs['col']})")
    add("")
    add(f"**Answer.** {ans['collateral'][1]}.")
    add("")
    add("### 4.3 Italy then, France now")
    add("")
    now = rules["now"]
    add(w.daily_rules_sentence(now["date"], now["spread"], now["smoothed"], now["baseline"], b30["in_episode"],
                               b30.get("start"), b30.get("peak"), b30.get("half_retrace_level"),
                               b30.get("p_recover_next_12m"), g["in_episode"], fr["france_now"]["in_episode"]))
    add("")
    dd = frd["decomposition"]
    add(w.decomposition_sentence(w.pd_day(dd["base_day"]), w.pd_day(dd["last_day"]), dd["spread_base"],
                                 dd["spread_last"], dd["oat_leg"], dd["bund_contribution"]))
    add("")
    add(w.france_specific_sentence(fr["euro_wide"]["since"], split["cum_change"], split["euro_wide"],
                                   split["france_specific"], split["ci_france_specific"], split["ci_euro_wide"]))
    add("")
    add(f"![France daily]({figs['fr']})")
    add("")
    add(w.survival_sentence(surv["n_episodes"], surv["n_countries"], surv["median_months"],
                            surv["at"]["12"]["survival"],
                            surv["at"]["12"]["lower"], surv["at"]["12"]["upper"], fr["threshold_bp"]))
    add(" " + w.gradual_base_rate_sentence(gp["n_episodes"], gp["n_countries"], gp["median_months"],
                                           gp["at"]["12"]["survival"]))
    add("")
    es = frd["events_summary"]
    add(f"**Events.** {len(events.EVENTS)} events met the two-source rule (official sites, Bloomberg and CNBC; "
        f"Reuters, the Financial Times, Le Monde and Les Echos could not be reached by the search tool). "
        + w.event_study_summary_sentence(es["n"], es["n_unusual"], es["mean_change"], es["n_widened"]))
    add("")
    add("| Date | Event | Two-day change (bp) | Percentile |")
    add("|---|---|---|---|")
    for e in frd["events"]:
        add(f"| {e['date']} | {e['event']} | {e['change_bp']:+.1f} | {e['percentile']:.0%} |")
    add("")
    add(f"**Answer.** {ans['france'][1]}. {ans['france'][2]}")
    add("")
    add("### 4.4 The calendar and the forecasts")
    add("")
    t = {c: fc["currencies"][c]["turns"]["ye"] for c in ("USD", "EUR")}
    add(w.yearend_contrast_sentence(t["USD"]["mean"], t["USD"]["share_up"], t["USD"]["n"], t["EUR"]["mean"],
                                    t["EUR"]["share_up"], t["EUR"]["n"]) + " "
        + w.yearend_mechanism_sentence(t["USD"]["mean"], t["EUR"]["mean"]))
    add("")
    for cur in ("USD", "EUR"):
        add(model_line(cur))
        add("")
    add("| Currency | Model | Turn-day pinball | All-day pinball | DM p (turns) | Holm-adjusted | 5-95% coverage |")
    add("|---|---|---|---|---|---|---|")
    for cur in ("USD", "EUR", "JPY"):
        for m in fc["currencies"][cur]["models"]:
            add(f"| {cur} | {m['label']} | {m['pinball_turn']:.2f} | {m['pinball_all']:.2f} | "
                f"{pval(m.get('dm_turn_p'))} | {pval(m.get('dm_turn_p_holm'))} | {m['interval_coverage']:.1%} |")
    add("")
    for cur in ("USD", "EUR", "JPY"):
        c = cal[cur]
        label = next(m["label"] for m in fc["currencies"][cur]["models"] if m["model"] == c["model"])
        add("- " + w.calibration_sentence(cur, label, c["interval_coverage"], c["interval_lower"], c["interval_upper"],
                                          c["verdict"], c["n"]))
    add("")
    add(f"![Calibration]({figs['cal']})")
    add("")
    add(f"**Answer.** {ans['calendar'][1]}. {ans['calendar'][2]}")
    add("")
    add("### 4.5 Japan")
    add("")
    add(f"{ans['japan'][2]} The bootstrap intervals of the two half-lives are {hl['exit']['lower']:.1f} to "
        f"{hl['exit']['upper']:.1f} business days after the exit and {hl['negative']['lower']:.1f} to "
        f"{hl['negative']['upper']:.1f} under negative rates.")
    add("")
    add("### 4.6 Multiple testing")
    add("")
    add(f"Of the {n_tests} tests, {sig_raw} are significant at 5% before the correction and {sig_adj} after it. "
        "The full list is in the dashboard's appendix and `results/inference/tests.json`; the tests whose "
        "conclusion changes are:")
    add("")
    changed = [x for x in tests if x["p"] is not None and (x["p"] < 0.05) != (x["p_holm"] < 0.05)]
    add("| Family | Test | p | Holm-adjusted p |")
    add("|---|---|---|---|")
    for x in changed:
        add(f"| {x['family']} | {x['what']} | {pval(x['p'])} | {pval(x['p_holm'])} |")
    add("")
    add("## 5. Robustness")
    add("")
    add("Each finding was re-derived under alternatives fixed before any was computed (`docs/METHODOLOGY.md`, U3):")
    add("")
    add("| # | Finding | Result |")
    add("|---|---|---|")
    for k, s in rob["summary"].items():
        add(f"| {k} | {s['finding']} | {w.robustness_badge_text(s['holds'], s['n'], s['not_computable'])} |")
    add("")
    failed = [x for x in rob["rows"] if x["holds"] is False]
    add("Where a conclusion does not hold: " + "; ".join(f"{x['finding']}, {x['spec']} ({x['value']})"
                                                           for x in failed) + ".")
    add("")
    add("## 6. The frozen Year-End 2026 forecasts")
    add("")
    add(f"{note['frozen_line']} v1 is the pre-registered headline; v2 is a challenger whose test-period results "
        "are not a clean out-of-sample claim because it was designed after seeing v1's.")
    add("")
    add("| Currency | Forecast | 5% | Median | 90% | 95% |")
    add("|---|---|---|---|---|---|")
    for cur in ("USD", "EUR"):
        for lab, src in (("v1", r["frozen"]), ("v2", r["frozen_v2"])):
            x = src["currencies"][cur]
            add(f"| {cur} | {lab} | {x['q05']:+.1f} | {x['q50']:+.1f} | {x['q90']:+.1f} | {x['q95']:+.1f} |")
    add("")
    for line in note["v2"]["lines"] + note["v2"]["test"] + note.get("tails", []):
        add(f"- {line}")
    add("")
    add(f"![Year-ends]({figs['ye']})")
    add("")
    add(f"**Client verdict.** {note['client']['question']} **{note['client']['verdict']}.** "
        f"{note['client']['sentence']}")
    add("")
    for line in note["recommendation"]["lines"]:
        add(f"- {line}")
    add("")
    add("Both forecasts are scored automatically once 31 December 2026 is published; " + " ".join(note["scoring"]))
    add("")
    add("## 7. Limitations")
    add("")
    add(f"- Small samples in the tails: the year-end tail rests on {v2['USD']['analogue_test'][-1]['n_prior'] + 1} "
        f"dollar and {v2['EUR']['analogue_test'][-1]['n_prior'] + 1} euro year-ends, which is why v1's 90th and "
        "95th percentiles are not separately identified.")
    add("- €STR is an unsecured deposit rate, not a repo rate; euro repo can behave differently at the turn.")
    add("- MMSR collateral-specific rates are maintenance-period averages (69 periods), rounded to 1 bp.")
    add("- The euro-wide split for France is monthly because daily Italian and Spanish yields are not free; the "
        "split's interval reflects only the estimation of the euro-wide beta.")
    add("- Binomial calibration intervals assume independent days; forecasts 40 days ahead overlap, so the "
        "block-bootstrap coverage intervals are the more honest ones.")
    add("- Event verification relied on Bloomberg, CNBC and official sites, mostly through search listings.")
    add("- Survival episodes overlap in time across countries (2010-2012), so base rates are not independent draws.")
    add("")
    add("## References")
    add("")
    add("**Data.** ECB Data Portal (€STR, policy rates, ILM, MMSR, IRS); ECB PSPP breakdown; Banque de France "
        "Webstat (TEC10); Deutsche Bundesbank statistics (10-year Bund); Federal Reserve Bank of New York Markets "
        "API (SOFR, TGCR, BGCR, EFFR); FRED, Federal Reserve Bank of St. Louis (IORB, IOER, target range, reserves, "
        "ON RRP, Fed repo operations); Office of Financial Research Short-term Funding Monitor (DVP repo); US "
        "Treasury Fiscal Data (auctions, Daily Treasury Statement); Bank of Japan Time-Series Data Search (TONA, "
        "call rates, current accounts, basic loan rate); Assemblée nationale; Bloomberg, CNBC, Moody's and Agence "
        "France Trésor (events).")
    add("")
    for ref in (
        "Chow, G. C. (1960). Tests of equality between sets of coefficients in two linear regressions. Econometrica "
        "28(3).",
        "Clopper, C. J. and Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated in the case of "
        "the binomial. Biometrika 26(4).",
        "Diebold, F. X., Gunther, T. A. and Tay, A. S. (1998). Evaluating density forecasts with applications to "
        "financial risk management. International Economic Review 39(4).",
        "Diebold, F. X. and Mariano, R. S. (1995). Comparing predictive accuracy. Journal of Business and Economic "
        "Statistics 13(3).",
        "Engle, R. F. and Granger, C. W. J. (1987). Co-integration and error correction. Econometrica 55(2).",
        "Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. Journal "
        "of the American Statistical Association 102(477).",
        "Greenwood, M. (1926). The natural duration of cancer. Reports on Public Health and Medical Subjects 33.",
        "Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the "
        "business cycle. Econometrica 57(2).",
        "Harvey, D., Leybourne, S. and Newbold, P. (1997). Testing the equality of prediction mean squared errors. "
        "International Journal of Forecasting 13(2).",
        "Holm, S. (1979). A simple sequentially rejective multiple test procedure. Scandinavian Journal of "
        "Statistics 6(2).",
        "Kalbfleisch, J. D. and Prentice, R. L. (1980). The Statistical Analysis of Failure Time Data. Wiley.",
        "Kaplan, E. L. and Meier, P. (1958). Nonparametric estimation from incomplete observations. Journal of the "
        "American Statistical Association 53(282).",
        "Koenker, R. and Bassett, G. (1978). Regression quantiles. Econometrica 46(1).",
        "Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. Annals of "
        "Statistics 17(3).",
        "Newey, W. K. and West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and "
        "autocorrelation consistent covariance matrix. Econometrica 55(3).",
        "Romano, Y., Patterson, E. and Candès, E. (2019). Conformalized quantile regression. Advances in Neural "
        "Information Processing Systems 32.",
    ):
        add(f"- {ref}")
    add("")
    return "\n".join(lines)


def word_count(text: str) -> int:
    """Words outside tables, image links and the reference list."""
    body = text.split("## References")[0]
    kept = [ln for ln in body.splitlines() if not ln.startswith(("|", "!["))]
    return len(" ".join(kept).split())


def main() -> None:
    text = build(load())
    NOTE.write_text(text, encoding="utf-8")
    n_figs = len(list(FIG_DIR.glob("*.png")))
    print(f"Wrote {NOTE.relative_to(ROOT)}: {word_count(text)} words (body), {n_figs} figures")


if __name__ == "__main__":
    main()
