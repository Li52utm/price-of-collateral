"""Phase 0 framework: network guard, README auto-block, pipeline checks, wording basics, theme."""

from __future__ import annotations

import pandas as pd
import pytest
import requests

import pipeline
import ui
import wording
from conftest import NetworkBlocked
from readme_block import END, START, current_block, render_block, replace_auto_block


def test_network_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        requests.get("https://data-api.ecb.europa.eu")


def test_replace_auto_block_only_touches_the_block() -> None:
    text = f"head\n{START}\nold\n{END}\ntail"
    out = replace_auto_block(text, "new")
    assert out == f"head\n{START}\nnew\n{END}\ntail"
    assert current_block(out) == "new"
    with pytest.raises(ValueError):
        replace_auto_block("no markers", "x")
    with pytest.raises(ValueError):
        replace_auto_block(f"{END} {START}", "x")


def test_render_block_lists_findings_and_tests() -> None:
    block = render_block({"as_of": "3 November 2026", "findings": ["A.", "B."], "n_tests": 12})
    assert "- A.\n- B." in block and "**12**" in block and "3 November 2026" in block


def test_pipeline_checks() -> None:
    idx = pd.date_range("2026-01-01", periods=5)
    new = pd.DataFrame({"a": range(5)}, index=idx)
    pipeline.check_growth("x", new, new.iloc[:3])
    with pytest.raises(pipeline.DataCheckError):
        pipeline.check_growth("x", new.iloc[:2], new)
    with pytest.raises(pipeline.DataCheckError):
        pipeline.check_growth("x", new.iloc[0:0], None)
    with pytest.raises(pipeline.DataCheckError):
        pipeline.check_columns("x", new, ["a", "b"])
    pipeline.check_recent("x", new["a"], idx[-1] + pd.Timedelta(days=3), 5)
    with pytest.raises(pipeline.DataCheckError):
        pipeline.check_recent("x", new["a"], idx[-1] + pd.Timedelta(days=30), 5)


def test_wording_building_blocks_flip() -> None:
    assert wording.wider_or_narrower(2) == "wider" and wording.wider_or_narrower(-2) == "narrower"
    assert wording.above_or_below(1) == "above" and wording.above_or_below(-1) == "below"
    assert wording.rose_or_fell(-0.1) == "fell"
    assert wording.share_words(0, 5) == "none of 5" and wording.share_words(5, 5) == "all 5"
    assert wording.share_words(2, 5) == "2 of 5"
    assert "not statistically" in wording.significance_phrase(0.3)
    assert wording.significance_phrase(0.0001) == "statistically significant (p < 0.001)"


def test_palette_is_distinct() -> None:
    main = [*ui.CURRENCY_COLORS.values(), *(ui.COUNTRY_COLORS[c] for c in ("DE", "FR", "IT", "ES"))]
    assert len(set(main)) == len(main)
    assert ui.hex_to_rgba("#0072B2", 0.2) == "rgba(0, 114, 178, 0.2)"


def test_staleness_rule() -> None:
    today = pd.Timestamp("2026-11-10")
    assert not ui.is_stale(pd.Timestamp("2026-11-05"), today)
    assert ui.is_stale(pd.Timestamp("2026-10-01"), today)
    assert ui.is_stale(None, today)
