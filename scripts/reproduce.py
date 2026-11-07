"""Rebuild every results file from the committed snapshots and check it, WITHOUT touching tracked files.

    .venv\\Scripts\\python scripts\\reproduce.py                 determinism: two rebuilds must be identical
    .venv\\Scripts\\python scripts\\reproduce.py --against-git   manual check: a rebuild against git HEAD

Every rebuild runs `scripts/run_all.py --out-dir <temporary directory>` in a fresh process: the snapshots are read
from results/snapshots/ and nothing under results/ is written (docs/METHODOLOGY.md, "Reproducibility").

Determinism (default; tests/test_determinism.py): rebuild twice into two temporary directories; every file must
be byte-for-byte identical (line endings normalised). This is the property that holds within one environment.

Against git (manual): rebuild once and compare with the version committed at HEAD. Optimisation-based results
(quantile regression, Markov switching, bootstrap refits) can differ in the last digits across operating systems
and numerical libraries; the CANONICAL results are those the GitHub refresh (Linux) generates and commits. So
numbers are compared with a tolerance, |a - b| <= GIT_ATOL + GIT_RTOL * max(|a|, |b|), and the largest absolute
and relative differences are reported per file, with every file beyond the tolerance listed.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RESULTS = ROOT / "results"
SKIP_PREFIXES = ("snapshots/", "forecasts/")    # inputs and frozen files (relative to a results root)
SKIP_FILES = ("data_validation.json",)          # written by the refresh, not by run_all
RTOL = 1e-9                                      # same_content(): rounding only
GIT_RTOL, GIT_ATOL = 1e-6, 1e-9                  # cross-platform tolerance for --against-git


def _lf(b: bytes) -> bytes:
    """Bytes with Windows line endings normalised to \\n (git may check files out either way)."""
    return b.replace(b"\r\n", b"\n")


def committed(rel: str) -> bytes | None:
    """The file's bytes at HEAD (`rel` relative to the project), or None if it is not tracked."""
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
    return out.stdout if out.returncode == 0 else None


# --------------------------------------------------------------------------- #
# Numeric comparison
# --------------------------------------------------------------------------- #
def _walk(a, b, diffs: list[tuple[float, float]]) -> bool:
    """Collect (|a-b|, max(|a|,|b|)) for every pair of numbers; False if the structure or any text differs."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_walk(a[k], b[k], diffs) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_walk(x, y, diffs) for x, y in zip(a, b, strict=True))
    numbers = (int, float)
    if isinstance(a, numbers) and isinstance(b, numbers) and not isinstance(a, bool) and not isinstance(b, bool):
        if np.isnan(a) and np.isnan(b):
            return True
        diffs.append((abs(float(a) - float(b)), max(abs(float(a)), abs(float(b)))))
        return True
    return a == b


def numeric_diffs(rel: str, old: bytes, new: bytes) -> list[tuple[float, float]] | None:
    """Every number pair's (absolute difference, scale) in a JSON or CSV file; None if anything but numbers differs."""
    diffs: list[tuple[float, float]] = []
    try:
        if rel.endswith(".json"):
            return diffs if _walk(json.loads(old), json.loads(new), diffs) else None
        if rel.endswith(".csv"):
            a, b = pd.read_csv(io.BytesIO(old)), pd.read_csv(io.BytesIO(new))
            if list(a.columns) != list(b.columns) or a.shape != b.shape:
                return None
            for c in a.columns:
                if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
                    x, y = a[c].to_numpy(dtype=float), b[c].to_numpy(dtype=float)
                    if not np.array_equal(np.isnan(x), np.isnan(y)):
                        return None
                    keep = ~np.isnan(x)
                    diffs += list(zip(np.abs(x - y)[keep], np.maximum(np.abs(x), np.abs(y))[keep], strict=True))
                elif not a[c].astype(str).equals(b[c].astype(str)):
                    return None
            return diffs
    except Exception:
        return None
    return None


def within(diffs: list[tuple[float, float]], rtol: float, atol: float) -> bool:
    """Every number pair satisfies |a - b| <= atol + rtol * max(|a|, |b|)."""
    return all(d <= atol + rtol * s for d, s in diffs)


def same_content(rel: str, old: bytes, new: bytes, rtol: float = RTOL, atol: float = 1e-12) -> bool:
    """Byte equality (line endings normalised), else every number within the tolerance for JSON and CSV."""
    if _lf(old) == _lf(new):
        return True
    diffs = numeric_diffs(rel, old, new)
    return diffs is not None and within(diffs, rtol, atol)


# --------------------------------------------------------------------------- #
# Rebuilds
# --------------------------------------------------------------------------- #
def results_files(root: Path) -> list[str]:
    """Every compared results file under a results root (POSIX, relative to that root)."""
    out = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not rel.startswith(SKIP_PREFIXES) and rel not in SKIP_FILES:
            out.append(rel)
    return out


def rebuild_into(out_dir: Path) -> Path:
    """Run scripts/run_all.py --out-dir in a fresh process (module paths are read at import). Raises on failure."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_all.py"), "--out-dir", str(out_dir)],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"run_all failed:\n{out.stdout[-2000:]}\n{out.stderr[-4000:]}")
    return out_dir


def compare_dirs(a: Path, b: Path) -> dict:
    """Byte comparison of two rebuilds: identical, different, and files present in only one of them."""
    fa, fb = set(results_files(a)), set(results_files(b))
    rep = {"identical": [], "different": [], "only_in_one": sorted(fa ^ fb)}
    for rel in sorted(fa & fb):
        same = _lf((a / rel).read_bytes()) == _lf((b / rel).read_bytes())
        rep["identical" if same else "different"].append(rel)
    return rep


def check_determinism(work: Path | None = None) -> dict:
    """Rebuild twice into two temporary directories and compare the two rebuilds byte for byte."""
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        first, second = rebuild_into(Path(tmp) / "first"), rebuild_into(Path(tmp) / "second")
        return compare_dirs(first, second)


def check_against_git(rtol: float = GIT_RTOL, atol: float = GIT_ATOL, work: Path | None = None) -> dict:
    """Rebuild into a temporary directory and compare each file with git HEAD at the cross-platform tolerance.

    Per file: identical bytes, within the tolerance (with the largest absolute and relative difference), beyond it,
    or text that differs (a generated sentence quoting a number can move in its last printed digit)."""
    rep = {"rtol": rtol, "atol": atol, "identical": [], "within": {}, "beyond": {}, "text_differs": [],
           "untracked": [], "max_abs": 0.0, "max_rel": 0.0}
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        out = rebuild_into(Path(tmp) / "rebuild")
        for rel in results_files(out):
            old, new = committed(f"results/{rel}"), (out / rel).read_bytes()
            if old is None:
                rep["untracked"].append(rel)
            elif _lf(old) == _lf(new):
                rep["identical"].append(rel)
            else:
                diffs = numeric_diffs(rel, old, new)
                if diffs is None:
                    rep["text_differs"].append(rel)
                    continue
                big_abs = max((d for d, _ in diffs), default=0.0)
                big_rel = max((d / s for d, s in diffs if s > 0), default=0.0)
                rep["max_abs"], rep["max_rel"] = max(rep["max_abs"], big_abs), max(rep["max_rel"], big_rel)
                key = "within" if within(diffs, rtol, atol) else "beyond"
                rep[key][rel] = {"max_abs": big_abs, "max_rel": big_rel,
                                 "n_beyond": sum(d > atol + rtol * s for d, s in diffs)}
    return rep


def main(against_git: bool = False) -> None:
    if not against_git:
        rep = check_determinism()
        print(f"two rebuilds: identical {len(rep['identical'])}; different {len(rep['different'])}; "
              f"in only one {len(rep['only_in_one'])}")
        for rel in rep["different"] + rep["only_in_one"]:
            print(f"   DIFFERENT {rel}")
        sys.exit(1 if rep["different"] or rep["only_in_one"] else 0)
    rep = check_against_git()
    print(f"against git HEAD (tolerance relative {rep['rtol']:g}, absolute {rep['atol']:g}): identical "
          f"{len(rep['identical'])}; within tolerance {len(rep['within'])}; beyond {len(rep['beyond'])}; "
          f"text differs {len(rep['text_differs'])}; untracked {len(rep['untracked'])}")
    print(f"largest difference: absolute {rep['max_abs']:.3g}, relative {rep['max_rel']:.3g}")
    for rel, d in {**rep["within"], **rep["beyond"]}.items():
        flag = "BEYOND" if rel in rep["beyond"] else "within"
        print(f"   {flag:6s} {rel}: max abs {d['max_abs']:.3g}, max rel {d['max_rel']:.3g}, "
              f"{d['n_beyond']} numbers beyond the tolerance")
    for rel in rep["text_differs"]:
        print(f"   TEXT   {rel}")
    sys.exit(1 if rep["beyond"] or rep["text_differs"] else 0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--against-git", action="store_true", help="compare a rebuild with git HEAD (tolerance)")
    main(parser.parse_args().against_git)
