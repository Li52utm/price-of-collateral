"""D6: central-bank repo facility pricing (hand-built examples, offline) and its sentence."""

from __future__ import annotations

import pandas as pd
import pytest

import data
import facilities as Fa
import findings
import validation
import wording as w


def test_row_differences_in_bp() -> None:
    r = Fa.row("X", "floor", 2.0, "backstop", 2.15, "rate", 1.95, "2026-11-03")
    assert r["backstop_minus_floor_bp"] == pytest.approx(15.0) and r["headroom_bp"] == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# Date alignment (corrected 2026-11-07): Bank Rate rose to 4.00% on Thu 5 Nov 2026, SONIA published only to
# Wed 4 Nov. The old table read Bank Rate on 5 Nov against SONIA of 4 Nov: "+26.6 bp headroom".
# --------------------------------------------------------------------------- #
BOE = next(s for s in Fa.BANKS if s["bank"] == "Bank of England")


def _boe_long() -> pd.DataFrame:
    days = pd.bdate_range("2026-10-26", "2026-11-05")
    bank_rate = pd.Series(3.75, index=days)
    bank_rate[pd.Timestamp("2026-11-05")] = 4.00                  # policy change on day t
    sonia = pd.Series(3.7335, index=days[days <= "2026-11-04"])  # market rate published only to t-1
    return validation.demo_long({"bank_rate": bank_rate, "sonia": sonia})


def test_policy_change_on_t_with_market_rate_to_t_minus_1_compares_on_t_minus_1() -> None:
    r = Fa.bank_row(BOE, _boe_long())
    assert r["date"] == "2026-11-04"
    assert r["floor"] == 3.75 and r["backstop"] == 3.75 and r["market"] == 3.7335
    assert r["headroom_bp"] == pytest.approx(1.65)                # not the false +26.65 bp
    assert r["later_changes"] == [{"series": "bank_rate", "name": "Bank Rate (reserves remuneration)",
                                   "previous": 3.75, "value": 4.0, "from": "2026-11-05"}]
    note = w.facility_change_note(r)
    assert note == ("For the Bank of England, Bank Rate (reserves remuneration) rose to 4.00% from 5 November 2026; "
                    "SONIA for that day is not yet published, so the row compares both on 4 November 2026.")


def test_once_the_market_rate_catches_up_the_row_moves_to_t() -> None:
    long = pd.concat([_boe_long(), validation.demo_long({"sonia": pd.Series(3.98, index=[
        pd.Timestamp("2026-11-05")])})], ignore_index=True)
    r = Fa.bank_row(BOE, long)
    assert r["date"] == "2026-11-05" and r["floor"] == 4.0 and r["later_changes"] == []
    assert r["headroom_bp"] == pytest.approx(2.0) and w.facility_change_note(r) == ""


def test_latest_common_date_needs_every_series() -> None:
    long = _boe_long()
    assert data.latest_common_date(["bank_rate"], long) == pd.Timestamp("2026-11-05")
    assert data.latest_common_date(["bank_rate", "sonia"], long) == pd.Timestamp("2026-11-04")
    with pytest.raises(ValueError):
        data.latest_common_date(["bank_rate", "sonia"], long[long["series"] == "bank_rate"])


def test_a_policy_cut_is_worded_as_a_fall() -> None:
    r = Fa.row("Bank of England", "Bank Rate", 4.0, "STR", 4.0, "SONIA", 3.98, "2026-11-04",
               later=[{"series": "bank_rate", "name": "Bank Rate", "previous": 4.0, "value": 3.75,
                       "from": "2026-11-05"}])
    assert "Bank Rate fell to 3.75% from 5 November 2026" in w.facility_change_note(r)


def test_srf_headroom_sentence_flips_with_the_sign() -> None:
    below = Fa.row("Federal Reserve", "f", 3.9, "b", 4.0, "SOFR", 3.92, "2026-11-05")
    above = Fa.row("Federal Reserve", "f", 3.9, "b", 4.0, "SOFR", 4.05, "2026-11-05")
    assert w.srf_headroom_sentence(below) == ("SOFR is 8 bp below the standing repo facility rate (4.00%) on "
                                              "5 November 2026.")
    assert w.srf_headroom_sentence(above).startswith("SOFR is 5 bp above")


def _rows() -> list[dict]:
    return [Fa.row("ECB", "f", 2.0, "b", 2.15, "€STR", 1.95, "2026-11-04"),
            Fa.row("Fed", "f", 3.9, "b", 4.0, "SOFR", 3.97, "2026-11-04"),
            Fa.row("BoE", "f", 3.75, "b", 3.75, "SONIA", 3.73, "2026-11-04"),
            Fa.row("BoJ", "f", 1.0, "b", 1.25, "TONA", 0.98, "2026-11-04")]


def test_facility_sentence_orders_and_names_least_headroom() -> None:
    s = w.facility_sentence(_rows())
    assert s.startswith("Repo backstop minus floor: BoE +0 bp, Fed +10 bp, ECB +15 bp and BoJ +25 bp")
    assert "the BoE's backstop sits at its floor" in s and "the BoJ's furthest" in s
    assert "SONIA is 2 bp below the BoE's backstop" in s
    rows = _rows()
    rows[1] = Fa.row("Fed", "f", 3.9, "b", 4.0, "SOFR", 4.05, "2026-11-04")      # SOFR above the SRF rate
    rows[2] = Fa.row("BoE", "f", 3.75, "b", 3.80, "SONIA", 3.73, "2026-11-04")
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
    for x in rows:   # every rate in a row is read on one date, on which every series of the row is published
        assert x["headroom_bp"] == pytest.approx((x["backstop"] - x["market"]) * 100, abs=1e-6)
        assert x["date"] <= r["facilities"]["data_as_of"]
