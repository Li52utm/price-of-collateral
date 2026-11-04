"""VII. The Year-End 2026 Desk Note: euro and dollar funding over 31 December 2026, frozen and scored."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import desk_note  # noqa: E402
import ui  # noqa: E402

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["desk_note"])
ui.question_box("desk_note")

note = desk_note.build(ui.results())
if note is None:
    ui.missing_results("frozen forecast")
    ui.footer()
    st.stop()

st.html(f'<p class="desk-title">{note["title"]}</p><p class="desk-meta">The Price of Collateral, desk note. '
        f'{note["frozen_line"]}</p>')
rec = note["recommendation"]
ui.verdict_box("Recommendation", f"USD: {rec['USD']}; EUR: {rec['EUR']}", " ".join(rec["lines"]))

ui.section_heading("i", "Key points")
for p in note["key_points"]:
    ui.md(f"- {p}")

ui.section_heading("ii", "The year-end forecast")
rows = []
for cur in ("USD", "EUR"):
    x = note["forecasts"][cur]
    rows.append({"Currency": cur, "Target": x["target"], "Model": x["model_label"], "5%": x["q05"], "Median": x["q50"],
                 "90%": x["q90"], "95%": x["q95"], "Latest level": x["latest_level"]})
ui.table(pd.DataFrame(rows))
for cur in ("USD", "EUR"):
    path = note["forecasts"][cur]["path"]
    days = pd.to_datetime(list(path))
    q = pd.DataFrame(list(path.values()), index=days)
    fig = go.Figure()
    color = ui.CURRENCY_COLORS[cur]
    fig.add_scatter(x=days, y=q["q95"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=days, y=q["q05"], fill="tonexty", fillcolor=ui.hex_to_rgba(color, 0.2), line=dict(width=0),
                    name="5-95% range")
    fig.add_scatter(x=days, y=q["q50"], mode="lines+markers", line=dict(color=color, width=2), name="median")
    fig.add_hline(y=note["forecasts"][cur]["latest_level"], line=ui.ref_line(dash="dot"), annotation_text="latest level")
    fig.update_yaxes(title=f"{note['forecasts'][cur]['target']} (bp)")
    ui.show_chart(fig, f"{cur}: frozen forecast over the turn", height=300,
                  sources="New York Fed, ECB Data Portal, FRED, OFR, US Treasury")
for m in note["models"]:
    ui.md(m)

ui.section_heading("iii", "What the turn means for funding")
for line in note["funding"]:
    ui.md(f"- {line}")

ui.section_heading("iv", "The France view")
for line in note["france"]:
    ui.md(line)

ui.section_heading("v", "Risks")
for line in note["risks"]:
    ui.md(f"- {line}")

ui.section_heading("vi", "Scoring")
for line in note["scoring"]:
    ui.note(line, "info" if note["scored"] else "warning")

ui.section_heading("vii", "Disclosures")
for line in note["disclosures"]:
    st.caption(line)

c = note["client"]
ui.verdict_box(c["question"], c["verdict"], c["sentence"])
st.download_button("Download the desk note (Markdown)", desk_note.markdown(note), file_name="yearend_2026_desk_note.md",
                   mime="text/markdown")
ui.footer()
