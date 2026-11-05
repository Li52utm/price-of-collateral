"""Create a frozen Year-End 2026 forecast, ONCE per version.

    .venv\\Scripts\\python scripts\\freeze_forecast.py               (v1, the pre-registered headline; done 4 Nov 2026)
    .venv\\Scripts\\python scripts\\freeze_forecast.py --version v2  (the challenger, U4)

Writes results/forecasts/yearend_2026.json (v1) or yearend_2026_v2.json (v2) with the model version, the
data as-of date, the creation timestamp, the git commit and a SHA-256 of the forecasting code. Refuses to
run if the file exists: a forecast is published before year-end and scored afterwards, so it never changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import forecast  # noqa: E402
import forecast_v2  # noqa: E402


def main(version: str = "v1") -> None:
    """Freeze `version` (raises FileExistsError if that frozen file already exists)."""
    frozen = forecast.create_frozen_forecast() if version == "v1" else forecast_v2.create_frozen_v2()
    for currency, fc in frozen["currencies"].items():
        print(f"{currency} {fc['turn_day']}: median {fc['q50']:+.1f} bp, 5-95% [{fc['q05']:+.1f}, {fc['q95']:+.1f}] "
              f"({fc['model_label']})")
    print(f"Frozen at {frozen['created_at']}, commit {frozen['git_commit']}, data as of {frozen['data_as_of']}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", choices=("v1", "v2"), default="v1")
    main(parser.parse_args().version)
