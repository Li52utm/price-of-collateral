"""D9: the restructured desk note (regional overview, ranked risks) and its severity rules."""

from __future__ import annotations

import pytest

import desk_note as D
import findings
import wording as w


def test_severity_rules() -> None:
    assert D.severity_euro_liquidity({"upper": -3, "kink": -2, "lower": -1}) == 1.0
    assert D.severity_euro_liquidity({"upper": -3, "kink": -2, "lower": 1}) == 0.67
    assert D.severity_euro_liquidity({"upper": -3, "kink": 2, "lower": 5}) == 0.33
    assert D.severity_euro_liquidity({"upper": 1, "kink": 2, "lower": 5}) == 0.0
    assert D.severity_euro_liquidity(None) == 0.0
    assert D.severity_us_reserves(0.0) == 1.0 and D.severity_us_reserves(-4.0) == 0.5
    assert D.severity_us_reserves(-6.0) == 0.0
    assert D.severity_backstop(2, 0.0) == 1.0 and D.severity_backstop(0, 1.2) == 0.5
    assert D.severity_backstop(0, 0.5) == 0.0
    assert D.severity_france(True, None) == 1.0 and D.severity_france(False, "unusual") == 0.5
    assert D.severity_france(False, "within range") == 0.0
    assert D.severity_drift("drifting up") == 1.0 and D.severity_drift("no significant trend") == 0.0
    assert D.severity_calibration(["well calibrated"], True) == 1.0
    assert D.severity_calibration(["too wide", "well calibrated"], False) == 0.5
    assert D.severity_calibration(["well calibrated"], False) == 0.0


def test_rank_risks_by_severity_then_fixed_order() -> None:
    items = [{"key": "calibration", "severity": 1.0}, {"key": "us_backstop", "severity": 0.5},
             {"key": "euro_liquidity", "severity": 1.0}, {"key": "france", "severity": 0.0}]
    assert [x["key"] for x in D.rank_risks(items)] == ["euro_liquidity", "calibration", "us_backstop", "france"]


@pytest.mark.parametrize("change,word", [(9.0, "up 9.0 bp"), (-9.0, "down 9.0 bp"), (0.01, "unchanged")])
def test_level_change_phrase(change: float, word: str) -> None:
    s = w.level_change_phrase("SOFR minus IORB", {"date": "2026-11-03", "value": 7.0, "change_1m": change})
    assert s.startswith("SOFR minus IORB: +7.0 bp (3 November 2026)") and word in s
    money = w.level_change_phrase("reserves", {"date": "2026-11-03", "value": 2.89, "change_1m": -0.04}, "USD tn", 2)
    assert "USD 2.89 tn" in money and "down USD 0.04 tn" in money
    assert w.level_change_phrase("x", {"date": "2026-11-03", "value": 1.0, "change_1m": None}).endswith("2026)")


def test_note_structure_and_consistency() -> None:
    r = findings.load_results()
    note = D.build(r)
    regions = [x["region"] for x in note["overview"]]
    assert regions[:3] == ["United States", "Euro area", "Euro area: France"] and regions[-1] == "Japan"
    assert ("United Kingdom" in regions) == bool(r.get("uk"))
    sev = [x["severity"] for x in note["ranked_risks"]]
    assert sev == sorted(sev, reverse=True)
    assert len(note["risks"]) == sum(s > 0 for s in sev) and len(note["watched"]) == sum(s == 0 for s in sev)
    by_key = {x["key"]: x["severity"] for x in note["ranked_risks"]}
    assert by_key["euro_liquidity"] == D.severity_euro_liquidity(r["runway"]["distance_bn"])
    assert by_key["us_reserves"] == D.severity_us_reserves(r["overview"]["US"]["spread_20d_mean"])
    assert by_key["euro_drift"] == D.severity_drift(r["runway"]["trend"]["main"]["verdict"])
    md = D.markdown(note)
    order = [md.index(h) for h in ("## Recommendation", note["client"]["verdict"] + ".**", "## Funding overview",
                                   "## Year-end: the main risks", "## The year-end forecast", "## Scoring",
                                   "## Disclosures")]
    assert order == sorted(order)
    us = note["overview"][0]["lines"]
    v1 = note["frozen"]["currencies"]["USD"]
    assert any(w.signed_bp(v1["q50"]) in line and "Year-end view" in line for line in us)


def test_overview_missing_gives_empty_sections() -> None:
    r = findings.load_results()
    r = {k: v for k, v in r.items() if k not in ("overview",)}
    note = D.build(r)
    assert note["overview"] == [] and note["client"]["verdict"] in ("Yes", "No", "Partly")
