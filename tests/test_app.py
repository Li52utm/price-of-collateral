"""Dashboard tests: every chapter through app.py with Streamlit's AppTest, offline; missing files; stale data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import findings
import ui

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
CHAPTERS = {"chapters/1_story.py": "story", "chapters/2_corridors.py": "corridors",
            "chapters/3_collateral.py": "collateral", "chapters/4_france.py": "france",
            "chapters/5_calendar.py": "calendar", "chapters/6_japan.py": "japan",
            "chapters/7_desk_note.py": "desk_note"}
TIMEOUT = 300


@pytest.fixture
def offline_app():
    st.cache_data.clear()

    def run(page: str | None = None) -> AppTest:
        at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        if page is not None:
            at.switch_page(page).run()
        return at

    yield run
    st.cache_data.clear()


def text_of(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def captions_of(at: AppTest) -> str:
    return " ".join(c.value for c in at.caption)


@pytest.mark.parametrize("page", list(CHAPTERS))
def test_every_chapter_renders_offline(offline_app, page: str) -> None:
    at = offline_app(page)
    assert not at.exception, [e.value for e in at.exception]
    captions = captions_of(at)
    assert f"Data as of {ui.day(ui.data_as_of())}, refreshed automatically each weekday." in captions
    assert "Not investment advice." in captions
    assert ui.validation_summary_line(ui.load_validation()) in captions
    key = CHAPTERS[page]
    q, a, _ = findings.answer(key, findings.load_results())
    text = text_of(at)
    assert f"**The question:** {q}" in text and f"**The answer: {a}." in text
    assert a != findings.NOT_AVAILABLE[0]
    if at.get("plotly_chart"):
        assert "Source: " in captions and "Data as of" in captions
    assert not [b.label for b in at.button if "refresh" in b.label.lower() or "fetch" in b.label.lower()]


def test_story_is_the_default_page(offline_app) -> None:
    at = offline_app()
    assert not at.exception
    assert "pawn shop" in text_of(at)


def test_desk_note_has_the_frozen_line_and_client_box(offline_app) -> None:
    at = offline_app("chapters/7_desk_note.py")
    text = text_of(at)
    assert "Would I advise a client to term out their year-end funding?" in text
    assert any(v in text for v in ("? Yes.**", "? No.**", "? Partly.**"))
    assert "To be scored after 31 December 2026" in text  # no score file before the turn
    html = " ".join(str(h.proto) for h in at.get("html"))
    assert "Forecast frozen on" in html and "commit" in html


def test_missing_results_files_explain_instead_of_crashing(offline_app, monkeypatch, tmp_path) -> None:
    empty = tmp_path / "results"
    (empty / "snapshots").mkdir(parents=True)
    # Keep the data manifest so the as-of line works; every results file is missing.
    (empty / "snapshots" / "manifest.json").write_text((ROOT / "results" / "snapshots" / "manifest.json").read_text())
    monkeypatch.setattr(ui, "RESULTS_DIR", empty)
    monkeypatch.setattr(findings, "RESULTS_DIR", empty)
    for page in CHAPTERS:
        at = offline_app(page)
        assert not at.exception, (page, [e.value for e in at.exception])
        assert findings.NOT_AVAILABLE[0] in text_of(at)
        if page != "chapters/1_story.py":
            assert "not available yet" in text_of(at)


def test_stale_data_shows_a_warning(offline_app, monkeypatch) -> None:
    monkeypatch.setattr(ui, "data_as_of", lambda: pd.Timestamp("2026-01-05"))
    at = offline_app("chapters/5_calendar.py")
    assert not at.exception
    assert "The data may be stale" in text_of(at)


def test_appendix_renders_with_robustness_and_tests(offline_app) -> None:
    at = offline_app(ui.APPENDIX_PAGE)
    assert not at.exception, [e.value for e in at.exception]
    text = text_of(at)
    rob = ui.read_result_json("robustness/table.json")
    for key, s in rob["summary"].items():
        assert f"**{key}.**" in text
        assert f"{s['holds']} of {s['n']}" in text or f"all {s['n']}" in text


def test_desk_note_page_states_term_rate_freshness_and_v2(offline_app) -> None:
    at = offline_app("chapters/7_desk_note.py")
    assert not at.exception, [e.value for e in at.exception]
    text = text_of(at)
    assert "Term premium input: the latest published OFR term repo rate is from" in text
    assert "v1 and v2 side by side" in text and "not a clean out-of-sample test" in text
    assert "not separately identified" in text
