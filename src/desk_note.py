"""Chapter VII: the Year-End 2026 desk note, built from the frozen forecast and the results files.

Pure functions (no Streamlit): `build(results)` returns every line the page shows, and `markdown(note)`
the downloadable version. The client rule is fixed in docs/METHODOLOGY.md, Phase 6.
"""

from __future__ import annotations

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
    risks = [
        (f"The dollar upper tail: the 95th percentile ({w.signed_bp(usd['q95'])}) is far above the median; a "
         "reserve drain or heavy Treasury settlement near the turn would push SOFR towards it."),
        ("The euro forecast rests on four training year-ends; €STR measures unsecured deposits, not repo, so euro "
         "repo can behave differently at the turn."),
        ("The models beat the naive baseline on the test period, but not always significantly; treat the ranges, not "
         "the medians, as the message." if any("not statistically" in m for m in models) else
         "The models beat the naive baseline significantly on the test period, but a single turn can still land in "
         "the tails; treat the ranges, not the medians, as the message."),
        "French spreads are driven by domestic politics, which no model here forecasts.",
    ]
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
        f"Data: ECB Data Portal, New York Fed, FRED, OFR, US Treasury Fiscal Data, Bank of Japan, Bundesbank. "
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
        "funding": [usd_line, eur_line, term_backtest], "france": france_lines, "risks": risks, "tails": tails,
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
    """The downloadable desk note."""
    f = note["forecasts"]
    lines = [f"# {note['title']}", "", "The Price of Collateral, desk note", "", note["frozen_line"], "",
             "## Recommendation", "",
             f"- USD: **{note['recommendation']['USD']}**", f"- EUR: **{note['recommendation']['EUR']}**", "",
             "## Key points", "", *[f"- {p}" for p in note["key_points"]], "",
             "## The year-end forecast (bp)", "",
             "| Currency | Target | Model | 5% | Median | 90% | 95% |", "|---|---|---|---|---|---|---|"]
    for c in ("USD", "EUR"):
        x = f[c]
        lines.append(f"| {c} | {x['target']} | {x['model_label']} | {x['q05']:+.1f} | {x['q50']:+.1f} | "
                     f"{x['q90']:+.1f} | {x['q95']:+.1f} |")
    v2f = (note.get("v2") or {}).get("frozen")
    if v2f:
        for c in ("USD", "EUR"):
            x = v2f["currencies"][c]
            lines.append(f"| {c} | {x['target']} | v2 challenger: CQR + year-end analogue | {x['q05']:+.1f} | "
                         f"{x['q50']:+.1f} | {x['q90']:+.1f} | {x['q95']:+.1f} |")
        lines += ["", "v1 is the pre-registered headline; v2 was designed after seeing v1's test-period "
                      "calibration.", "",
                  *[f"- {x}" for x in note["v2"]["lines"]]]
    lines += ["", *note["models"], "", "## What the turn means for funding", "", *[f"- {x}" for x in note["funding"]],
              "", "## France", "", *note["france"], "", "## Risks", "", *[f"- {x}" for x in note["risks"]], "",
              "## Why the 90th and 95th percentiles coincide", "", *[f"- {x}" for x in note.get("tails", [])], "",
              "## Scoring", "", *note["scoring"], "",
              "## Disclosures", "", *[f"- {x}" for x in note["disclosures"]], "",
              f"**{note['client']['question']} {note['client']['verdict']}.** {note['client']['sentence']}", ""]
    return "\n".join(lines)
