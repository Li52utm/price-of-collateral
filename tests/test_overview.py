"""D9: the overview numbers (hand-built examples) and the README desk lines."""

from __future__ import annotations

import pandas as pd
import pytest

import findings
import overview as O


def test_level_and_change_uses_one_calendar_month() -> None:
    s = pd.Series([1.0, 2.0, 5.0], index=pd.to_datetime(["2026-09-30", "2026-10-02", "2026-11-03"]))
    out = O.level_and_change(s)
    assert out == {"date": "2026-11-03", "value": 5.0, "change_1m": 3.0, "prior_date": "2026-10-02"}
    scaled = O.level_and_change(s, 100.0)
    assert scaled["value"] == 500.0 and scaled["change_1m"] == pytest.approx(300.0)
    short = O.level_and_change(pd.Series([1.0], index=pd.to_datetime(["2026-11-03"])))
    assert short["change_1m"] is None and short["prior_date"] is None


def test_overview_results_consistent() -> None:
    r = findings.load_results()
    ov = r["overview"]
    assert set(ov) >= {"US", "EUR", "FR", "UK", "JP"}
    assert ov["FR"]["spread"]["value"] == pytest.approx(r["france_daily"]["rules"]["now"]["spread"], abs=1e-6)
    for cur, key, scale in (("USD", ("US", "reserves_tn"), 1.0), ("EUR", ("EUR", "liquidity_bn"), 1e-3)):
        res = r["corridors"]["reserves"][cur]   # chapter II's "latest" is the same latest published value
        assert ov[key[0]][key[1]]["value"] * scale == pytest.approx(res["latest_liq"], abs=1e-6)
        assert ov[key[0]][key[1]]["date"] == res["latest_date"]
        assert res["last_pair_date"] <= res["latest_date"]   # the regression's last week, kept separately
    assert r["runway"]["latest_date"] == ov["EUR"]["liquidity_bn"]["date"]


def test_readme_desk_findings() -> None:
    r = findings.load_results()
    lines = findings.desk_findings(r)
    assert lines[0].startswith("**Euro runway.**") and any(x.startswith("**Repo backstops.**") for x in lines)
    assert findings.desk_findings({}) == []
