"""VI. Japan: does Japanese overnight pricing follow the BoJ out of negative rates?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

SRC = "Bank of Japan"

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["japan"])
ui.question_box("japan")
ui.robustness_badge("japan")

j = ui.results().get("japan")
daily = ui.csv("japan/japan_daily.csv")
if j is None or daily is None:
    ui.missing_results("Japan")
    ui.footer()
    st.stop()

ui.section_heading("i", "Out of negative rates")
st.markdown("TONA is the rate Japanese banks pay each other overnight without collateral. The collateralized "
            "overnight call rate, the closest free daily stand-in for Japanese repo, is only available from 2025.")
d = daily.loc["2015-06-01":]
fig = go.Figure()
fig.add_scatter(x=d.index, y=d["policy"], name="BoJ policy rate", line=dict(color=ui.COLORS["ink"], shape="hv"))
fig.add_scatter(x=d.index, y=d["tona"], name="TONA", line=dict(color=ui.CURRENCY_COLORS["JPY"], width=1.2))
fig.add_scatter(x=d.index, y=d["collat"], name="collateralized overnight call", line=dict(color=ui.COLORS["slate"], width=1))
fig.update_yaxes(title="percent")
ui.show_chart(fig, "BoJ policy rate and overnight rates", sources=SRC)

ui.section_heading("ii", "How fast each change reached the market")
for c in j["changes"]:
    t = c["tona"]
    if t.get("available"):
        ui.md("- " + w.japan_change_sentence(c["date"], c["change_bp"], t["half_gap_days"], t["pass_through_20d"]))
rows = [{"Change": c["date"], "Size (bp)": round(c["change_bp"]), "New rate (%)": c["new_rate"],
         "TONA: days to half the gap": c["tona"].get("half_gap_days"),
         "TONA: pass-through over 20 days": f"{c['tona'].get('pass_through_20d', float('nan')):.0%}",
         "Collateralized call: days to half the gap": c["collat"].get("half_gap_days") if c["collat"].get("available") else "no data"}
        for c in j["changes"]]
ui.table(pd.DataFrame(rows))

ui.section_heading("iii", "Error-correction model")
ecm = pd.DataFrame([{"Sample": label, "Days": e["n"], "Policy changes": e["n_changes"],
                     "Gap correction per day": round(e["gamma"], 4),
                     "Half-life of a gap (business days)": round(e["half_life_days"], 1),
                     "Same-day pass-through": "n/a (no change in sample)" if e["beta"] is None else f"{e['beta']:.0%}",
                     "Mean gap (bp)": round(e["mean_gap_bp"], 1)}
                    for label, e in (("Since Feb 2016", j["ecm_full"]), ("Negative rates", j["ecm_negative"]),
                                     ("After the exit", j["ecm_exit"]))])
ui.table(ecm)
st.caption("d TONA = a + g (TONA - policy) yesterday + b d policy today; Newey-West errors with 10 lags.")
ui.footer()
