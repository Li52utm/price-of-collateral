"""U7: the committed research note is exactly what scripts/build_note.py generates from the results."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_note  # noqa: E402


def test_note_is_generated_from_results() -> None:
    text = build_note.build(build_note.load())
    assert text == build_note.NOTE.read_text(encoding="utf-8")
    assert 2500 <= build_note.word_count(text) <= 4000
    for section in ("## Abstract", "## 2. Data", "## 3. Methods", "## 4. Results", "## 5. Robustness",
                    "## 6. The frozen Year-End 2026 forecasts", "## 7. Limitations", "## References"):
        assert section in text
    for fig in build_note.FIG_DIR.glob("*.png"):
        assert f"figures/{fig.name}" in text
