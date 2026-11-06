"""D8: the desk-gaps section is complete, general and free of figures."""

from __future__ import annotations

import re

import desk_gaps

REQUIRED = ("specials", "Futures", "LCH RepoClear", "leverage ratio", "Term repo", "Haircut", "Equity financing")


def test_every_requested_item_is_covered_with_why_and_proxy() -> None:
    items = " ".join(g["item"] for g in desk_gaps.GAPS)
    for word in REQUIRED:
        assert word in items, word
    for g in desk_gaps.GAPS:
        assert set(g) == {"item", "why", "proxy"} and len(g["item"]) > 10 and len(g["why"]) > 40 and len(g["proxy"]) > 4


def test_no_figures_in_the_text() -> None:
    text = " ".join(v for g in desk_gaps.GAPS for v in g.values())
    # Words like "G-SIB" or "31 December" are fine; numbers with units (bp, %, bn) are not.
    assert not re.search(r"\d+(\.\d+)?\s*(bp|%|bn|billion|trillion)", text)
