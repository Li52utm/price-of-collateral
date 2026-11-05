"""Refresh every committed snapshot and result file (the scheduled data pipeline).

Run from the project root:
    .venv\\Scripts\\python scripts\\refresh_snapshots.py      (Windows)
    .venv/bin/python scripts/refresh_snapshots.py           (macOS / Linux)

Steps:
    1. Download every series (src/download.py). If any download fails, stop: nothing is written.
    2. Pipeline checks (src/pipeline.py): no series empty, shorter than, or ending before the
       committed snapshot; €STR and SOFR recent. Any failure stops the refresh.
    3. Validation (src/validation.py) on the fresh download. Any FAIL stops the refresh.
    4. Write results/snapshots/ and the validation reports.
    5. Recompute every results file from the new snapshot (scripts/run_all.py). This NEVER
       touches the frozen forecast results/forecasts/yearend_2026.json; it only writes the score
       file once the year-end values exist.
    6. Regenerate the README auto-block (scripts/update_readme.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

import data  # noqa: E402
import download  # noqa: E402
import pipeline  # noqa: E402
import validation  # noqa: E402

REQUIRED_RECENT = {"estr": 7, "sofr": 7}  # calendar days the latest value may lag the fetch date
VALIDATION_JSON = ROOT / "results" / "data_validation.json"
VALIDATION_MD = ROOT / "docs" / "DATA_VALIDATION.md"


def check_download(new: pd.DataFrame, previous: pd.DataFrame | None, fetched: pd.Timestamp) -> None:
    """Pipeline checks on the fresh long frame (raises pipeline.DataCheckError)."""
    names = sorted(new["series"].unique())
    if previous is not None:
        missing = sorted(set(previous["series"]) - set(names))
        if missing:
            raise pipeline.DataCheckError(f"series missing from the download: {missing}")
    for name in names:
        s = data.raw(name, new)
        old = data.raw(name, previous) if previous is not None else None
        pipeline.check_growth(name, s, old if old is not None and len(old) else None)
    for name, days in REQUIRED_RECENT.items():
        pipeline.check_recent(name, data.raw(name, new), fetched.normalize(), days)


def add_new_series(previous: pd.DataFrame) -> None:
    """Download only registered series missing from the snapshot, capped at what was published by the
    snapshot's fetch date (observation date + lag <= fetch date), validate the merged frame, write it."""
    import sources
    manifest = data.load_manifest()
    fetched = pd.Timestamp(manifest["fetched_at"])
    new_names = [s.name for s in sources.ALL_SERIES if s.name not in set(previous["series"])]
    if not new_names:
        print("No new series to add.")
        return
    print(f"1. Downloading new series only: {new_names}")
    new = download.download_new(new_names)
    keep = []
    for name, part in new.groupby("series"):
        avail = data.available_dates(pd.DatetimeIndex(part["date"]), sources.lag(name), data.currency_of(name))
        keep.append(part[avail <= fetched.normalize()])
    long = pd.concat([previous, *keep], ignore_index=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long.sort_values(["series", "date"]).reset_index(drop=True)
    print("2-3. Pipeline checks and validation on the merged snapshot ...")
    for name in new_names:
        pipeline.check_growth(name, data.raw(name, long), None)
    rep = validation.run_all(long, fetched)
    for c in rep["checks"]:
        print(f"   {c['status']:4s} {c['name']}")
    if rep["counts"][validation.FAIL]:
        raise validation.ValidationFailed("validation FAIL: nothing written")
    print("4. Writing snapshots and validation reports ...")
    data.write_snapshot(long, data.load_settlements(), manifest["fetched_at"])
    validation.write_reports(rep, VALIDATION_JSON, VALIDATION_MD)


def main(skip_download: bool = False, add_new: bool = False) -> None:
    fetched = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("s")
    previous = data.load_long() if data.SERIES_PATH.exists() else None
    if add_new:
        add_new_series(previous)
    elif skip_download:  # re-run steps 4-6 on the committed snapshot (no network)
        print("1-3. Skipping download: using the committed snapshot")
        long, settlements = previous, data.load_settlements()
    else:
        print("1. Downloading ...")
        fresh = download.download_all()
        long, settlements = fresh["series"], fresh["settlements"]
        print("2. Pipeline checks ...")
        check_download(long, previous, fetched)
        print("3. Validation ...")
        rep = validation.run_all(long, fetched)
        for c in rep["checks"]:
            print(f"   {c['status']:4s} {c['name']}")
        if rep["counts"][validation.FAIL]:
            raise validation.ValidationFailed("validation FAIL: nothing written")
        print("4. Writing snapshots and validation reports ...")
        data.write_snapshot(long, settlements, str(fetched))
        validation.write_reports(rep, VALIDATION_JSON, VALIDATION_MD)
    print("5. Recomputing results ...")
    import run_all
    run_all.main()
    print("6. README auto-block ...")
    import update_readme
    update_readme.main()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-download", action="store_true", help="recompute results from the committed snapshot")
    parser.add_argument("--add-new-series", action="store_true",
                        help="download only registered series missing from the snapshot and merge them in")
    args = parser.parse_args()
    main(args.skip_download, args.add_new_series)
