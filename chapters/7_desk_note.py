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
ui.robustness_badge("desk_note")

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
v2 = note.get("v2") or {}
if v2.get("frozen"):
    ui.md("**v1 and v2 side by side.** v1 is the pre-registered headline forecast. v2, the challenger "
          "(conformalised quantile regression, with a distribution built from past year-ends for the turn itself), "
          "was designed after seeing v1's test-period calibration, so only its 31 December 2026 score is a clean test.")
    rows = []
    for cur in ("USD", "EUR"):
        for label, src in (("v1 (pre-registered)", note["frozen"]), ("v2 (challenger)", v2["frozen"])):
            x = src["currencies"][cur]
            rows.append({"Currency": cur, "Forecast": label, "5%": x["q05"], "Median": x["q50"], "90%": x["q90"],
                         "95%": x["q95"]})
    ui.table(pd.DataFrame(rows))
    for line in v2["lines"]:
        ui.md(f"- {line}")
    for line in v2["test"]:
        ui.md(f"- {line}")
turns = ui.csv("forecast/past_year_ends.csv")
if turns is not None:
    fig = go.Figure()
    for cur in ("USD", "EUR"):
        t = turns[turns["currency"] == cur]
        fig.add_scatter(x=t.index.year, y=t["actual"], mode="markers+lines", name=f"{cur} on the year-end day",
                        line=dict(color=ui.CURRENCY_COLORS[cur], width=1.5), marker=dict(size=9))
        fz = note["frozen"]["currencies"][cur]
        fig.add_scatter(x=[2026, 2026], y=[fz["q05"], fz["q95"]], mode="lines", name=f"{cur} v1 5-95% for 2026",
                        line=dict(color=ui.CURRENCY_COLORS[cur], width=6), opacity=0.35)
        if v2.get("frozen"):
            f2 = v2["frozen"]["currencies"][cur]
            fig.add_scatter(x=[2026.15, 2026.15], y=[f2["q05"], f2["q95"]], mode="lines",
                            name=f"{cur} v2 5-95% for 2026", line=dict(color=ui.CURRENCY_COLORS[cur], width=6, dash="dot"))
    fig.update_xaxes(title="year-end", dtick=1)
    fig.update_yaxes(title="spread to the policy rate on the year-end day (bp)")
    ui.show_chart(fig, "Every past year-end turn, and the 2026 ranges they support", height=360,
                  sources="New York Fed, FRED, ECB Data Portal")
    st.caption(f"The year-end tail rests on {int((turns['currency'] == 'USD').sum())} dollar and "
               f"{int((turns['currency'] == 'EUR').sum())} euro year-ends.")
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

if note.get("tails"):
    ui.md("**Why the 90th and 95th percentiles coincide.** The diagnosis below refits the frozen model on the "
          "same data; the frozen file itself is never changed.")
    for line in note["tails"]:
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
