"""V. The Calendar: euro vs dollar year-ends, and whether funding spikes can be forecast."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

import findings  # noqa: E402
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
ui.md(w.yearend_contrast_sentence(usd_t["mean"], usd_t["share_up"], usd_t["n"], eur_t["mean"], eur_t["share_up"],
                                  eur_t["n"]))
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
        "DM p vs baseline (all / turns)": (f"{m['dm_all_p']:.3f} / {m['dm_turn_p']:.3f}"
                                            if m.get("dm_all_p") is not None else "n/a"),
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
                    fillcolor=ui.hex_to_rgba(ui.CURRENCY_COLORS["USD"],
                                             0.18), line=dict(width=0), name="5-95% forecast")
    fig.add_scatter(x=pred.index, y=pred[f"{winner}_q50"], line=dict(color=ui.CURRENCY_COLORS["USD"], width=1),
                    name="median forecast")
    fig.add_scatter(x=pred.index, y=pred["actual"], line=dict(color=ui.COLORS["ink"], width=1), name="actual")
    fig.update_yaxes(title="SOFR minus IOR (bp)")
    ui.show_chart(fig, "USD test period: forecasts made 40 business days ahead against what happened", sources=SRC)

ui.section_heading("iii", "Are the forecast ranges calibrated?")
cal = ui.results().get("calibration") or {}
if cal:
    st.markdown("A well-calibrated 5-95% range contains the outcome on about 90% of days. The verdict uses an exact "
                "binomial interval; since forecasts 40 days ahead overlap, the block-bootstrap interval is shown too.")
    boot_f = (ui.results().get("bootstrap") or {}).get("forecast") or {}
    for cur in ("USD", "EUR", "JPY"):
        c = cal.get(cur)
        if not c:
            continue
        label = next(m["label"] for m in fc["currencies"][cur]["models"] if m["model"] == c["model"])
        b = boot_f.get(cur, {}).get("models", {}).get(c["model"], {}).get("ci_coverage", {})
        extra = (f" Block-bootstrap interval: {b['lower']:.1%} to {b['upper']:.1%}." if b.get("lower") is not None
                 else "")
        ui.md("- " + w.calibration_sentence(cur, label, c["interval_coverage"], c["interval_lower"],
                                            c["interval_upper"], c["verdict"], c["n"]) + extra)
    fig = go.Figure()
    for cur, symbol in (("USD", "circle"), ("EUR", "square"), ("JPY", "diamond")):
        c = cal.get(cur)
        if not c:
            continue
        qs = list(c["per_quantile"])
        share = [c["per_quantile"][q]["share_below"] for q in qs]
        fig.add_scatter(x=[f"{int(c['per_quantile'][q]['nominal'] * 100)}%" for q in qs], y=share, mode="markers",
                        name=cur, marker=dict(color=ui.CURRENCY_COLORS[cur], size=10, symbol=symbol),
                        error_y=dict(type="data", symmetric=False,
                                     array=[c["per_quantile"][q]["upper"] - s for q, s in zip(qs, share, strict=True)],
                                     arrayminus=[s - c["per_quantile"][q]["lower"] for q, s in
                                                 zip(qs, share, strict=True)]))
    fig.add_scatter(x=["5%", "50%", "90%", "95%"], y=[0.05, 0.5, 0.9, 0.95], mode="markers", name="nominal",
                    marker=dict(color=ui.COLORS["ink"], symbol="line-ew-open", size=22))
    fig.update_xaxes(type="category", title="forecast quantile")
    fig.update_yaxes(title="share of test days below the forecast", range=[0, 1.02])
    ui.show_chart(fig, "Coverage per quantile on the test period, with exact 95% intervals", height=320,
                  sources="results/inference/calibration.json")
    fig = go.Figure()
    for cur in ("USD", "EUR", "JPY"):
        c = cal.get(cur)
        if c:
            fig.add_bar(x=c["pit"]["bins"], y=c["pit"]["observed"], name=cur,
                        marker=dict(color=ui.CURRENCY_COLORS[cur]))
    first = next(iter(cal.values()))
    fig.add_scatter(x=first["pit"]["bins"], y=first["pit"]["expected"], mode="markers", name="expected",
                    marker=dict(color=ui.COLORS["ink"], symbol="line-ew-open", size=26))
    fig.update_yaxes(title="share of test days")
    ui.show_chart(fig, "Where outcomes fell relative to the forecast quantiles (PIT bins)", height=300,
                  sources="results/inference/calibration.json")

ui.section_heading("iv", "Term or overnight across a turn?")
tvo = fc["term_vs_overnight"]["USD"]
st.markdown("The rule: lock in two-week term funding seven business days before a month-end only when the "
            "forecast spike over the window exceeds today's term premium. Otherwise borrow overnight.")
ui.md(w.term_rule_sentence(tvo["saving_vs_on"], tvo["saving_vs_term"], tvo["n_locked"], tvo["n_windows"]))
totals = tvo["totals"]
ui.kpi_row([("Always overnight", w.money(totals["on"]), None), ("Always term", w.money(totals["term"]), None),
            ("The rule", w.money(totals["rule"]), None)])
st.caption("Total interest per USD 100m over every test-period month-end window (OFR DVP rates, ACT/360). "
           f"Euro: skipped. {fc['term_vs_overnight']['EUR']['reason'].capitalize()}.")

ui.section_heading("v", "Treasury cash and the overnight spread")
cash_lines = findings.treasury_cash_lines(ui.results())
if not cash_lines:
    ui.missing_results("Treasury cash")
else:
    ui.md(f"**{cash_lines[-1]}**")
    labels = {"EUR": ("government and other non-bank deposits at the Eurosystem (EUR bn)", "€STR minus DFR (bp)"),
              "USD": ("Treasury General Account (USD bn)", "SOFR minus IORB (bp)")}
    for i, cur in enumerate(("EUR", "USD")):
        ui.md(cash_lines[i])
        wk = ui.csv(f"desk/autonomous_weekly_{cur}.csv")
        if wk is None:
            continue
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_scatter(x=wk.index, y=wk["cash"] * 100, name=labels[cur][0],
                        line=dict(color=ui.COLORS["slate"], width=1.5), secondary_y=False)
        fig.add_scatter(x=wk.index, y=wk["spread"], name=labels[cur][1],
                        line=dict(color=ui.CURRENCY_COLORS[cur], width=1.5), secondary_y=True)
        for q in pd.date_range(wk.index.min(), wk.index.max(), freq="QE"):
            fig.add_vline(x=q, line=ui.ref_line(ui.COLORS["loss"] if q.month == 12 else ui.COLORS["rule"],
                                                "dot" if q.month != 12 else "dash", 1))
        fig.update_yaxes(title=labels[cur][0], secondary_y=False)
        fig.update_yaxes(title=labels[cur][1], secondary_y=True)
        ui.show_chart(fig, f"{cur}: Treasury cash and the weekly overnight spread (dotted: quarter-ends; dashed: "
                           "year-ends)", height=360, sources="ECB Data Portal, FRED, New York Fed")
    st.caption("Weekly changes regressed on weekly changes, train to 2022, tested from 2023; 95% intervals from a "
               "moving-block bootstrap (8 weeks, 1,000 resamples). The euro series is the Eurosystem's liabilities "
               "to other euro area residents, mostly government deposits (docs/METHODOLOGY.md, D2).")

ui.section_heading("vi", "The Fed's year-end toolkit")
tk, turns_tk = ui.results().get("toolkit"), ui.csv("desk/toolkit_turns.csv")
if tk is None or turns_tk is None:
    ui.missing_results("Fed toolkit")
else:
    ui.md(w.toolkit_pattern_sentence(tk["pattern"]))
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors = [ui.COLORS["loss"] if k == "year-end" else ui.CURRENCY_COLORS["USD"] for k in turns_tk["kind"]]
    fig.add_bar(x=turns_tk.index, y=turns_tk["repo_at"], name="Fed repo operations on the turn (USD bn)",
                marker=dict(color=colors), secondary_y=False)
    fig.add_scatter(x=turns_tk.index, y=turns_tk["spread_at_bp"], mode="markers+lines", name="SOFR minus IOR (bp)",
                    line=dict(color=ui.COLORS["ink"], width=1), secondary_y=True)
    fig.update_yaxes(title="repo operations (USD bn)", secondary_y=False)
    fig.update_yaxes(title="SOFR minus IOR on the turn (bp)", secondary_y=True)
    ui.show_chart(fig, "Fed repo operations and SOFR minus IOR on every quarter-end (year-ends in red)", height=340,
                  sources="FRED (RPONTTLD, WSHOBL, RRPONTSYD), New York Fed")
    recent = turns_tk[turns_tk.index >= "2024-01-01"][["kind", "repo_before", "repo_at", "repo_after", "rrp_at",
                                                        "spread_at_bp", "bills_bn", "bills_13w_change_bn"]]
    recent.columns = ["Turn", "Repo, week before (bn)", "Repo on the day (bn)", "Repo, week after (bn)",
                      "ON RRP on the day (bn)", "SOFR - IOR (bp)", "Fed bills (bn)", "Bills, 13-week change (bn)"]
    recent.index = recent.index.strftime("%d %b %Y")
    ui.table(recent.round(1))
    st.caption("Before and after: daily averages over the five business days either side of the turn (USD bn).")
ui.footer()
