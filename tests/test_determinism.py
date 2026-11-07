"""U6: rebuilding every results file from the committed snapshots is deterministic within one environment.

scripts/reproduce.py rebuilds TWICE, each time with `scripts/run_all.py --out-dir` into its own temporary
directory, and the two rebuilds must be identical byte for byte. Nothing under results/ is written, so the test
never modifies tracked files (tests/conftest.py checks that for the whole session). Comparing with the committed
files would mix environments: optimisation-based results differ in the last digits between Windows and Linux,
and the committed (canonical) results are the Linux ones made by the GitHub refresh (docs/METHODOLOGY.md,
"Reproducibility"); that comparison is the manual `reproduce.py --against-git`, with a tolerance.
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


def test_two_rebuilds_are_identical_and_frozen_forecasts_untouched(tmp_path: Path) -> None:
    before = [(ROOT / rel).read_bytes() for rel in FROZEN]
    rep = reproduce.check_determinism(work=tmp_path)
    assert rep["different"] == [], rep["different"]
    assert rep["only_in_one"] == [], rep["only_in_one"]
    assert len(rep["identical"]) >= 40
    assert [(ROOT / rel).read_bytes() for rel in FROZEN] == before


@pytest.mark.parametrize("rel", FROZEN)
def test_frozen_forecast_matches_git(rel: str) -> None:
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    assert reproduce._lf((ROOT / rel).read_bytes()) == reproduce._lf(out.stdout)


def test_numeric_comparison_tolerates_rounding_only() -> None:
    assert reproduce.same_content("x.json", b'{"a": 1.0000000000001}', b'{"a": 1.0}')
    assert not reproduce.same_content("x.json", b'{"a": 1.01}', b'{"a": 1.0}')
    assert reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\r\n1.0000000000001,x\r\n")
    assert not reproduce.same_content("x.csv", b"a,b\n1,x\n", b"a,b\n1,y\n")
    assert not reproduce.same_content("x.txt", b"a", b"b")


def test_git_tolerance_is_relative_1e6_absolute_1e9() -> None:
    old, new = b'{"p": 0.3594, "q": [1.0, 2.0], "s": "x"}', b'{"p": 0.35940035, "q": [1.0, 2.0], "s": "x"}'
    diffs = reproduce.numeric_diffs("x.json", old, new)
    assert diffs is not None and reproduce.within(diffs, reproduce.GIT_RTOL, reproduce.GIT_ATOL)
    assert not reproduce.within(reproduce.numeric_diffs("x.json", old, b'{"p": 0.3604, "q": [1.0, 2.0], "s": "x"}'),
                                reproduce.GIT_RTOL, reproduce.GIT_ATOL)
    assert reproduce.numeric_diffs("x.json", old, b'{"p": 0.3594, "q": [1.0, 2.0], "s": "y"}') is None  # text
    assert reproduce.within([(5e-10, 0.0)], reproduce.GIT_RTOL, reproduce.GIT_ATOL)   # absolute floor near zero
