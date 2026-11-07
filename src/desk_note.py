"""Chapter VII: the Year-End 2026 desk note, built from the frozen forecast and the results files.

Pure functions (no Streamlit): `build(results)` returns every line the page shows, and `markdown(note)`
the downloadable version. The client rule is fixed in docs/METHODOLOGY.md, Phase 6.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import findings
import stats_tools as st
import wording as w

WINDOW_START_BD = 7      # business days before 31 Dec 2026 (the Phase 2 term rule)
WINDOW_DAYS = 14
EUR_HURDLE_BP = 1.0
YEAR_END = pd.Timestamp("2026-12-31")


def window_bounds(path: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Start (7 business days before 31 Dec 2026) and exclusive end (14 calendar days later) of the window."""
    days = sorted(pd.Timestamp(d) for d in path)
    before = [d for d in days if d <= YEAR_END]
    start = before[-(WINDOW_START_BD + 1)] if len(before) > WINDOW_START_BD else before[0]
    return start, start + pd.Timedelta(days=WINDOW_DAYS)


def window_days(path: dict) -> list[str]:
    """Business days of the frozen path inside the turn window."""
    start, end = window_bounds(path)
    return [str(d.date()) for d in sorted(pd.Timestamp(x) for x in path) if start <= d < end]


def expected_excess(fc: dict) -> float:
    """Night-weighted mean of the frozen medians over the window minus the latest level (bp).

    Each business day's rate applies until the next business day, so 24 and 31 December 2026 carry
    four nights each (corrected 2026-11-05, METHODOLOGY.md U0; it was an unweighted business-day mean).
    """
    days = window_days(fc["path"])
    _, end = window_bounds(fc["path"])
    medians = [fc["path"][d]["q50"] for d in days]
    weights = st.night_weights(pd.DatetimeIndex(days), end)
    return float(st.weighted_mean(medians, weights) - fc["latest_level"])


def usd_hurdle(tvo: dict) -> tuple[float | None, bool]:
    """(premium to compare with, stale?): a stale premium is replaced by the 1 bp hurdle (U0)."""
    stale = bool(tvo.get("term_stale", False))
    return (None if stale else tvo.get("latest_premium_bp")), stale


# --------------------------------------------------------------------------- #
# D9: severity rules for the ranked risks (METHODOLOGY.md, "Desk upgrade D9")
# --------------------------------------------------------------------------- #
RISK_ORDER = ("euro_liquidity", "us_reserves", "us_backstop", "france", "euro_drift", "calibration")
NEAR_IORB_BP = 5.0
USAGE_MIN_BN = 1.0


def severity_euro_liquidity(distance: dict | None) -> float:
    """1 below the band's lower end, 0.67 below the kink, 0.33 below the upper end, else 0 (0 if not identified)."""
    if not distance:
        return 0.0
    if distance["lower"] <= 0:
        return 1.0
    if distance["kink"] <= 0:
        return 0.67
    return 0.33 if distance["upper"] <= 0 else 0.0


def severity_us_reserves(mean_20d_bp: float, near_bp: float = NEAR_IORB_BP) -> float:
    """1 if the 20-day mean of SOFR minus IORB is at or above zero, 0.5 if within `near_bp` below, else 0."""
    if mean_20d_bp >= 0:
        return 1.0
    return 0.5 if mean_20d_bp >= -near_bp else 0.0


def severity_backstop(days_used_30d: int, last_turn_bn: float, min_bn: float = USAGE_MIN_BN) -> float:
    """1 if the facility was used in the last 30 days, 0.5 if only at the last quarter-end, else 0."""
    if days_used_30d > 0:
        return 1.0
    return 0.5 if last_turn_bn >= min_bn else 0.0


def severity_france(in_blowout: bool, steepness: str | None) -> float:
    """1 in a blowout episode, 0.5 if the curve steepness is unusual, else 0."""
    if in_blowout:
        return 1.0
    return 0.5 if steepness == "unusual" else 0.0


def severity_drift(verdict: str | None) -> float:
    """1 if €STR minus the DFR is drifting up, else 0."""
    return 1.0 if verdict == "drifting up" else 0.0


def severity_calibration(verdicts: list[str], tails_pinned: bool) -> float:
    """1 if a winner is too narrow or the 90th and 95th percentiles coincide; 0.5 if too wide; else 0."""
    if "too narrow" in verdicts or tails_pinned:
        return 1.0
    return 0.5 if "too wide" in verdicts else 0.0


def rank_risks(items: list[dict]) -> list[dict]:
    """Sort by severity (highest first), ties in RISK_ORDER."""
    return sorted(items, key=lambda x: (-x["severity"], RISK_ORDER.index(x["key"])))


def ranked_risks(r: dict) -> list[dict]:
    """Every pre-registered risk with its severity, current number and explanation (unsorted inputs skipped)."""
    out = []
    rw, ov, tk = r.get("runway"), r.get("overview"), r.get("toolkit")
    if rw:
        d = rw["distance_bn"]
        sev = severity_euro_liquidity(d)
        number = (f"liquidity {w.eur_bn(rw['latest_bn'])}, {w.eur_bn(d['lower'])} "
                  f"{'below' if d['lower'] <= 0 else 'above'} the band's lower end" if d else
                  f"liquidity {w.eur_bn(rw['latest_bn'])}; pressure point not identified")
        out.append({"key": "euro_liquidity", "severity": sev, "number": number,
                    "explanation": ("Chapter II places the start of euro funding pressure above today's liquidity, so "
                                    "the floor system has less cushion into the turn." if sev >= 0.67 else
                                    "Liquidity is still at or above the pressure point identified in chapter II.")})
    if ov:
        m = ov["US"]["spread_20d_mean"]
        sev = severity_us_reserves(m)
        out.append({"key": "us_reserves", "severity": sev,
                    "number": f"SOFR minus IORB {w.signed_bp(m)} on average over the last 20 days, reserves "
                              f"USD {ov['US']['reserves_tn']['value']:.2f} trillion",
                    "explanation": ("Repo trading at or above the rate on reserves means reserves are no longer "
                                    "abundant; turns then add to an already firm base." if sev == 1 else
                                    "Repo trades close to the rate on reserves; a turn could push it above."
                                    if sev == 0.5 else "Repo trades comfortably below the rate on reserves.")})
    if tk:
        s = tk["latest"]
        sev = severity_backstop(s["repo_30d_days_used"], s["last_turn_repo_bn"])
        out.append({"key": "us_backstop", "severity": sev,
                    "number": f"{s['repo_30d_days_used']} days of use in the last 30; "
                              f"{w.usd_bn(s['last_turn_repo_bn'])} at the last quarter-end",
                    "explanation": ("Banks are already borrowing from the Fed's facility, a sign that market repo is "
                                    "tight." if sev == 1 else
                                    "The facility was needed at the last quarter-end, so the year-end may need it "
                                    "too." if sev == 0.5 else "The facility has not been needed recently.")})
    daily, curve = r.get("france_daily"), r.get("curve")
    if daily:
        b = daily["rules"]["blowout"][next(iter(daily["rules"]["blowout"]))]["status"]
        steep = curve["main"]["verdict"] if curve else None
        sev = severity_france(b["in_episode"], steep)
        out.append({"key": "france", "severity": sev,
                    "number": f"OAT-Bund {daily['rules']['now']['spread']:.0f} bp, "
                              f"{'in' if b['in_episode'] else 'not in'} a blowout episode"
                              + (f", 2s10s excess over Germany {curve['main']['latest']['excess']:+.0f} bp"
                                 if curve else ""),
                    "explanation": ("French collateral is repricing; political news can move it further into the "
                                    "turn, and no model here forecasts politics." if sev > 0 else
                                    "The OAT-Bund spread is not in an episode by the pre-registered rules.")})
    if rw:
        v = rw["trend"]["main"]
        sev = severity_drift(v["verdict"])
        out.append({"key": "euro_drift", "severity": sev,
                    "number": f"slope {v['slope_bp_per_year']:+.2f} bp a year over 12 months",
                    "explanation": ("€STR is creeping up towards the deposit rate as liquidity drains." if sev == 1
                                    else "No significant upward drift in €STR against the deposit rate.")})
    cal, tails = r.get("calibration") or {}, (r.get("tails") or {}).get("currencies", {})
    if cal or tails:
        verdicts = [cal[c]["verdict"] for c in ("USD", "EUR") if c in cal]
        pinned = any(tails.get(c, {}).get("same_pins") for c in ("USD", "EUR"))
        sev = severity_calibration(verdicts, pinned)
        out.append({"key": "calibration", "severity": sev,
                    "number": "test-period verdicts: " + ", ".join(f"{c} {cal[c]['verdict']}" for c in ("USD", "EUR")
                                                                   if c in cal)
                              + ("; 90th and 95th year-end percentiles coincide" if pinned else ""),
                    "explanation": ("Treat the frozen ranges as a floor on uncertainty: the tails rest on seven or "
                                    "eight past year-ends." if sev == 1 else
                                    "The ranges were too wide on the test period, so they overstate risk."
                                    if sev == 0.5 else "The ranges were well calibrated on the test period.")})
    return rank_risks(out)


def regional_overview(r: dict, frozen: dict, v2f: dict | None) -> list[dict]:
    """The funding overview by region: a title and generated lines for each."""
    ov = r.get("overview")
    if not ov:
        return []
    v2 = (v2f or {}).get("currencies", {})
    us, eu = ov["US"], ov["EUR"]
    us_lines = [w.level_change_phrase("SOFR minus IORB", us["spread"]) + ".",
                f"State: {w.level_change_phrase('reserve balances', us['reserves_tn'], 'USD tn', 2)}; "
                f"{w.level_change_phrase('the Treasury General Account', us['tga_bn'], 'USD bn', 0)}; "
                f"{w.level_change_phrase('ON RRP take-up', us['onrrp_bn'], 'USD bn', 1)}."]
    tk, fac = r.get("toolkit"), r.get("facilities")
    if tk:
        us_lines.append(w.backstop_line(tk["latest"]))
    if fac:
        fed = next(x for x in fac["rows"] if x["bank"] == "Federal Reserve")
        us_lines.append(w.srf_headroom_sentence(fed))
    us_lines.append(w.year_end_view_sentence("USD", frozen["currencies"]["USD"], v2.get("USD")))
    eu_lines = [w.level_change_phrase("€STR minus the DFR", eu["spread"]) + "."]
    state = [w.level_change_phrase("the liquidity proxy", eu["liquidity_bn"], "EUR bn", 0)]
    if eu.get("gov_deposits_bn"):
        state.append(w.level_change_phrase("government deposits at the Eurosystem", eu["gov_deposits_bn"], "EUR bn", 0))
    eu_lines.append("State: " + "; ".join(state) + ".")
    eu_lines += findings.runway_lines(r)[:1] + findings.runway_lines(r)[3:4]
    eu_lines.append(w.year_end_view_sentence("EUR", frozen["currencies"]["EUR"], v2.get("EUR")))
    fr_lines = [w.level_change_phrase("The OAT-Bund 10-year spread", ov["FR"]["spread"]) + "."]
    q, a, e = findings.answer("france", r)
    fr_lines.append(f"{a}.")
    for line in (findings.steepness_line(r), findings.france_absorption_line(r)):
        if line:
            fr_lines.append(line)
    regions = [{"region": "United States", "lines": us_lines}, {"region": "Euro area", "lines": eu_lines},
               {"region": "Euro area: France", "lines": fr_lines}]
    if r.get("uk"):
        uk_lines = [w.level_change_phrase("SONIA minus Bank Rate", ov["UK"]["spread"], decimals=2) + ".",
                    findings.uk_lines(r)[0], w.no_forecast_sentence("sterling")]
        regions.append({"region": "United Kingdom", "lines": uk_lines})
    jp_lines = [w.level_change_phrase("TONA minus the BoJ policy rate", ov["JP"]["spread"]) + ".",
                "State: " + w.level_change_phrase("BoJ current account balances", ov["JP"]["current_accounts_tn"],
                                                  "JPY tn", 1) + " (monthly average).",
                w.no_forecast_sentence("the yen")]
    regions.append({"region": "Japan", "lines": jp_lines})
    return regions


def build(r: dict) -> dict | None:
    """Every line of the Year-End 2026 desk note from the results (None without the frozen forecast)."""
    frozen, fcs = r.get("frozen"), r.get("forecast")
    if not frozen or not fcs:
        return None
    usd, eur = frozen["currencies"]["USD"], frozen["currencies"]["EUR"]
    tvo = fcs["term_vs_overnight"]["USD"]
    premium, stale = usd_hurdle(tvo)
    usd_excess, eur_excess = expected_excess(usd), expected_excess(eur)
    usd_lock, usd_line = w.term_out_line("USD", usd_excess, premium, EUR_HURDLE_BP, usd["q50"])
    eur_lock, eur_line = w.term_out_line("EUR", eur_excess, None, EUR_HURDLE_BP, eur["q50"])
    staleness = w.term_staleness_sentence(tvo.get("latest_term_date"), tvo.get("term_age_bd"), stale,
                                          tvo.get("stale_after_bd", 20))
    if staleness:
        usd_line = f"{usd_line} {staleness}"
    verdict, sentence = w.client_verdict(usd_lock, eur_lock, premium)
    turns = {c: fcs["currencies"][c]["turns"]["ye"] for c in ("USD", "EUR")}
    key_points = [
        (f"Dollar: the frozen forecast for SOFR minus interest on reserves on 31 December 2026 is "
         f"{w.signed_bp(usd['q50'])} (median), with a 5-95% range of {w.signed_bp(usd['q05'])} to "
         f"{w.signed_bp(usd['q95'])}; "
         f"the latest level is {w.signed_bp(usd['latest_level'])}."),
        (f"Euro: the frozen forecast for €STR minus the deposit facility rate on 31 December 2026 is "
         f"{w.signed_bp(eur['q50'])}, with a 5-95% range of {w.signed_bp(eur['q05'])} to {w.signed_bp(eur['q95'])}."),
        w.yearend_contrast_sentence(turns["USD"]["mean"], turns["USD"]["share_up"], turns["USD"]["n"],
                                    turns["EUR"]["mean"], turns["EUR"]["share_up"], turns["EUR"]["n"]),
    ]
    models = []
    for c in ("USD", "EUR"):
        cur = fcs["currencies"][c]
        win = next(m for m in cur["models"] if m["model"] == cur["winner"])
        base = next(m for m in cur["models"] if m["model"] == "baseline")
        ci = (((r.get("bootstrap") or {}).get("forecast") or {}).get(c) or {}).get("models", {}).get(
            cur["winner"], {}).get("ci_diff_turn")
        models.append(w.model_comparison_sentence(c, win["label"], win["pinball_turn"], base["pinball_turn"],
                                                  win.get("dm_turn_p_holm", win.get("dm_turn_p")),
                                                  cur["winner"] == "baseline", ci, "dm_turn_p_holm" in win))
    tk = r.get("toolkit")
    backstop = w.backstop_line(tk["latest"]) if tk else None
    term_backtest = w.term_rule_sentence(tvo["saving_vs_on"], tvo["saving_vs_term"], tvo["n_locked"], tvo["n_windows"])
    france_q, france_a, france_e = findings.answer("france", r)
    fr = r.get("france") or {}
    france_lines = [f"{france_a}. {france_e}"]
    if fr:
        repo = fr["repo"]
        france_lines.append(w.repo_treatment_sentence(repo["fr_de_before"], repo["fr_de_after"], repo["it_de_before"],
                                                      repo["it_de_after"], repo["position_before"],
                                                      repo["position_after"],
                                                      findings.adjusted_p(r, "chow_june2024_it_fr",
                                                                          repo["chow_it_fr"]["p_value"])[0],
                                                      repo["latest"]["fr_de"], repo["latest"]["it_de"],
                                                      findings.adjusted_p(r, "chow_june2024_it_fr")[1]))
    scoring = []
    for label, score in (("v1 (pre-registered)", r.get("score")), ("v2 (challenger)", r.get("score_v2"))):
        for c, s in (score or {}).get("currencies", {}).items():
            inside = "inside" if s["inside_interval"] else "outside"
            scoring.append(f"{label}, {c}: actual {w.signed_bp(s['actual'])} on 31 December 2026, {inside} the 5-95% "
                           f"range; error against the median {w.signed_bp(s['error_vs_median'])}; mean pinball loss "
                           f"{s['mean_pinball']:.2f}.")
    if not scoring:
        scoring = ["To be scored after 31 December 2026: the refresh scores both frozen forecasts (v1 and v2) "
                   "automatically once the year-end values are published."]
    score = r.get("score")
    v2f = r.get("frozen_v2")
    challenger = []
    if v2f:
        for c in ("USD", "EUR"):
            a, b = frozen["currencies"][c], v2f["currencies"][c]
            challenger.append(w.v1_v2_sentence(c, a["q50"], a["q05"], a["q90"], a["q95"], b["q50"], b["q05"], b["q90"],
                                               b["q95"], b.get("n_year_ends")))
    v2s = r.get("v2") or {}
    v2_test = []
    for c, e in (v2s.get("currencies") or {}).items():
        m = e["models"]
        v2_test.append(w.v2_test_sentence(c, m["cqr"]["pinball_turn"], m["v1_state"]["pinball_turn"],
                                          m["baseline"]["pinball_turn"], m["cqr"]["coverage"], m["cqr"]["verdict"],
                                          m["v1_state"]["coverage"], sum(a["inside"] for a in e["analogue_test"]),
                                          len(e["analogue_test"])))
    ranked = ranked_risks(r)
    risks = [w.risk_line(x["key"], x["severity"], x["number"], x["explanation"]) for x in ranked if x["severity"] > 0]
    watched = [w.risk_line(x["key"], x["severity"], x["number"], x["explanation"]) for x in ranked
               if x["severity"] == 0]
    overview = regional_overview(r, frozen, r.get("frozen_v2"))
    tails = []
    diag = (r.get("tails") or {}).get("currencies", {})
    for c in ("USD", "EUR"):
        d = diag.get(c)
        if d:
            fz = frozen["currencies"][c]
            tails.append(w.tail_sentence(c, fz["q90"], fz["q95"], d["raw_q"]["q90"], d["raw_q"]["q95"],
                                         d["n_year_ends"], d["pinned_q95"], d["same_pins"]))
    disclosures = [
        "Educational project. Not investment advice. No position is held in any instrument discussed.",
        "Forecasts are statistical estimates from public data with publication lags respected; they are not a view "
        "on central bank decisions.",
        f"Data: ECB Data Portal, New York Fed, FRED, OFR, US Treasury Fiscal Data, Bank of Japan, Bundesbank, Banque "
        f"de France (Webstat), Bank of England, Eurostat. "
        f"Data as of {pd.Timestamp(frozen['data_as_of']).day} {pd.Timestamp(frozen['data_as_of']):%B %Y} at freezing.",
    ]
    created = pd.Timestamp(frozen["created_at"])
    return {
        "title": "Year-End 2026: funding over the turn",
        "frozen_line": (f"Forecast frozen on {created.day} {created:%B %Y}, commit {frozen['git_commit'][:7]} "
                        f"(model {frozen['model_version']}, data as of {frozen['data_as_of']})."),
        "recommendation": {"USD": "Term out" if usd_lock else "Stay overnight",
                           "EUR": "Term out" if eur_lock else "Stay overnight", "lines": [usd_line, eur_line]},
        "key_points": key_points, "forecasts": {"USD": usd, "EUR": eur}, "models": models,
        "funding": [usd_line, eur_line, term_backtest] + ([backstop] if backstop else []),
        "overview": overview, "ranked_risks": ranked, "watched": watched,
        "france": france_lines, "risks": risks, "tails": tails,
        "disclosures": disclosures, "scoring": scoring, "scored": bool(score),
        "v2": {"frozen": v2f, "lines": challenger, "test": v2_test, "caveat": v2s.get("caveat")},
        "client": {"question": findings.QUESTIONS["desk_note"], "verdict": verdict, "sentence": sentence},
        "rule": {"USD": {"excess_bp": usd_excess, "hurdle_bp": premium if premium is not None else EUR_HURDLE_BP,
                         "premium_bp": tvo.get("latest_premium_bp"), "lock": usd_lock, "stale": stale,
                         "term_date": tvo.get("latest_term_date"), "term_age_bd": tvo.get("term_age_bd")},
                 "EUR": {"excess_bp": eur_excess, "hurdle_bp": EUR_HURDLE_BP, "lock": eur_lock}},
        "frozen": frozen,
    }


def markdown(note: dict) -> str:
    """The downloadable desk note: recommendation and client line first, then the regional funding overview, the
    ranked year-end risks, the frozen forecasts, scoring and disclosures (D9 structure)."""
    f = note["forecasts"]
    c = note["client"]
    lines = [f"# {note['title']}", "", "The Price of Collateral, funding outlook", "", note["frozen_line"], "",
             "## Recommendation", "",
             f"- USD: **{note['recommendation']['USD']}**", f"- EUR: **{note['recommendation']['EUR']}**", "",
             f"**{c['question']} {c['verdict']}.** {c['sentence']}", "",
             "## Funding overview", ""]
    for region in note.get("overview", []):
        lines += [f"### {region['region']}", "", *[f"- {x}" for x in region["lines"]], ""]
    lines += ["## Year-end: the main risks", "", *[f"{i}. {x}" for i, x in enumerate(note["risks"], 1)], ""]
    if note.get("watched"):
        lines += ["Watched, not flagged:", "", *[f"- {x}" for x in note["watched"]], ""]
    lines += ["## Key points", "", *[f"- {p}" for p in note["key_points"]], "",
              "## The year-end forecast (bp)", "",
              "| Currency | Target | Model | 5% | Median | 90% | 95% |", "|---|---|---|---|---|---|---|"]
    for cur in ("USD", "EUR"):
        x = f[cur]
        lines.append(f"| {cur} | {x['target']} | {x['model_label']} | {x['q05']:+.1f} | {x['q50']:+.1f} | "
                     f"{x['q90']:+.1f} | {x['q95']:+.1f} |")
    v2f = (note.get("v2") or {}).get("frozen")
    if v2f:
        for cur in ("USD", "EUR"):
            x = v2f["currencies"][cur]
            lines.append(f"| {cur} | {x['target']} | v2 challenger: CQR + year-end analogue | {x['q05']:+.1f} | "
                         f"{x['q50']:+.1f} | {x['q90']:+.1f} | {x['q95']:+.1f} |")
        lines += ["", "v1 is the pre-registered headline; v2 was designed after seeing v1's test-period "
                      "calibration.", "",
                  *[f"- {x}" for x in note["v2"]["lines"]]]
    lines += ["", *note["models"], "", "## What the turn means for funding", "", *[f"- {x}" for x in note["funding"]],
              "", "## Why the 90th and 95th percentiles coincide", "", *[f"- {x}" for x in note.get("tails", [])], "",
              "## Scoring", "", *note["scoring"], "",
              "## Disclosures", "", *[f"- {x}" for x in note["disclosures"]], ""]
    return "\n".join(lines)


RULE_PATH = findings.RESULTS_DIR / "forecast" / "desk_note_rule.json"


def run(path: Path = RULE_PATH) -> dict | None:
    """Write the client rule's inputs and outcome (for the audit and the README); None without the inputs."""
    note = build(findings.load_results())
    if note is None:
        return None
    out = {"verdict": note["client"]["verdict"], "rule": note["rule"],
           "recommendation": {c: note["recommendation"][c] for c in ("USD", "EUR")}}
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
