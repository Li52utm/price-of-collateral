"""III. The Price of Collateral: Italian and French against German repo, credit risk or scarcity?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

SRC = "ECB Data Portal (MMSR, IRS), ECB PSPP breakdown"

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["collateral"])
ui.question_box("collateral")

c = ui.results().get("collateral")
panel = ui.csv("collateral/period_panel.csv")
if c is None or panel is None:
    ui.missing_results("collateral")
    ui.footer()
    st.stop()

ui.section_heading("i", "What lenders charge against each country's bonds")
st.markdown("The ECB's money-market statistics report repo rates by the country that issued the collateral, "
            "averaged over each reserve maintenance period (about six weeks). The chart shows how much more a "
            "cash lender earned, overnight (spot-next), against each country's bonds than against German Bunds.")
fig = go.Figure()
for cty in ("IT", "FR", "ES"):
    fig.add_scatter(x=panel.index, y=panel[f"repo_{cty}"], name=w.COUNTRY_NAMES[cty] + " collateral",
                    line=dict(color=ui.COUNTRY_COLORS[cty], width=2), mode="lines+markers", marker=dict(size=4))
fig.add_hline(y=0, line=ui.ref_line(ui.COUNTRY_COLORS["DE"]), annotation_text="German collateral")
fig.add_vline(x=c["qt_start"], line=ui.ref_line(dash="dash"), annotation_text="start of QT")
fig.update_yaxes(title="repo rate minus German-collateral rate (bp)")
ui.show_chart(fig, "Repo premium over German collateral, per maintenance period", sources=SRC)

ui.section_heading("ii", "Credit risk or scarcity?")
st.markdown("Two stories can explain the premium. **Credit**: lenders want more against bonds of a riskier "
            "government, measured by its 10-year yield spread to Germany. **Scarcity**: German Bunds are in short "
            "supply because the Eurosystem holds so many, and plentiful central bank liquidity lets cash chase "
            "them, so the Bund repo rate falls below the others.")
rows = []
for cty in ("IT", "FR"):
    r = c["regressions"][cty]
    scarcity = abs(r["std_effect"]["liquidity"]) + abs(r["std_effect"]["de_holdings"])
    ui.md(w.collateral_sentence(cty, r["verdict"], r["std_effect"]["credit"], scarcity, r["r2"], r["mean_spread"],
                                r["latest_spread"]))
    ui.md(w.qt_break_sentence(cty, r["chow"]["p_value"], r["sub_periods"].get("before_qt", {}).get("verdict"),
                              r["sub_periods"].get("after_qt", {}).get("verdict")))
    for k in ("credit", "liquidity", "de_holdings"):
        rows.append({"Collateral": w.COUNTRY_NAMES[cty], "Variable": c["labels"][k],
                     "Coefficient": round(r["params"][k], 3), "p-value (Newey-West)": round(r["pvalues"][k], 3),
                     "Effect of one standard deviation (bp)": round(r["std_effect"][k], 2)})
ui.table(pd.DataFrame(rows))
st.caption(f"{c['n_periods']} maintenance periods; Newey-West standard errors with 3 lags; structural break test "
           f"(Chow) at the start of quantitative tightening, {c['qt_start']}.")

ui.section_heading("iii", "Did it change? Rolling coefficients")
for cty in ("IT", "FR"):
    roll = ui.csv(f"collateral/rolling_{cty}.csv", None, False)
    if roll is None:
        continue
    roll["end"] = pd.to_datetime(roll["end"])
    fig = go.Figure()
    fig.add_scatter(x=roll["end"], y=roll["credit"] * 10, name="credit: bp per 10 bp of yield spread",
                    line=dict(color=ui.COUNTRY_COLORS[cty], width=2))
    fig.add_scatter(x=roll["end"], y=roll["liquidity"], name="liquidity: bp per EUR 1 trillion",
                    line=dict(color=ui.COLORS["ink"], width=1.5, dash="dash"))
    fig.add_hline(y=0, line=ui.ref_line())
    fig.update_yaxes(title="coefficient (bp)")
    ui.show_chart(fig, f"{w.COUNTRY_NAMES[cty]} collateral: coefficients over rolling 24-period windows", height=300,
                  sources=SRC)
ui.footer()
