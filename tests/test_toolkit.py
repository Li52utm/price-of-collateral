"""D3: the Fed's year-end toolkit (hand-built examples, offline) and its sentences."""

from __future__ import annotations

import pandas as pd

import findings
import toolkit as T
import wording as w


def test_quarter_turns_keeps_complete_quarter_months() -> None:
    days = pd.bdate_range("2025-12-01", "2026-04-02")
    assert list(T.quarter_turns(days, pd.Timestamp("2025-01-01"))) == [pd.Timestamp("2025-12-31"),
                                                                     pd.Timestamp("2026-03-31")]
    assert list(T.quarter_turns(pd.bdate_range("2026-03-02", "2026-03-31"), pd.Timestamp("2025-01-01"))) == []


def test_around_needs_full_windows() -> None:
    days = pd.bdate_range("2026-03-23", "2026-04-07")
    s = pd.Series(range(len(days)), index=days, dtype=float)
    out = T.around(s, pd.Timestamp("2026-03-31"), days, n=5)
    assert out == {"before": 3.0, "at": 6.0, "after": 9.0}
    short = T.around(s, pd.Timestamp("2026-03-24"), days, n=5)
    assert short["before"] is None and short["at"] == 1.0


def test_bills_at_level_and_change() -> None:
    weds = pd.date_range("2026-01-07", periods=20, freq="7D")
    bills = pd.Series(range(100, 120), index=weds, dtype=float)
    level, change = T.bills_at(bills, pd.Timestamp("2026-05-01"), weeks=13)
    assert level == 116.0 and change == 13.0
    assert T.bills_at(bills, pd.Timestamp("2025-01-01")) == (None, None)


def _table() -> pd.DataFrame:
    idx = pd.to_datetime(["2021-12-31", "2022-03-31", "2024-12-31", "2025-12-31"])
    return pd.DataFrame({"repo_before": [0, 0, 1.0, 9.0], "repo_at": [0, 0, 5.0, 75.0], "repo_after": [0, 0, 2.0, 5.0],
                         "spread_at_bp": [-10.0, -11.0, 9.0, 22.0]}, index=idx)


def test_pattern_counts_and_shape() -> None:
    p = T.pattern(_table(), split_year=2023)
    assert (p["n_used"], p["n_used_early"], p["n_used_late"]) == (2, 0, 2)
    assert p["mean_at_used"] == 40.0 and p["max_at_date"] == "2025-12-31"
    s = w.toolkit_pattern_sentence(p)
    assert "more often since 2023" in s and "peaks on the turn itself" in s and "also had a higher" in s


def test_pattern_sentence_unused_and_less_often() -> None:
    t = _table()
    t["repo_at"] = 0.0
    assert "were not used" in w.toolkit_pattern_sentence(T.pattern(t))
    t2 = _table()
    t2["repo_at"] = [5.0, 5.0, 0.0, 0.0]
    t2["repo_before"] = [1.0, 1.0, 0.0, 0.0]
    t2["repo_after"] = [1.0, 1.0, 0.0, 0.0]
    t2["spread_at_bp"] = [20.0, 21.0, 9.0, 1.0]
    s = w.toolkit_pattern_sentence(T.pattern(t2, split_year=2023))
    assert "less often since 2023" in s


def test_backstop_line_flips() -> None:
    s = {"repo_30d_days_used": 0, "repo_bn": 0.0, "repo_date": "2026-11-03", "last_turn": "2026-09-30",
         "last_turn_repo_bn": 1.2, "last_turn_spread_bp": 0.0, "rrp_bn": 0.2, "bills_bn": 572.0,
         "bills_date": "2026-10-28", "bills_13w_change_bn": 57.0}
    assert "was not used" in w.backstop_line(s) and "up USD 57 bn" in w.backstop_line(s)
    assert "was used" in w.backstop_line({**s, "repo_30d_days_used": 3, "bills_13w_change_bn": -5.0})
    assert "down USD 5 bn" in w.backstop_line({**s, "bills_13w_change_bn": -5.0})


def test_toolkit_results_consistent() -> None:
    r = findings.load_results()
    tk = r["toolkit"]
    t = pd.read_csv(findings.RESULTS_DIR / "desk" / "toolkit_turns.csv", index_col=0, parse_dates=True)
    assert tk["pattern"]["n_used"] == int((t["repo_at"].fillna(0) >= 1.0).sum())
    assert tk["pattern"]["n_turns"] == len(t)
    import desk_note
    note = desk_note.build(r)
    assert any(line.startswith("Backstop:") for line in note["funding"])
