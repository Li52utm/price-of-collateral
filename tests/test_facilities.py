"""D6: central-bank repo facility pricing (hand-built examples, offline) and its sentence."""

from __future__ import annotations

import pandas as pd
import pytest

import facilities as Fa
import findings
import validation
import wording as w


def test_row_differences_in_bp() -> None:
    r = Fa.row("X", "floor", 2.0, "backstop", 2.15, "rate", 1.95, "2026-11-03")
    assert r["backstop_minus_floor_bp"] == pytest.approx(15.0) and r["headroom_bp"] == pytest.approx(20.0)


def test_value_on_takes_last_value_on_or_before() -> None:
    long = validation.demo_long({"dfr": pd.Series([2.0, 2.25], index=pd.to_datetime(["2026-01-01", "2026-06-17"]))})
    assert Fa.value_on("dfr", pd.Timestamp("2026-06-16"), long) == (2.0, "2026-01-01")
    assert Fa.value_on("dfr", pd.Timestamp("2026-07-01"), long) == (2.25, "2026-06-17")


def _rows() -> list[dict]:
    return [Fa.row("ECB", "f", 2.0, "b", 2.15, "€STR", 1.95, "d"),
            Fa.row("Fed", "f", 3.9, "b", 4.0, "SOFR", 3.97, "d"),
            Fa.row("BoE", "f", 3.75, "b", 3.75, "SONIA", 3.73, "d"),
            Fa.row("BoJ", "f", 1.0, "b", 1.25, "TONA", 0.98, "d")]


def test_facility_sentence_orders_and_names_least_headroom() -> None:
    s = w.facility_sentence(_rows())
    assert s.startswith("Repo backstop minus floor: BoE +0 bp, Fed +10 bp, ECB +15 bp and BoJ +25 bp")
    assert "the BoE's backstop sits at its floor" in s and "the BoJ's furthest" in s
    assert "SONIA is 2 bp below the BoE's backstop" in s
    rows = _rows()
    rows[1] = Fa.row("Fed", "f", 3.9, "b", 4.0, "SOFR", 4.05, "d")      # SOFR above the SRF rate
    rows[2] = Fa.row("BoE", "f", 3.75, "b", 3.80, "SONIA", 3.73, "d")
    s2 = w.facility_sentence(rows)
    assert "SOFR is 5 bp above the Fed's backstop" in s2 and "sits closest to its floor" in s2


def test_facility_results_consistent() -> None:
    r = findings.load_results()
    rows = r["facilities"]["rows"]
    assert {x["bank"] for x in rows} == {"ECB", "Federal Reserve", "Bank of England", "Bank of Japan"}
    for x in rows:
        assert x["backstop_minus_floor_bp"] == pytest.approx((x["backstop"] - x["floor"]) * 100, abs=1e-6)
    boj = next(x for x in rows if x["bank"] == "Bank of Japan")
    assert boj["backstop_minus_floor_bp"] == pytest.approx(25.0)    # by construction since Aug 2024
    assert findings.facility_line({}) is None and "Repo backstop minus floor" in findings.facility_line(r)
