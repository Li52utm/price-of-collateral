"""Recompute every results file from the committed snapshots (no network).

Called by scripts/refresh_snapshots.py after the snapshot is written; can also be run on its own:
    .venv\\Scripts\\python scripts\\run_all.py

Each step is a function in a src/ module that reads the snapshot and writes under results/.
The frozen forecast results/forecasts/yearend_2026.json is never written here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

STEPS: list[tuple[str, str]] = [  # (module, function); filled in phase by phase
    ("forecast", "run"),
    ("tails", "run"),
    ("corridors", "run"),
    ("collateral", "run"),
    ("france", "run"),
    ("france_daily", "run"),
    ("japan", "run"),
    ("inference", "run"),
]


def main() -> None:
    import importlib

    for module_name, function_name in STEPS:
        print(f"   {module_name}.{function_name}")
        getattr(importlib.import_module(module_name), function_name)()


if __name__ == "__main__":
    main()
