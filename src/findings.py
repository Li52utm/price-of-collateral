"""The question / answer pair of every chapter and the README findings, built from the results files.

Pure functions of the results dictionaries (no Streamlit), so the dashboard, the README auto-block and
the final report state the same generated conclusions. `load_results(results_dir)` reads every
summary; missing files give None and the answer says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import wording as w

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
SUMMARIES = {"forecast": "forecast/summary.json", "corridors": "corridors/summary.json",
             "collateral": "collateral/summary.json", "france": "france/summary.json",
             "japan": "japan/summary.json", "frozen": "forecasts/yearend_2026.json",
             "score": "forecasts/yearend_2026_score.json", "validation": "data_validation.json",
             "tails": "forecast/tail_diagnosis.json", "france_daily": "france/daily_summary.json",
             "bootstrap": "inference/bootstrap.json", "tests": "inference/tests.json",
             "calibration": "inference/calibration.json", "frozen_v2": "forecasts/yearend_2026_v2.json",
             "v2": "forecast/v2_summary.json", "score_v2": "forecasts/yearend_2026_v2_score.json",
             "robustness": "robustness/table.json", "construction": "france/construction.json",
             "runway": "desk/runway.json", "autonomous": "desk/autonomous.json",
             "toolkit": "desk/toolkit.json", "holders": "desk/holders.json",
             "curve": "france/curve.json",
             "facilities": "desk/facilities.json",
             "uk": "desk/uk.json",
             "overview": "desk/overview.json"}

QUESTIONS = {
    "story": "What is repo, and why does the bond you hand over matter?",
    "corridors": "Do the ECB, the Fed and the BoJ keep overnight rates where they want them, and what happens as "
                 "balance sheets shrink?",
    "collateral": "Is the extra repo cost of Italian and French collateral about credit risk or scarcity?",
    "france": "Will French OATs bounce back, and what would it take?",
    "calendar": "Why do euro year-ends behave differently from dollar year-ends, and can funding spikes be forecast?",
    "japan": "Does Japanese overnight pricing follow the BoJ out of negative rates?",
    "desk_note": "Would I advise a client to term out their year-end funding?",
}
NOT_AVAILABLE = ("Not available yet", "The results file for this chapter is missing; run scripts/run_all.py to create "
                                      "it.")


def load_results(results_dir: Path = RESULTS_DIR) -> dict:
    """Every chapter summary under results/ (None where a file is missing)."""
    out = {}
    for key, rel in SUMMARIES.items():
        path = results_dir / rel
        out[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return out


def adjusted_p(r: dict, test_id: str, fallback: float | None = None) -> tuple[float | None, bool]:
    """(Holm-adjusted p of a registered test, True) or (fallback, False) if the inference file is missing."""
    tests = (r.get("tests") or {}).get("tests", [])
    for t in tests:
        if t["id"] == test_id:
            return t["p_holm"], True
    return fallback, False


def collateral_verdict(r: dict, country: str) -> str:
    """The chapter III verdict after the U2 'too close to call' rule."""
    reg = r["collateral"]["regressions"][country]
    cs = ((r.get("bootstrap") or {}).get("credit_scarcity") or {}).get(country)
    return w.final_verdict(reg["verdict"], cs["too_close_to_call"] if cs else None)


# --------------------------------------------------------------------------- #
# Per chapter
# --------------------------------------------------------------------------- #
def story_answer(r: dict) -> tuple[str, str]:
    """Chapter I answer: what repo is and what the collateral premium has been."""
    col, fr = r.get("collateral"), r.get("france")
    if not col or not fr:
        return NOT_AVAILABLE
    it = col["regressions"]["IT"]
    repo = fr["repo"]
    return w.story_answer(it["mean_spread"], it["latest_spread"], repo["latest"]["fr_de"], repo["latest"]["it_de"])


def corridors_answer(r: dict) -> tuple[str, str]:
    """Chapter II answer: how tightly each corridor held and the reserves slope."""
    c = r.get("corridors")
    ci = ((r.get("bootstrap") or {}).get("reserves_slope") or {}).get("USD")
    return w.corridors_answer(c["stats"], c["reserves"], ci) if c else NOT_AVAILABLE


def collateral_answer(r: dict) -> tuple[str, str]:
    """Chapter III answer: credit or scarcity, after Holm and the 'too close to call' rule."""
    c = r.get("collateral")
    if not c:
        return NOT_AVAILABLE
    it, fr = c["regressions"]["IT"], c["regressions"]["FR"]
    p_it, _ = adjusted_p(r, "chow_qt_IT", it["chow"]["p_value"])
    p_fr, _ = adjusted_p(r, "chow_qt_FR", fr["chow"]["p_value"])
    cs = (r.get("bootstrap") or {}).get("credit_scarcity") or {}
    lines = [w.credit_scarcity_ci_sentence(k, v["point"]["difference"], v["difference"]["lower"],
                                           v["difference"]["upper"]) for k, v in cs.items()]
    return w.collateral_answer(collateral_verdict(r, "IT"), collateral_verdict(r, "FR"), p_it, p_fr, lines)


def france_answer(r: dict) -> tuple[str, str]:
    """Chapter IV answer: France's episode status (daily rule) and recovery conditions."""
    f = r.get("france")
    if not f:
        return NOT_AVAILABLE
    v, now, e, cs = f["survival"], f["france_now"], f["euro_wide"], f["conditions_share"]
    c = now["conditions"]
    share = e["cum_france_specific"] / e["cum_change"] if e["cum_change"] else float("nan")
    status = None
    daily = r.get("france_daily")
    if daily:  # the daily rule (U1) is the headline; the monthly rule is the robustness check
        b = daily["rules"]["blowout"][str(int(daily_threshold(daily)))]["status"]
        g = daily["rules"]["gradual"]
        g_main = next(iter(g.values()))["status"]
        status = w.daily_status_phrase(b["in_episode"], b.get("start"), daily["rules"]["now"]["spread"],
                                       daily["rules"]["now"]["date"], g_main["in_episode"], now["in_episode"])
    return w.oat_answer(now["in_episode"] if not daily else b["in_episode"], v["median_months"],
                        1 - v["at"]["12"]["survival"], cs["ecb_cut"][0], cs["peers_tightening"][0],
                        cs["eurosystem_buying"][0], c["ecb_cut"], c["peers_tightening"], c["eurosystem_buying"], share,
                        status, b.get("p_recover_next_12m") if daily and b["in_episode"] else None)


def daily_threshold(daily: dict) -> float:
    """The main daily blowout threshold (the first key written by france_daily.daily_rules)."""
    return float(next(iter(daily["rules"]["blowout"])))


def model_winner(fc: dict, currency: str) -> tuple[bool, float | None]:
    """(a regression beat the baseline on turn days, turn-day DM p-value of the winner)."""
    cur = fc["currencies"][currency]
    winner = cur["winner"]
    if winner == "baseline":
        return False, None
    row = next(m for m in cur["models"] if m["model"] == winner)
    return True, row.get("dm_turn_p_holm", row.get("dm_turn_p"))


def calendar_answer(r: dict) -> tuple[str, str]:
    """Chapter V answer: whether the models beat the baseline (Holm-adjusted) and calibration."""
    fc = r.get("forecast")
    if not fc:
        return NOT_AVAILABLE
    uw, up = model_winner(fc, "USD")
    ew, ep = model_winner(fc, "EUR")
    cal = r.get("calibration") or {}
    verdicts = {c: cal[c]["verdict"] for c in ("USD", "EUR") if c in cal}
    return w.calendar_answer(uw, ew, up, ep, fc["currencies"]["USD"]["turns"]["ye"]["mean"],
                             fc["currencies"]["EUR"]["turns"]["ye"]["mean"], fc["test_start"][:4], verdicts)


def japan_answer(r: dict) -> tuple[str, str]:
    """Chapter VI answer: same-day pass-through and the half-lives with their intervals."""
    j = r.get("japan")
    if not j:
        return NOT_AVAILABLE
    same_day = sum(1 for c in j["changes"] if c["tona"].get("half_gap_days") == 0)
    latest_gap = (j["latest"]["tona"] - j["latest"]["policy"]) * 100
    hl = (r.get("bootstrap") or {}).get("japan_half_life") or {}
    return w.japan_answer(len(j["changes"]), same_day, j["ecm_exit"]["half_life_days"],
                          j["ecm_negative"]["half_life_days"], latest_gap, hl.get("exit"), hl.get("negative"))


def desk_note_answer(r: dict) -> tuple[str, str]:
    """Chapter VII answer: the client verdict from the desk note rule."""
    import desk_note
    note = desk_note.build(r)
    if note is None:
        return NOT_AVAILABLE
    return note["client"]["verdict"], note["client"]["sentence"]


def construction_lines(r: dict) -> list[str]:
    """D0 caveat sentences on the daily OAT-Bund spread (empty if the result file is missing)."""
    c = r.get("construction")
    if not c:
        return []
    g, m = c["gap"], c["monthly"]
    return [w.construction_sentence(g["mean_bp"], g["recent_mean_bp"], c["latest_spread_current_bp"],
                                    c["latest_spread_cm_bp"], c["small"], c["small_gap_bp"], g["n_days"]),
            w.construction_monthly_sentence(m["oat_tec10_vs_irs_fr"]["mean_bp"], m["bund_current_vs_irs_de"]["mean_bp"],
                                            m["bund_cm_vs_irs_de"]["mean_bp"], m["oat_tec10_vs_irs_fr"]["n_months"])]


def runway_lines(r: dict) -> list[str]:
    """D1 sentences: distance to the euro pressure band, the drain, the scenarios and the trend test."""
    rw = r.get("runway")
    if not rw:
        return []
    tr, sens = rw["trend"]["main"], rw["trend"]["without_turn_days"]
    return [w.runway_distance_sentence(rw["latest_bn"], w.pd_day(rw["latest_date"]), rw["boundaries_bn"],
                                       rw["distance_bn"]),
            w.runway_drift_sentence(rw["drift"]["liquidity_bn_per_week"], rw["drift"]["securities_bn_per_week"]),
            w.runway_scenario_sentence(rw["scenarios"]),
            w.spread_trend_sentence(tr["slope_bp_per_year"], tr["ci"][0], tr["ci"][1], tr["p_value"], tr["verdict"],
                                    tr["first_bp"], tr["last_bp"], sens["verdict"])]


def treasury_cash_lines(r: dict) -> list[str]:
    """D2 sentences: one per currency, then the one-line answer (empty if the result file is missing)."""
    a = r.get("autonomous")
    if not a:
        return []
    lines = []
    for cur in ("EUR", "USD"):
        v = a["currencies"][cur]
        f = v["full"]
        lines.append(w.treasury_cash_sentence(cur, f["coef"]["cash"], *f["ci"]["cash"],
                                              f.get("p_cash_holm", f["p"]["cash"]), v["oos"]["r2_oos"],
                                              f["coef"]["liq"], *f["ci"]["liq"], v["verdict"]))
    lines.append(w.treasury_cash_answer(a["currencies"]["EUR"]["verdict"], a["currencies"]["USD"]["verdict"]))
    return lines


def holder_lines(r: dict) -> list[str]:
    """D4 sentences: the cross-country summary then one line per country (empty if the result is missing)."""
    h = r.get("holders")
    if not h:
        return []
    shifts = {c: v["shift"] for c, v in h["countries"].items() if v["shift"]}
    return [w.holder_summary_sentence(shifts), *[w.holder_shift_sentence(c, s) for c, s in shifts.items()]]


def france_absorption_line(r: dict) -> str | None:
    """D4: who absorbed France's new supply (None if the result is missing)."""
    h = r.get("holders")
    return w.france_absorption_sentence(h["france_absorption"]) if h else None


def steepness_line(r: dict) -> str | None:
    """D5: France's 2s10s against Germany's (None if the result is missing)."""
    c = r.get("curve")
    return w.steepness_sentence(c["main"], c["sensitivity_current_bonds"]["verdict"]) if c else None


def facility_line(r: dict) -> str | None:
    """D6: the facility-pricing comparison (None if the result is missing)."""
    f = r.get("facilities")
    return w.facility_sentence(f["rows"]) if f else None


def uk_lines(r: dict) -> list[str]:
    """D7 sentences: reserves supplied through repo, then SONIA against Bank Rate (empty if missing)."""
    u = r.get("uk")
    if not u:
        return []
    return [w.uk_repo_sentence(u["weekly"], u["trend"]), w.uk_spread_sentence(u["spread"], u["spearman_spread_share"])]


ANSWERS = {"story": story_answer, "corridors": corridors_answer, "collateral": collateral_answer,
           "france": france_answer, "calendar": calendar_answer, "japan": japan_answer,
           "desk_note": desk_note_answer}


def answer(key: str, r: dict) -> tuple[str, str, str]:
    """(question, answer, explanation) for a chapter."""
    try:
        a, e = ANSWERS[key](r)
    except (KeyError, TypeError):
        a, e = NOT_AVAILABLE
    return QUESTIONS[key], a, e


def readme_findings(results_dir: Path = RESULTS_DIR) -> list[str]:
    """One generated line per chapter for the README auto-block."""
    r = load_results(results_dir)
    lines = []
    for key in ("corridors", "collateral", "france", "calendar", "japan", "desk_note"):
        q, a, e = answer(key, r)
        badges = [f"{w.robustness_badge_text(s['holds'], s['n'], s['not_computable'])} ({k})"
                  for k, s in ((r.get("robustness") or {}).get("summary") or {}).items() if s["chapter"] == key]
        lines.append(f"**{q}** {a}. {e}" + (f" *{'; '.join(badges)}.*" if badges else ""))
    lines += desk_findings(r)
    return lines


def desk_findings(r: dict) -> list[str]:
    """The desk upgrade's headline lines for the README (each generated; missing results are skipped)."""
    out = []
    rw = runway_lines(r)
    if rw:
        out.append(f"**Euro runway.** {rw[0]} {rw[3]}")
    cash = treasury_cash_lines(r)
    if cash:
        out.append(f"**Treasury cash.** {cash[-1]}")
    fac = facility_line(r)
    if fac:
        out.append(f"**Repo backstops.** {fac}")
    uk = uk_lines(r)
    if uk:
        out.append(f"**United Kingdom.** {uk[0].split(': ')[0]}.")
    steep = steepness_line(r)
    if steep:
        out.append(f"**French curve.** {steep.split(': ')[0]}.")
    return out
