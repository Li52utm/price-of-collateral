"""Create the frozen Year-End 2026 forecast, ONCE.

    .venv\Scripts\python scripts\freeze_forecast.py

Writes results/forecasts/yearend_2026.json with the model version, the data as-of date, the creation
timestamp, the git commit and a SHA-256 of the forecasting code. Refuses to run if the file exists:
the forecast is published before year-end and scored afterwards, so it must never change.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import forecast  # noqa: E402


def main() -> None:
    frozen = forecast.create_frozen_forecast()
    for currency, fc in frozen["currencies"].items():
        print(f"{currency} {fc['turn_day']}: median {fc['q50']:+.1f} bp, 5-95% [{fc['q05']:+.1f}, {fc['q95']:+.1f}] "
              f"({fc['model_label']})")
    print(f"Frozen at {frozen['created_at']}, commit {frozen['git_commit']}, data as of {frozen['data_as_of']}.")


if __name__ == "__main__":
    main()
