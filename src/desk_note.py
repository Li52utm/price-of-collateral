"""Chapter VII: the Year-End 2026 desk note, built from the frozen forecast and the results files.

Pure functions (no Streamlit): `build(results)` returns every line the page shows, and `markdown(note)`
the downloadable version. The client rule is fixed in docs/METHODOLOGY.md, Phase 6.
"""

from __future__ import annotations

import pandas as pd

import findings
import wording as w

WINDOW_START_BD = 7      # business days before 31 Dec 2026 (the Phase 2 term rule)
WINDOW_DAYS = 14
EUR_HURDLE_BP = 1.0
YEAR_END = pd.Timestamp("2026-12-31")


def window_days(path: dict) -> list[str]:
    days = sorted(pd.Timestamp(d) for d in path)
    before = [d for d in days if d <= YEAR_END]
    start = before[-(WINDOW_START_BD + 1)] if len(before) > WINDOW_START_BD else before[0]
    end = start + pd.Timedelta(days=WINDOW_DAYS)
    return [str(d.date()) for d in days if start <= d < end]


def expected_excess(fc: dict) -> float:
    days = window_days(fc["path"])
    medians = [fc["path"][d]["q50"] for d in days]
    return float(sum(medians) / len(medians) - fc["latest_level"])


def build(r: dict) -> dict | None:
    frozen, fcs = r.get("frozen"), r.get("forecast")
    if not frozen or not fcs:
        return None
    usd, eur = frozen["currencies"]["USD"], frozen["currencies"]["EUR"]
    tvo = fcs["term_vs_overnight"]["USD"]
    premium = tvo.get("latest_premium_bp")
    usd_lock, usd_line = w.term_out_line("USD", expected_excess(usd), premium, EUR_HURDLE_BP)
    eur_lock, eur_line = w.term_out_line("EUR", expected_excess(eur), None, EUR_HURDLE_BP)
    verdict, sentence = w.client_verdict(usd_lock, eur_lock)
    turns = {c: fcs["currencies"][c]["turns"]["ye"] for c in ("USD", "EUR")}
    key_points = [
        (f"Dollar: the frozen forecast for SOFR minus interest on reserves on 31 December 2026 is "
         f"{w.signed_bp(usd['q50'])} (median), with a 5-95% range of {w.signed_bp(usd['q05'])} to {w.signed_bp(usd['q95'])}; "
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
        models.append(w.model_comparison_sentence(c, win["label"], win["pinball_turn"], base["pinball_turn"],
                                                  win.get("dm_turn_p"), cur["winner"] == "baseline"))
    term_backtest = w.term_rule_sentence(tvo["saving_vs_on"], tvo["saving_vs_term"], tvo["n_locked"], tvo["n_windows"])
    france_q, france_a, france_e = findings.answer("france", r)
    fr = r.get("france") or {}
    france_lines = [f"{france_a}. {france_e}"]
    if fr:
        repo = fr["repo"]
        france_lines.append(w.repo_treatment_sentence(repo["fr_de_before"], repo["fr_de_after"], repo["it_de_before"],
                                                      repo["it_de_after"], repo["position_before"], repo["position_after"],
                                                      repo["chow_it_fr"]["p_value"], repo["latest"]["fr_de"],
                                                      repo["latest"]["it_de"]))
    score = r.get("score")
    if score:
        scoring = []
        for c, s in score["currencies"].items():
            inside = "inside" if s["inside_interval"] else "outside"
            scoring.append(f"{c}: actual {w.signed_bp(s['actual'])} on 31 December 2026, {inside} the 5-95% range; "
                           f"error against the median {w.signed_bp(s['error_vs_median'])}; mean pinball loss "
                           f"{s['mean_pinball']:.2f}.")
    else:
        scoring = ["To be scored after 31 December 2026: the refresh scores the frozen forecast automatically once the "
                   "year-end values are published."]
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
        "funding": [usd_line, eur_line, term_backtest], "france": france_lines, "risks": risks,
        "disclosures": disclosures, "scoring": scoring, "scored": bool(score),
        "client": {"question": findings.QUESTIONS["desk_note"], "verdict": verdict, "sentence": sentence},
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
    lines += ["", *note["models"], "", "## What the turn means for funding", "", *[f"- {x}" for x in note["funding"]],
              "", "## France", "", *note["france"], "", "## Risks", "", *[f"- {x}" for x in note["risks"]], "",
              "## Scoring", "", *note["scoring"], "", "## Disclosures", "", *[f"- {x}" for x in note["disclosures"]], "",
              f"**{note['client']['question']} {note['client']['verdict']}.** {note['client']['sentence']}", ""]
    return "\n".join(lines)
