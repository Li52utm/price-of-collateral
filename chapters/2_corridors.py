"""II. Three Corridors: how tightly the ECB, the Fed and the BoJ hold overnight rates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["corridors"])
ui.question_box("corridors")
ui.robustness_badge("corridors")

c = ui.results().get("corridors")
if c is None:
    ui.missing_results("corridors")
    ui.footer()
    st.stop()

NAMES = {"EUR": ("ECB", "€STR", "Deposit facility", "Marginal lending"),
         "USD": ("Fed", "SOFR", "Target range, lower", "Target range, upper"),
         "JPY": ("BoJ", "TONA", "Policy rate", "Basic loan rate")}

ui.section_heading("i", "The corridors")
st.markdown("Each central bank sets a floor and a ceiling for overnight rates. The market rate should stay "
            "between them, close to the rate the bank wants.")
for cur in ("EUR", "USD", "JPY"):
    frame = ui.csv(f"corridors/corridor_{cur}.csv")
    if frame is None:
        continue
    bank, market, floor, ceiling = NAMES[cur]
    s = c["stats"][cur]
    ui.md(w.corridor_sentence(cur, s["inside_share"], s["below_floor_share"], s["recent_median_bp"],
                              s["recent_iqr_bp"], s["start"]))
    fig = go.Figure()
    fig.add_scatter(x=frame.index, y=frame["ceiling"], name=ceiling, line=ui.ref_line(ui.COLORS["slate"], "dot"))
    fig.add_scatter(x=frame.index, y=frame["floor"], name=floor, line=ui.ref_line(ui.COLORS["slate"]))
    if cur == "USD":
        fig.add_scatter(x=frame.index, y=frame["ior"], name="Interest on reserves", line=ui.ref_line(ui.COLORS["ink"],
                                                                                                     "dash"))
    fig.add_scatter(x=frame.index, y=frame["market"], name=market, line=dict(color=ui.CURRENCY_COLORS[cur], width=1.5))
    ui.shade_periods(fig, c["regimes"][cur], ("negative rates", "zero lower bound"))
    fig.update_yaxes(title="percent")
    ui.show_chart(fig, f"{bank}: policy corridor and {market}", height=340)

ui.section_heading("ii", "Calm and stressed regimes")
st.markdown("A two-regime model, estimated on 2022 and earlier, reads each day's spread to the policy rate as "
            "coming from a calm or a volatile regime. On later days it uses the same parameters and only past data.")
probs = ui.csv("corridors/stress_probability.csv")
for cur in ("USD", "EUR", "JPY"):
    m = c["markov"][cur]
    ui.md(w.markov_sentence(cur, m["mean_bp"]["calm"], m["mean_bp"]["stressed"], m["sd_bp"]["stressed"],
                            m["sd_bp"]["calm"], m["test_ll_per_day"], m["normal_ll_per_day"], m["share_stressed_test"]))
if probs is not None:
    fig = go.Figure()
    for cur in ("USD", "EUR", "JPY"):
        s = probs[cur].dropna()
        fig.add_scatter(x=s.index, y=s, name=NAMES[cur][1], line=dict(color=ui.CURRENCY_COLORS[cur], width=1))
    fig.add_vline(x="2023-01-01", line=ui.ref_line(dash="dash"))
    fig.update_yaxes(title="probability of the volatile regime", range=[0, 1])
    ui.show_chart(fig, "Filtered probability of the volatile regime (test period starts at the dashed line)",
                  height=320)

ui.section_heading("iii", "What happens as balance sheets shrink")
for cur in ("USD", "EUR"):
    ra = c["reserves"][cur]
    pairs, curve = ui.csv(f"corridors/reserves_pairs_{cur}.csv"), ui.csv(f"corridors/reserves_curve_{cur}.csv", None,
                                                                         False)
    identified = ra.get("kink_identified", True)
    ui.md(w.reserves_sentence(cur, ra["winner"], ra["slope_per_unit"], ra["pressure_point"], ra["pressure_band"],
                              ra["latest_liq"], ra["label"], identified, ra.get("boot_edge_share")))
    if pairs is None or curve is None:
        continue
    fig = go.Figure()
    fig.add_scatter(x=pairs["liq"], y=pairs["spread"], mode="markers", name="weeks",
                    marker=dict(color=ui.hex_to_rgba(ui.CURRENCY_COLORS[cur], 0.35), size=5))
    fig.add_scatter(x=curve["liq"], y=curve["fit"], name=f"{ra['winner']} fit (chosen out of sample)",
                    line=dict(color=ui.COLORS["ink"], width=2))
    fig.add_scatter(x=curve["liq"], y=curve["threshold_fit"], name=f"{ra['pressure_from']} fit (reference)",
                    line=ui.ref_line(ui.COLORS["amber"], "dash"))
    if ra["pressure_band"][0] is not None and identified:
        fig.add_vrect(x0=ra["pressure_band"][0], x1=ra["pressure_band"][1], fillcolor=ui.COLORS["amber_light"],
                      opacity=0.2, line_width=0)
    fig.add_vline(x=ra["latest_liq"], line=ui.ref_line(ui.COLORS["loss"], "dot"),
                  annotation_text="latest", annotation_position="top")
    fig.update_xaxes(title=ra["label"])
    fig.update_yaxes(title="spread to policy rate, next week (bp)")
    if cur == "USD":
        fig.update_yaxes(range=[-25, 40])
    ui.show_chart(fig, f"{cur}: liquidity against the overnight spread" + (" (band: 95% bootstrap range of the "
                                                                           "kink)" if identified
                                                             else " (kink not identified, no band shown)"), height=360)

ui.section_heading("iv", "Three episodes")
for case in c["cases"]:
    ui.md("- " + w.case_sentence(case["case"], case["currency"], case["peak_bp"], case["peak_date"], case["before_bp"]))
cases = pd.DataFrame(c["cases"])[["case", "currency", "peak_bp", "peak_date", "before_bp", "liquidity"]]
cases.columns = ["Episode", "Currency", "Peak spread (bp)", "Peak date", "Two weeks before (bp)", "Liquidity at start "
                                                                                                  "(tn)"]
ui.table(cases.round(2))
ui.footer()
