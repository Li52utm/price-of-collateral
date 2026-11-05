"""U6: every results file is rebuilt from the committed snapshots and matches the committed version.

Runs scripts/reproduce.py's check() in-process (about a minute). The frozen forecasts and the snapshots
are never written by the rebuild; the test also confirms both frozen files are byte-for-byte unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import reproduce  # noqa: E402


def test_rebuild_matches_committed_results() -> None:
    frozen = [ROOT / "results" / "forecasts" / n for n in ("yearend_2026.json", "yearend_2026_v2.json")]
    before = [p.read_bytes() for p in frozen]
    rep = reproduce.check(rebuild=True)
    assert rep["different"] == [], rep["different"]
    assert len(rep["identical"]) + len(rep["numerically_equal"]) >= 40
    assert [p.read_bytes() for p in frozen] == before


def test_numeric_comparison_tolerates_rounding_only() -> None:
    assert reproduce.same_content("x.json", b'{"a": 1.0000000000001}', b'{"a": 1.0}')
    assert not reproduce.same_content("x.json", b'{"a": 1.01}', b'{"a": 1.0}')
    assert reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\r\n1.0000000000001,x\r\n")
    assert not reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\n1,y\n")
    assert not reproduce.same_content("x.txt", b"a", b"b")
