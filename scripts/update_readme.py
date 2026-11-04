"""Regenerate the README's auto-block (key findings, as-of date, test count).

Run from the project root (refresh_snapshots.py calls it after every refresh):
    .venv\\Scripts\\python scripts\\update_readme.py

Every finding is a sentence built by src/wording.py from the results files (src/findings.py
collects them), so the block always follows the numbers. Only the text between
<!-- AUTO:START --> and <!-- AUTO:END --> in README.md is rewritten.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import data  # noqa: E402
from readme_block import render_block, replace_auto_block  # noqa: E402

README = ROOT / "README.md"


def count_tests() -> int:
    """Number of tests pytest collects (collection is offline)."""
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    match = re.search(r"(\d+) tests? collected", out)
    if not match:
        raise RuntimeError(f"could not read the test count from pytest:\n{out[-500:]}")
    return int(match.group(1))


def collect_findings() -> list[str]:
    try:
        import findings
    except ImportError:
        return []
    return findings.readme_findings()


def main() -> None:
    as_of = data.as_of()
    facts = {"as_of": f"{as_of.day} {as_of:%B %Y}", "findings": collect_findings(), "n_tests": count_tests()}
    text = README.read_text(encoding="utf-8")
    README.write_text(replace_auto_block(text, render_block(facts)), encoding="utf-8")
    print(f"README auto-block updated: data as of {as_of.date()}, {facts['n_tests']} tests")


if __name__ == "__main__":
    main()
