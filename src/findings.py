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
             "v2": "forecast/v2_summary.json", "score_v2": "forecasts/yearend_2026_v2_score.json"}

QUESTIONS = {
    "story": "What is repo, and why does the bond you hand over matter?",
    "corridors": "Do the ECB, the Fed and the BoJ keep overnight rates where they want them, and what happens as balance sheets shrink?",
    "collateral": "Is the extra repo cost of Italian and French collateral about credit risk or scarcity?",
    "france": "Will French OATs bounce back, and what would it take?",
    "calendar": "Why do euro year-ends behave differently from dollar year-ends, and can funding spikes be forecast?",
    "japan": "Does Japanese overnight pricing follow the BoJ out of negative rates?",
    "desk_note": "Would I advise a client to term out their year-end funding?",
}
NOT_AVAILABLE = ("Not available yet", "The results file for this chapter is missing; run scripts/run_all.py to create it.")


def load_results(results_dir: Path = RESULTS_DIR) -> dict:
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
    col, fr = r.get("collateral"), r.get("france")
    if not col or not fr:
        return NOT_AVAILABLE
    it = col["regressions"]["IT"]
    repo = fr["repo"]
    return w.story_answer(it["mean_spread"], it["latest_spread"], repo["latest"]["fr_de"], repo["latest"]["it_de"])


def corridors_answer(r: dict) -> tuple[str, str]:
    c = r.get("corridors")
    ci = ((r.get("bootstrap") or {}).get("reserves_slope") or {}).get("USD")
    return w.corridors_answer(c["stats"], c["reserves"], ci) if c else NOT_AVAILABLE


def collateral_answer(r: dict) -> tuple[str, str]:
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
    j = r.get("japan")
    if not j:
        return NOT_AVAILABLE
    same_day = sum(1 for c in j["changes"] if c["tona"].get("half_gap_days") == 0)
    latest_gap = (j["latest"]["tona"] - j["latest"]["policy"]) * 100
    hl = (r.get("bootstrap") or {}).get("japan_half_life") or {}
    return w.japan_answer(len(j["changes"]), same_day, j["ecm_exit"]["half_life_days"],
                          j["ecm_negative"]["half_life_days"], latest_gap, hl.get("exit"), hl.get("negative"))


def desk_note_answer(r: dict) -> tuple[str, str]:
    import desk_note
    note = desk_note.build(r)
    if note is None:
        return NOT_AVAILABLE
    return note["client"]["verdict"], note["client"]["sentence"]


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
    r = load_results(results_dir)
    lines = []
    for key in ("corridors", "collateral", "france", "calendar", "japan", "desk_note"):
        q, a, e = answer(key, r)
        lines.append(f"**{q}** {a}. {e}")
    return lines
