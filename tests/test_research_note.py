"""U7: the committed research note is exactly what scripts/build_note.py generates from the results."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_note  # noqa: E402


def test_note_is_generated_from_results(tmp_path: Path) -> None:
    # Figures go to a temporary directory: drawing into docs/figures/ would rewrite tracked files (and PNG
    # bytes differ between platforms). The committed figures are checked by name only.
    text = build_note.build(build_note.load(), fig_dir=tmp_path)
    assert text == build_note.NOTE.read_text(encoding="utf-8")
    assert 2500 <= build_note.word_count(text) <= 4000
    for section in ("## Abstract", "## 2. Data", "## 3. Methods", "## 4. Results", "## 5. Robustness",
                    "## 6. The frozen Year-End 2026 forecasts", "## 7. Limitations", "## References",
                    "## Appendix A. The funding desk view"):
        assert section in text
    drawn = sorted(f.name for f in tmp_path.glob("*.png"))
    assert drawn == sorted(f.name for f in build_note.FIG_DIR.glob("*.png")) and len(drawn) == 7
    for name in drawn:
        assert f"figures/{name}" in text
