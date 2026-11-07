"""Rebuild every results file from the snapshots and check the rebuild is deterministic.

    .venv\\Scripts\\python scripts\\reproduce.py                 (default: against the files on disk)
    .venv\\Scripts\\python scripts\\reproduce.py --against-git   (manual check: against git HEAD)

Default mode (`against="disk"`): read every results file, run scripts/run_all.py (no network) on the snapshots
on disk, and compare each rebuilt file with what was there before, i.e. rebuilding twice gives the same output.
This holds after every data refresh, because the results on disk were built from the snapshots on disk.

Git mode (`against="git"`): compare with the version committed at HEAD. Use it by hand on a clean checkout to
confirm the committed results match the committed snapshots; after a refresh that brings new data, the
results legitimately differ from HEAD until they are committed.

Skipped: the snapshots (inputs) and the frozen forecasts (never rewritten; the test checks them byte for byte).
Comparison: byte for byte first (line endings normalised), then numerically for CSV and JSON (relative tolerance
1e-9). Exit code 1 if any file differs. tests/test_determinism.py calls `check()`.
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


def _lf(b: bytes) -> bytes:
    """Bytes with Windows line endings normalised to \\n (git may check files out either way)."""
    return b.replace(b"\r\n", b"\n")


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
    if _lf(old) == _lf(new):
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


def results_files() -> list[str]:
    """Every compared results file (repo-relative, POSIX), excluding inputs, frozen files and the validation report."""
    out = []
    for path in sorted(RESULTS.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file() and not rel.startswith(SKIP_PREFIXES) and rel != "results/data_validation.json":
            out.append(rel)
    return out


def check(rebuild: bool = True, against: str = "disk") -> dict:
    """Rebuild (optional) and compare every results file with the reference: the files on disk before the
    rebuild (`against="disk"`, real determinism) or the version at git HEAD (`against="git"`). Returns a report."""
    if against not in ("disk", "git"):
        raise ValueError(f"against must be 'disk' or 'git', got {against!r}")
    before = {rel: (ROOT / rel).read_bytes() for rel in results_files()} if against == "disk" else {}
    if rebuild:
        import run_all
        run_all.main()
    report = {"against": against, "identical": [], "numerically_equal": [], "different": [], "untracked": []}
    for rel in results_files():
        old = before.get(rel) if against == "disk" else committed(rel)
        new = (ROOT / rel).read_bytes()
        if old is None:
            report["untracked"].append(rel)   # new file: not in the reference
        elif _lf(old) == _lf(new):
            report["identical"].append(rel)
        elif same_content(rel, old, new):
            report["numerically_equal"].append(rel)
        else:
            report["different"].append(rel)
    if against == "disk":
        report["missing_after_rebuild"] = sorted(set(before) - set(results_files()))
    return report


def main(against: str = "disk") -> None:
    rep = check(against=against)
    print(f"against {against}: identical: {len(rep['identical'])}; numerically equal: "
          f"{len(rep['numerically_equal'])}; different: {len(rep['different'])}; untracked: {len(rep['untracked'])}")
    for rel in rep["different"]:
        print(f"   DIFFERENT {rel}")
    sys.exit(1 if rep["different"] or rep.get("missing_after_rebuild") else 0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--against-git", action="store_true", help="compare with git HEAD instead of the files on disk")
    main("git" if parser.parse_args().against_git else "disk")
