"""Every generated comparison word must match its numbers (docs/METHODOLOGY.md, U0).

Two layers: (1) on the committed results, each chapter's generated sentence is checked against the
numbers it was built from; (2) each wording function is run on a set of inputs and on the same inputs
with the sign flipped, and the comparison word must flip with the numbers.
"""

from __future__ import annotations

import copy
import re

import pytest

import desk_note
import findings
import wording as w


@pytest.fixture(scope="module")
def r() -> dict:
    return findings.load_results()


# --------------------------------------------------------------------------- #
# 1. Real results
# --------------------------------------------------------------------------- #
def test_desk_note_rule_words_match_numbers(r: dict) -> None:
    note = desk_note.build(r)
    rule = note["rule"]
    for cur, line in zip(("USD", "EUR"), note["recommendation"]["lines"]):
        x = rule[cur]
        lock = x["excess_bp"] > x["hurdle_bp"]
        assert x["lock"] == lock
        assert note["recommendation"][cur] == ("Term out" if lock else "Stay overnight")
        assert line.startswith(f"{cur}: {'Term out' if lock else 'Stay overnight'}")
        assert (" above " if lock else " below ") in line
        assert w.signed_bp(x["excess_bp"]) in line
    n = sum(rule[c]["lock"] for c in ("USD", "EUR"))
    assert note["client"]["verdict"] == {2: "Yes", 1: "Partly", 0: "No"}[n]


def test_desk_note_premium_sign_is_described_correctly(r: dict) -> None:
    note = desk_note.build(r)
    usd = note["rule"]["USD"]
    line = note["recommendation"]["lines"][0]
    if usd["premium_bp"] is not None and not usd["stale"]:
        word = "cheaper than overnight" if usd["premium_bp"] < 0 else "more than overnight"
        assert word in line
    if note["client"]["verdict"] == "No" and usd["premium_bp"] is not None and usd["premium_bp"] < 0:
        assert "cheaper than overnight" in note["client"]["sentence"]


def test_staleness_matches_the_age(r: dict) -> None:
    tvo = r["forecast"]["term_vs_overnight"]["USD"]
    assert tvo["term_stale"] == (tvo["term_age_bd"] > tvo["stale_after_bd"])
    line = desk_note.build(r)["recommendation"]["lines"][0]
    assert ("treated as stale" in line) == tvo["term_stale"]


def test_model_comparison_words(r: dict) -> None:
    for cur in ("USD", "EUR"):
        c = r["forecast"]["currencies"][cur]
        win = next(m for m in c["models"] if m["model"] == c["winner"])
        base = next(m for m in c["models"] if m["model"] == "baseline")
        s = w.model_comparison_sentence(cur, win["label"], win["pinball_turn"], base["pinball_turn"],
                                        win.get("dm_turn_p"), c["winner"] == "baseline")
        if c["winner"] != "baseline":
            assert win["pinball_turn"] <= base["pinball_turn"] and "% lower" in s
            p = win.get("dm_turn_p")
            assert ("not statistically significant" in s) == (p is None or p >= 0.05)


def test_yearend_contrast_words(r: dict) -> None:
    t = {c: r["forecast"]["currencies"][c]["turns"]["ye"] for c in ("USD", "EUR")}
    s = w.yearend_contrast_sentence(t["USD"]["mean"], t["USD"]["share_up"], t["USD"]["n"],
                                    t["EUR"]["mean"], t["EUR"]["share_up"], t["EUR"]["n"])
    assert f"(SOFR minus IOR) {w.rose_or_fell(t['USD']['mean'])}" in s
    assert f"(€STR minus DFR) {w.rose_or_fell(t['EUR']['mean'])}" in s
    same = (t["USD"]["mean"] > 0) == (t["EUR"]["mean"] > 0)
    assert ("same direction" in s) == same


def test_term_rule_backtest_words(r: dict) -> None:
    tvo = r["forecast"]["term_vs_overnight"]["USD"]
    s = w.term_rule_sentence(tvo["saving_vs_on"], tvo["saving_vs_term"], tvo["n_locked"], tvo["n_windows"])
    assert ("saved" if tvo["saving_vs_on"] > 0 else "cost") in s.split("against always borrowing overnight")[0]


def test_corridor_words(r: dict) -> None:
    for cur, s in r["corridors"]["stats"].items():
        text = w.corridor_sentence(cur, s["inside_share"], s["below_floor_share"], s["recent_median_bp"],
                                   s["recent_iqr_bp"], s["start"]) if "inside_share" in s else None
        if text:
            assert f"{w.bp(s['recent_median_bp'])} {w.above_or_below(s['recent_median_bp'])} the policy rate" in text
            assert ("tightly" in text) == (s["recent_iqr_bp"] <= 3)


def test_reserves_words(r: dict) -> None:
    for cur, ra in r["corridors"]["reserves"].items():
        s = w.reserves_sentence(cur, ra["winner"], ra["slope_per_unit"], ra["pressure_point"], ra["pressure_band"],
                                ra["latest_liq"], ra["label"], ra["kink_identified"], ra["boot_edge_share"])
        assert ("rises" if ra["slope_per_unit"] < 0 else "falls") in s
        if ra["kink_identified"]:
            lo, hi = ra["pressure_band"]
            where = "below" if ra["latest_liq"] < lo else "inside" if ra["latest_liq"] <= hi else "above"
            assert f"is {where} that band" in s
        else:
            assert "not identified" in s and f"{ra['pressure_point']:.2f}" not in s


def test_collateral_words(r: dict) -> None:
    for c, reg in r["collateral"]["regressions"].items():
        if c not in ("IT", "FR"):
            continue
        scarcity = abs(reg["std_effect"]["liquidity"]) + abs(reg["std_effect"]["de_holdings"])
        s = w.collateral_sentence(c, reg["verdict"], reg["std_effect"]["credit"], scarcity, reg["r2"],
                                  reg["mean_spread"], reg["latest_spread"])
        assert f"{w.more_or_less(reg['mean_spread'])} than German" in s
        assert w.verdict_phrase(reg["verdict"]) in s


def test_story_words(r: dict) -> None:
    it = r["collateral"]["regressions"]["IT"]
    repo = r["france"]["repo"]
    _, e = w.story_answer(it["mean_spread"], it["latest_spread"], repo["latest"]["fr_de"], repo["latest"]["it_de"])
    assert ("now costs more than Italian" in e) == (repo["latest"]["fr_de"] > repo["latest"]["it_de"])


def test_repo_treatment_words(r: dict) -> None:
    repo = r["france"]["repo"]
    s = w.repo_treatment_sentence(repo["fr_de_before"], repo["fr_de_after"], repo["it_de_before"],
                                  repo["it_de_after"], repo["position_before"], repo["position_after"],
                                  repo["chow_it_fr"]["p_value"], repo["latest"]["fr_de"], repo["latest"]["it_de"])
    closer = repo["position_after"] > repo["position_before"]
    assert ("closer to Italian" in s) == closer
    assert ("cost more than Italian" in s) == (repo["latest"]["fr_de"] > repo["latest"]["it_de"])


def test_japan_words(r: dict) -> None:
    j = r["japan"]
    gap = (j["latest"]["tona"] - j["latest"]["policy"]) * 100
    _, e = findings.japan_answer(r)
    assert f"{w.above_or_below(gap)} the policy rate" in e


def test_tail_words(r: dict) -> None:
    for cur, d in r["tails"]["currencies"].items():
        fz = r["frozen"]["currencies"][cur]
        s = w.tail_sentence(cur, fz["q90"], fz["q95"], d["raw_q"]["q90"], d["raw_q"]["q95"], d["n_year_ends"],
                            d["pinned_q95"], d["same_pins"])
        assert ("were swapped" in s) == (d["raw_q"]["q90"] > d["raw_q"]["q95"])


# --------------------------------------------------------------------------- #
# 2. Sign-flipped inputs: the word flips with the number
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("excess,premium", [(5.0, -2.0), (-5.0, -2.0), (3.0, 2.0), (1.0, 2.0), (-3.0, 2.0)])
def test_term_out_line_flips(excess: float, premium: float) -> None:
    lock, line = w.term_out_line("USD", excess, premium, 1.0)
    assert lock == (excess > premium)
    assert (" above " if excess > premium else " below ") in line
    assert ("cheaper than overnight" in line) == (premium < 0)
    lock2, line2 = w.term_out_line("USD", -excess, -premium, 1.0)
    assert lock2 == (-excess > -premium)


def test_client_verdict_all_cases() -> None:
    assert w.client_verdict(True, True)[0] == "Yes"
    assert w.client_verdict(True, False)[0] == "Partly"
    assert w.client_verdict(False, True)[0] == "Partly"
    assert w.client_verdict(False, False, -2.0)[0] == "No"
    assert "cheaper than overnight" in w.client_verdict(False, False, -2.0)[1]
    assert "cheaper than overnight" not in w.client_verdict(False, False, 2.0)[1]


@pytest.mark.parametrize("x", [3.0, -3.0])
def test_small_words_flip(x: float) -> None:
    assert w.above_or_below(x) == ("above" if x > 0 else "below")
    assert w.wider_or_narrower(x) == ("wider" if x > 0 else "narrower")
    assert w.rose_or_fell(x) == ("rose" if x > 0 else "fell")
    assert w.more_or_less(x) == ("more" if x > 0 else "less")


@pytest.mark.parametrize("sign", [1, -1])
def test_sentences_flip_with_sign(sign: int) -> None:
    s = w.collateral_sentence("IT", "credit", 5.0 * sign, 2.0, 0.5, 8.0 * sign, 4.0 * sign)
    assert ("more than German" if sign > 0 else "less than German") in s
    s = w.yearend_contrast_sentence(5.0 * sign, 0.8, 8, -3.0 * sign, 0.2, 7)
    assert ("(SOFR minus IOR) rose" if sign > 0 else "(SOFR minus IOR) fell") in s
    assert "opposite direction" in s
    s = w.term_rule_sentence(1000.0 * sign, 500.0, 3, 10)
    assert (" saved USD 1.0k against always borrowing overnight" if sign > 0
            else " cost USD 1.0k against always borrowing overnight") in s
    s = w.case_sentence("X", "USD", 10.0 * sign, "2020-03-17", 0.0)
    assert ("above its level" if sign > 0 else "below its level") in s
    s = w.decomposition_sentence("May 2024", "Sep 2026", 50, 50 + 40 * sign, 30 * sign, 10 * sign)
    assert ("widening" if sign > 0 else "tightening") in s
    s = w.event_sentence("E", "Dec 2024", 12.0 * sign, 0.95)
    assert ("widened" if sign > 0 else "narrowed") in s
    s = w.japan_change_sentence("2024-03-19", 10.0 * sign, 0, 0.9)
    assert ("rise" if sign > 0 else "cut") in s
    _, e = w.japan_answer(5, 5, 1.0, 3.0, 2.0 * sign)
    assert ("above the policy rate" if sign > 0 else "below the policy rate") in e
    s = w.repo_treatment_sentence(5.0, 5.0 + 3 * sign, 10.0, 10.0, 0.4, 0.4 + 0.1 * sign, 0.2, 9.0 + sign * 5, 9.0)
    assert ("closer to Italian" if sign > 0 else "away from Italian") in s
    assert ("cost more than Italian" in s) == (sign > 0)


@pytest.mark.parametrize("p,word", [(0.01, "statistically significant (p = 0.010)"),
                                    (0.30, "not statistically significant (p = 0.300)")])
def test_significance_words(p: float, word: str) -> None:
    assert w.significance_phrase(p) == word
    s = w.model_comparison_sentence("USD", "State model", 1.0, 2.0, p, False)
    assert word in s and "50% lower" in s


@pytest.mark.parametrize("latest,where", [(1.0, "below"), (2.5, "inside"), (4.0, "above")])
def test_reserves_band_position(latest: float, where: str) -> None:
    s = w.reserves_sentence("USD", "piecewise", -6.0, 2.5, [2.0, 3.0], latest, "reserves")
    assert f"is {where} that band" in s
    s = w.reserves_sentence("USD", "piecewise", -6.0, 2.5, [2.0, 3.0], latest, "reserves", False, 0.5)
    assert "not identified" in s and "band of" not in s


def test_tail_sentence_crossing_flips() -> None:
    s = w.tail_sentence("USD", 31.7, 31.8, 31.8, 31.6, 8, ["2018-12-31"], True)
    assert "were swapped" in s
    s = w.tail_sentence("USD", 31.6, 31.8, 31.6, 31.8, 8, ["2018-12-31"], True)
    assert "were swapped" not in s


def test_desk_note_flips_when_forecast_flips(r: dict) -> None:
    flipped = copy.deepcopy(r)
    for cur in ("USD", "EUR"):
        for day in flipped["frozen"]["currencies"][cur]["path"].values():
            day["q50"] += 40
    note = desk_note.build(flipped)
    assert note["client"]["verdict"] == "Yes"
    for cur, line in zip(("USD", "EUR"), note["recommendation"]["lines"]):
        assert " above " in line and line.startswith(f"{cur}: Term out")
    # A stale term rate switches the dollar hurdle to 1 bp and says so.
    stale = copy.deepcopy(r)
    stale["forecast"]["term_vs_overnight"]["USD"].update(term_stale=True, term_age_bd=30)
    line = desk_note.build(stale)["recommendation"]["lines"][0]
    assert "treated as stale" in line and "1 bp hurdle" in line


def test_no_sentence_prints_a_negative_magnitude_after_more_or_less() -> None:
    """'cost -3.0 bp more' would contradict itself: magnitudes are printed unsigned."""
    s = w.collateral_sentence("FR", "scarcity", -1.0, 2.0, 0.3, -4.0, -2.0)
    assert not re.search(r"-\d+\.\d bp (more|less)", s)


@pytest.mark.parametrize("hi2", [40.0, 20.0])
def test_v1_v2_width_word_flips(hi2: float) -> None:
    s = w.v1_v2_sentence("USD", 6.0, -5.0, 31.7, 31.8, 8.0, 0.0, 30.0, hi2, 8)
    wider = (hi2 - 0.0) - (31.8 + 5.0)
    assert (" wider" in s) == (wider > 0) and (" narrower" in s) == (wider < 0)


def test_v2_test_sentence_words(r: dict) -> None:
    for c, e in r["v2"]["currencies"].items():
        m = e["models"]
        s = w.v2_test_sentence(c, m["cqr"]["pinball_turn"], m["v1_state"]["pinball_turn"], m["baseline"]["pinball_turn"],
                               m["cqr"]["coverage"], m["cqr"]["verdict"], m["v1_state"]["coverage"],
                               sum(a["inside"] for a in e["analogue_test"]), len(e["analogue_test"]))
        assert ("lower than v1" in s) == (m["cqr"]["pinball_turn"] < m["v1_state"]["pinball_turn"])
        assert "not a clean out-of-sample test" in s


def test_event_summary_words(r: dict) -> None:
    s = r["france_daily"]["events_summary"]
    rows = r["france_daily"]["events"]
    assert s["n_unusual"] == sum(e["percentile"] >= 0.9 for e in rows)
    assert s["n_widened"] == sum(e["change_bp"] > 0 for e in rows)
    text = w.event_study_summary_sentence(s["n"], s["n_unusual"], s["mean_change"], s["n_widened"])
    assert w.signed_bp(s["mean_change"]) in text
    for e in rows:
        line = w.daily_event_sentence(e["event"], e["event_day"], e["change_bp"], e["percentile"])
        assert ("widened" if e["change_bp"] > 0 else "narrowed" if e["change_bp"] < 0 else "unchanged") in line
