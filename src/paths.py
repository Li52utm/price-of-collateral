"""Where results are read and written: one place, so a rebuild can be sent to another directory.

    RESULTS       the results root: results/ in the project, or the directory in the environment variable
                  POC_RESULTS_DIR (set by `scripts/run_all.py --out-dir`). Tests rebuild into temporary
                  directories this way, so they never modify tracked files (tests/test_determinism.py).
    SNAPSHOT_DIR  the committed data snapshots: ALWAYS results/snapshots/ in the project. They are inputs, so a
                  rebuild into another directory still reads the committed data.

Read once at import: to rebuild elsewhere, set POC_RESULTS_DIR before the first import (run_all does this in a
fresh process).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_ENV = "POC_RESULTS_DIR"
RESULTS = Path(os.environ[RESULTS_ENV]).resolve() if os.environ.get(RESULTS_ENV) else ROOT / "results"
SNAPSHOT_DIR = ROOT / "results" / "snapshots"
