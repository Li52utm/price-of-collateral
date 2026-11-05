"""Router for "The Price of Collateral": a repo-market research dashboard in seven chapters.

Run with: .venv\\Scripts\\streamlit run app.py

This file only sets up the page and the navigation; each chapter lives in chapters/ (NOT pages/,
which would switch on Streamlit's automatic page list). Titles come from ui.CHAPTERS.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

import ui  # noqa: E402

PAGE_FILES = {
    "story": "chapters/1_story.py",
    "corridors": "chapters/2_corridors.py",
    "collateral": "chapters/3_collateral.py",
    "france": "chapters/4_france.py",
    "calendar": "chapters/5_calendar.py",
    "japan": "chapters/6_japan.py",
    "desk_note": "chapters/7_desk_note.py",
}

st.set_page_config(page_title="The Price of Collateral", layout="wide")

pages = [
    st.Page(PAGE_FILES[key], title=f"{chapter['numeral']}. {chapter['title']}",
            url_path=key.replace("_", "-"), default=key == "story")
    for key, chapter in ui.CHAPTERS.items()
] + [st.Page(ui.APPENDIX_PAGE, title=f"{ui.APPENDIX['numeral']}. {ui.APPENDIX['title']}", url_path="robustness")]
st.navigation(pages).run()
