"""U6: rebuilding every results file from the snapshots on disk is deterministic.

Runs scripts/reproduce.py's check() in-process (about a minute): results files are read, rebuilt from the
snapshots on disk with scripts/run_all.py, and compared with what was there before (rebuilding twice gives
identical output). This holds after a data refresh too, unlike a comparison with git HEAD, which would fail on
every refresh that brings new data (`reproduce.py --against-git` keeps that check for manual use).
The frozen forecasts are never written by the rebuild: they must be byte-for-byte unchanged by it AND identical
to the committed version.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import reproduce  # noqa: E402

FROZEN = ("results/forecasts/yearend_2026.json", "results/forecasts/yearend_2026_v2.json")


def test_rebuild_is_deterministic_and_frozen_forecasts_untouched() -> None:
    before = [(ROOT / rel).read_bytes() for rel in FROZEN]
    rep = reproduce.check(rebuild=True, against="disk")
    assert rep["different"] == [], rep["different"]
    assert rep["untracked"] == [] and rep["missing_after_rebuild"] == []
    assert len(rep["identical"]) + len(rep["numerically_equal"]) >= 40
    assert [(ROOT / rel).read_bytes() for rel in FROZEN] == before


@pytest.mark.parametrize("rel", FROZEN)
def test_frozen_forecast_matches_git(rel: str) -> None:
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    assert reproduce._lf((ROOT / rel).read_bytes()) == reproduce._lf(out.stdout)


def test_check_rejects_an_unknown_reference() -> None:
    with pytest.raises(ValueError):
        reproduce.check(rebuild=False, against="yesterday")


def test_numeric_comparison_tolerates_rounding_only() -> None:
    assert reproduce.same_content("x.json", b'{"a": 1.0000000000001}', b'{"a": 1.0}')
    assert not reproduce.same_content("x.json", b'{"a": 1.01}', b'{"a": 1.0}')
    assert reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\r\n1.0000000000001,x\r\n")
    assert not reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\n1,y\n")
    assert not reproduce.same_content("x.txt", b"a", b"b")
