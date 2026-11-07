"""Recompute every results file from the committed snapshots (no network).

Called by scripts/refresh_snapshots.py after the snapshot is written; can also be run on its own:
    .venv\\Scripts\\python scripts\\run_all.py

    .venv\\Scripts\\python scripts\\run_all.py --out-dir <directory>     (write somewhere else)

Each step is a function in a src/ module that reads the snapshot and writes under results/.
The frozen forecast results/forecasts/yearend_2026.json is never written here.

--out-dir sends every results file to another directory (src/paths.py, POC_RESULTS_DIR); the snapshots are
still read from results/snapshots/. The frozen forecasts are copied there first: read-only inputs that the
desk note and the scores need. scripts/reproduce.py uses it, so tests never modify tracked files.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

STEPS: list[tuple[str, str]] = [  # (module, function); filled in phase by phase
    ("forecast", "run"),
    ("forecast_v2", "run"),
    ("tails", "run"),
    ("corridors", "run"),
    ("collateral", "run"),
    ("france", "run"),
    ("france_daily", "run"),
    ("construction", "run"),
    ("curve", "run"),
    ("japan", "run"),
    ("runway", "run"),
    ("autonomous", "run"),
    ("toolkit", "run"),
    ("holders", "run"),
    ("facilities", "run"),
    ("uk", "run"),
    ("inference", "run"),
    ("robustness", "run"),
    ("overview", "run"),
    ("desk_note", "run"),
]


def main() -> None:
    import importlib

    for module_name, function_name in STEPS:
        print(f"   {module_name}.{function_name}")
        getattr(importlib.import_module(module_name), function_name)()


def prepare_out_dir(out_dir: Path) -> None:
    """Create `out_dir` and copy the frozen forecasts into it (inputs: never rewritten by any step)."""
    frozen = ROOT / "results" / "forecasts"
    (out_dir / "forecasts").mkdir(parents=True, exist_ok=True)
    for name in FROZEN_FILES:
        shutil.copyfile(frozen / name, out_dir / "forecasts" / name)


FROZEN_FILES = ("yearend_2026.json", "yearend_2026_v2.json")


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, help="write the results here instead of results/")
    args = parser.parse_args()
    if args.out_dir is not None:
        # Must be set before any src module is imported: paths.RESULTS is read once at import.
        prepare_out_dir(args.out_dir.resolve())
        os.environ["POC_RESULTS_DIR"] = str(args.out_dir.resolve())
    main()
