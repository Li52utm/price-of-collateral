"""V. The Calendar: euro vs dollar year-ends, and whether funding spikes can be forecast."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

SRC = "New York Fed, ECB Data Portal, FRED, OFR, US Treasury"

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["calendar"])
ui.question_box("calendar")
ui.robustness_badge("calendar")

fc = ui.results().get("forecast")
if fc is None:
    ui.missing_results("forecast")
    ui.footer()
    st.stop()

ui.section_heading("i", "Dollar and euro year-ends go opposite ways")
usd_t, eur_t = fc["currencies"]["USD"]["turns"]["ye"], fc["currencies"]["EUR"]["turns"]["ye"]
ui.md(w.yearend_contrast_sentence(usd_t["mean"], usd_t["share_up"], usd_t["n"], eur_t["mean"], eur_t["share_up"], eur_t["n"]))
ui.md(w.yearend_mechanism_sentence(usd_t["mean"], eur_t["mean"]))
fig = go.Figure()
for cur in ("USD", "EUR"):
    te = ui.csv(f"forecast/turn_effects_{cur}.csv", None, False)
    if te is None:
        continue
    te["date"] = pd.to_datetime(te["date"])
    ye = te[te["type"] == "ye"]
    fig.add_bar(x=ye["date"].dt.year, y=ye["effect"], name=w.MARKET_NAMES[cur], marker_color=ui.CURRENCY_COLORS[cur])
fig.update_layout(barmode="group")
fig.update_yaxes(title="year-end day minus the previous two weeks (bp)")
ui.show_chart(fig, "The year-end turn, each year", height=320, sources=SRC)
rows = []
for cur in ("USD", "EUR", "JPY"):
    for kind, label in (("ye", "Year-end"), ("qe", "Quarter-end"), ("me", "Month-end")):
        t = fc["currencies"][cur]["turns"][kind]
        rows.append({"Currency": cur, "Turn": label, "Number": t["n"], "Mean effect (bp)": round(t["mean"], 1),
                     "Median (bp)": round(t["median"], 1), "Share up": f"{t['share_up']:.0%}"})
ui.table(pd.DataFrame(rows))

ui.section_heading("ii", "Can the spikes be forecast? The honest test")
st.markdown(f"Three models forecast the median and the 5th, 90th and 95th percentiles of each spread "
            f"{fc['horizon_bd']} business days ahead, using only data published by then. They are fitted on data to "
            f"{fc['train_end']} and judged on {fc['test_start'][:4]} onward, which they never saw.")
for cur in ("USD", "EUR", "JPY"):
    cur_s = fc["currencies"][cur]
    win = next(m for m in cur_s["models"] if m["model"] == cur_s["winner"])
    base = next(m for m in cur_s["models"] if m["model"] == "baseline")
    boot_m = (((ui.results().get("bootstrap") or {}).get("forecast") or {}).get(cur) or {}).get("models", {})
    ui.md(w.model_comparison_sentence(cur, win["label"], win["pinball_turn"], base["pinball_turn"],
                                      win.get("dm_turn_p_holm", win.get("dm_turn_p")), cur_s["winner"] == "baseline",
                                      boot_m.get(cur_s["winner"], {}).get("ci_diff_turn"), "dm_turn_p_holm" in win))
    table = pd.DataFrame([{
        "Model": m["label"], "Pinball loss, all days": round(m["pinball_all"], 3),
        "Pinball loss, turn days": round(m["pinball_turn"], 3),
        "Below 90th pct": f"{m['below_q90']:.0%}", "Below 95th pct": f"{m['below_q95']:.0%}",
        "Inside 5-95%": f"{m['interval_coverage']:.0%}",
        "DM p vs baseline (all / turns)": (f"{m['dm_all_p']:.3f} / {m['dm_turn_p']:.3f}" if m.get("dm_all_p") is not None
                                            else "n/a"),
        "Holm-adjusted (all / turns)": (f"{m['dm_all_p_holm']:.3f} / {m['dm_turn_p_holm']:.3f}"
                                        if m.get("dm_all_p_holm") is not None else "n/a")} for m in cur_s["models"]])
    with st.expander(f"{cur}: test period {cur_s['test_start']} to {cur_s['test_end']}, {cur_s['n_test']} days, "
                     f"{cur_s['n_test_turn']} turn days", expanded=cur == "USD"):
        ui.table(table)

pred = ui.csv("forecast/test_predictions_USD.csv")
winner = fc["currencies"]["USD"]["winner"]
if pred is not None:
    fig = go.Figure()
    fig.add_scatter(x=pred.index, y=pred[f"{winner}_q95"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=pred.index, y=pred[f"{winner}_q05"], fill="tonexty",
                    fillcolor=ui.hex_to_rgba(ui.CURRENCY_COLORS["USD"], 0.18), line=dict(width=0), name="5-95% forecast")
    fig.add_scatter(x=pred.index, y=pred[f"{winner}_q50"], line=dict(color=ui.CURRENCY_COLORS["USD"], width=1),
                    name="median forecast")
    fig.add_scatter(x=pred.index, y=pred["actual"], line=dict(color=ui.COLORS["ink"], width=1), name="actual")
    fig.update_yaxes(title="SOFR minus IOR (bp)")
    ui.show_chart(fig, "USD test period: forecasts made 40 business days ahead against what happened", sources=SRC)

ui.section_heading("iii", "Term or overnight across a turn?")
tvo = fc["term_vs_overnight"]["USD"]
st.markdown("The rule: lock in two-week term funding seven business days before a month-end only when the "
            "forecast spike over the window exceeds today's term premium. Otherwise borrow overnight.")
ui.md(w.term_rule_sentence(tvo["saving_vs_on"], tvo["saving_vs_term"], tvo["n_locked"], tvo["n_windows"]))
totals = tvo["totals"]
ui.kpi_row([("Always overnight", w.money(totals["on"]), None), ("Always term", w.money(totals["term"]), None),
            ("The rule", w.money(totals["rule"]), None)])
st.caption("Total interest per USD 100m over every test-period month-end window (OFR DVP rates, ACT/360). "
           f"Euro: skipped. {fc['term_vs_overnight']['EUR']['reason'].capitalize()}.")
ui.footer()
