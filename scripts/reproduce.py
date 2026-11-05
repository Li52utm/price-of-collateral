"""Rebuild every results file from the committed snapshots and check it matches the committed version.

    .venv\\Scripts\\python scripts\\reproduce.py

Runs scripts/run_all.py (no network) and compares each file under results/ (except the snapshots, which
are inputs, and the frozen forecasts, which are never rewritten) with the version committed in git:
byte for byte first, then, if the bytes differ, numerically (CSV and JSON numbers within a relative
tolerance of 1e-9). Exit code 1 if any file differs. tests/test_determinism.py calls `check()`.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RESULTS = ROOT / "results"
SKIP_PREFIXES = ("results/snapshots/", "results/forecasts/")   # inputs and frozen files
RTOL = 1e-9


def committed(rel: str) -> bytes | None:
    """The file's bytes at HEAD, or None if it is not tracked."""
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
    return out.stdout if out.returncode == 0 else None


def _numbers_equal(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_numbers_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_numbers_equal(x, y) for x, y in zip(a, b, strict=False))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return bool(np.isclose(a, b, rtol=RTOL, atol=1e-12, equal_nan=True))
    return a == b


def same_content(rel: str, old: bytes, new: bytes) -> bool:
    """Byte equality (line endings normalised), else numeric equality for JSON and CSV."""
    if old.replace(b"\r\n", b"\n") == new.replace(b"\r\n", b"\n"):
        return True
    try:
        if rel.endswith(".json"):
            return _numbers_equal(json.loads(old), json.loads(new))
        if rel.endswith(".csv"):
            a, b = pd.read_csv(io.BytesIO(old)), pd.read_csv(io.BytesIO(new))
            if list(a.columns) != list(b.columns) or a.shape != b.shape:
                return False
            for c in a.columns:
                if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
                    if not np.allclose(a[c], b[c], rtol=RTOL, atol=1e-12, equal_nan=True):
                        return False
                elif not a[c].astype(str).equals(b[c].astype(str)):
                    return False
            return True
    except Exception:
        return False
    return False


def check(rebuild: bool = True) -> dict:
    """Rebuild (optional) and compare every tracked results file with HEAD. Returns a report."""
    if rebuild:
        import run_all
        run_all.main()
    report = {"identical": [], "numerically_equal": [], "different": [], "untracked": []}
    for path in sorted(RESULTS.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIP_PREFIXES) or rel == "results/data_validation.json":
            continue
        old = committed(rel)
        new = path.read_bytes()
        if old is None:
            report["untracked"].append(rel)
        elif old.replace(b"\r\n", b"\n") == new.replace(b"\r\n", b"\n"):
            report["identical"].append(rel)
        elif same_content(rel, old, new):
            report["numerically_equal"].append(rel)
        else:
            report["different"].append(rel)
    return report


def main() -> None:
    rep = check()
    print(f"identical: {len(rep['identical'])}; numerically equal: {len(rep['numerically_equal'])}; "
          f"different: {len(rep['different'])}; untracked: {len(rep['untracked'])}")
    for rel in rep["different"]:
        print(f"   DIFFERENT {rel}")
    sys.exit(1 if rep["different"] else 0)


if __name__ == "__main__":
    main()
