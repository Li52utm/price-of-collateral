"""IV. Italy Then, France Now: will French OATs bounce back, and what would it take?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import events  # noqa: E402
import findings  # noqa: E402
import ui  # noqa: E402
import wording as w  # noqa: E402

SRC = "ECB Data Portal (IRS monthly yields, MMSR), Assemblée nationale"
SRC_DAILY = "Banque de France (Webstat), Deutsche Bundesbank"

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["france"])
ui.question_box("france")
ui.robustness_badge("france")

f = ui.results().get("france")
spreads = ui.csv("collateral/yield_spreads_monthly.csv")
if f is None or spreads is None:
    ui.missing_results("France")
    ui.footer()
    st.stop()

fd = ui.results().get("france_daily")
ui.note("The daily view uses the Banque de France's daily 10-year OAT yield (TEC10, Webstat) against the "
        "Bundesbank's daily 10-year Bund. Italian and Spanish yields exist only monthly, so the euro-wide split and "
        "the cross-country base rates stay monthly; the monthly rules are kept as the robustness check.")
for line in findings.construction_lines(ui.results()):
    ui.note(line)

if fd:
    ui.section_heading("i", "France now, day by day")
    daily = ui.csv("france/daily_spread.csv")
    rules, nowd = fd["rules"], fd["rules"]["now"]
    b = rules["blowout"]["30"]["status"]
    g = rules["gradual"]["15bp_6m"]["status"]
    ui.md(w.daily_rules_sentence(nowd["date"], nowd["spread"], nowd["smoothed"], nowd["baseline"], b["in_episode"],
                                 b.get("start"), b.get("peak"), b.get("half_retrace_level"),
                                 b.get("p_recover_next_12m"), g["in_episode"], f["france_now"]["in_episode"]))
    dd = fd["decomposition"]
    ui.md(w.decomposition_sentence(w.pd_day(dd["base_day"]), w.pd_day(dd["last_day"]), dd["spread_base"],
                                   dd["spread_last"], dd["oat_leg"], dd["bund_contribution"]))
    if daily is not None:
        recent = daily.loc["2023-01-01":]
        fig = go.Figure()
        fig.add_scatter(x=recent.index, y=recent["spread"], name="daily spread",
                        line=dict(color=ui.hex_to_rgba(ui.COUNTRY_COLORS["FR"], 0.45), width=1))
        fig.add_scatter(x=recent.index, y=recent["smoothed"], name="5-day average",
                        line=dict(color=ui.COUNTRY_COLORS["FR"], width=2))
        fig.add_scatter(x=recent.index, y=recent["baseline"] + 30, name="blowout line (trailing year + 30 bp)",
                        line=ui.ref_line(ui.COLORS["loss"], "dash"))
        fig.add_scatter(x=recent.index, y=recent["baseline"] + 15, name="gradual line (trailing year + 15 bp)",
                        line=ui.ref_line(ui.COLORS["slate"], "dot"))
        fig.update_yaxes(title="OAT-Bund 10-year spread (bp)")
        ui.show_chart(fig, "The OAT-Bund spread, daily, against the two episode rules", height=340,
                      sources="Banque de France (Webstat), Deutsche Bundesbank")
    if fd.get("gradual_panel", {}).get("n_episodes"):
        gp = fd["gradual_panel"]
        ui.md(w.gradual_base_rate_sentence(gp["n_episodes"], gp["n_countries"], gp["median_months"],
                                           gp["at"]["12"]["survival"]))

ui.section_heading("ii", "Italy then, France now")
fig = go.Figure()
for cty in ("IT", "ES", "PT", "FR"):
    fig.add_scatter(x=spreads.index, y=spreads[cty], name=cty, line=dict(color=ui.COUNTRY_COLORS[cty],
                                                                         width=2.5 if cty == "FR" else 1.2))
fig.update_yaxes(title="10-year spread to Germany (bp)", range=[0, 700])
ui.show_chart(fig, "Ten-year government bond spreads to Germany, monthly", sources=SRC)

d, e = f["decomposition"], f["euro_wide"]
ui.section_heading("iii", "Bund leg or OAT leg; France or the euro area? (monthly)")
ui.md(w.decomposition_sentence(d["base_month"], d["last_month"], d["spread_base"], d["spread_last"], d["oat_leg"],
                               d["bund_leg"]))
fs = (ui.results().get("bootstrap") or {}).get("france_split")
ui.md(w.france_specific_sentence(e["since"], e["cum_change"], e["cum_euro_wide"], e["cum_france_specific"],
                                 fs["ci_france_specific"] if fs else None, fs["ci_euro_wide"] if fs else None))
split = ui.csv("france/france_specific_monthly.csv")
if split is not None:
    since = split.loc[e["since"]:]
    fig = go.Figure()
    fig.add_scatter(x=since.index, y=since["fr_change"].cumsum(), name="OAT-Bund spread change",
                    line=dict(color=ui.COUNTRY_COLORS["FR"], width=2.5))
    fig.add_scatter(x=since.index, y=since["euro_wide"].cumsum(), name="euro-wide part (implied by IT and ES)",
                    line=dict(color=ui.COLORS["slate"], dash="dash"))
    fig.add_scatter(x=since.index, y=since["france_specific"].cumsum(), name="France-specific part",
                    line=dict(color=ui.COLORS["loss"]))
    fig.update_yaxes(title="cumulative change since the dissolution month (bp)")
    ui.show_chart(fig, "Where the French widening came from", height=320, sources=SRC)
st.caption(f"Euro-wide beta estimated on {f['euro_wide']['n_fit']} months to December 2023: "
           f"{e['params']['IT']:.2f} on Italy and {e['params']['ES']:.2f} on Spain (R² {e['r2']:.2f}).")

ui.section_heading("iv", "How long do blowouts last? (monthly base rates)")
v, now = f["survival"], f["france_now"]
a12 = v["at"]["12"]
ui.md(w.survival_sentence(v["n_episodes"], v["n_countries"], v["median_months"], a12["survival"], a12["lower"],
                          a12["upper"], f["threshold_bp"]))
sens20 = f["sensitivity"].get("20", {}).get("france")
ui.md(w.france_status_sentence(now["in_episode"], now["spread_now"], now.get("trailing_baseline"),
                               now.get("gap_to_threshold"), f["threshold_bp"], 20 if sens20 else None,
                               sens20["start"] if sens20 else None, sens20["p_recover_next_12m"] if sens20 else None))
km = ui.csv("france/kaplan_meier.csv", None, False)
if km is not None:
    fig = go.Figure()
    fig.add_scatter(x=km["time"], y=km["upper"], line=dict(width=0, shape="hv"), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=km["time"], y=km["lower"], fill="tonexty", fillcolor=ui.hex_to_rgba(ui.COLORS["ink"], 0.12),
                    line=dict(width=0, shape="hv"), name="95% band")
    fig.add_scatter(x=km["time"], y=km["survival"], line=dict(color=ui.COLORS["ink"], width=2, shape="hv"),
                    name="share of episodes not yet half-retraced")
    fig.update_xaxes(title="months since the blowout started")
    fig.update_yaxes(title="share", range=[0, 1])
    ui.show_chart(fig, "Kaplan-Meier: time to retrace half the widening", height=320, sources=SRC)
eps = ui.csv("france/episodes.csv", None, False)
if eps is not None:
    with st.expander(f"All {len(eps)} episodes"):
        show = eps[["country", "start", "baseline", "peak", "peak_date", "recovery", "duration"]].copy()
        show.columns = ["Country", "Start", "Baseline (bp)", "Peak (bp)", "Peak month", "Half retraced", "Months"]
        ui.table(show.round(1))
sens = f["sensitivity"]
st.caption("Sensitivity (thresholds fixed in advance): " + "; ".join(
    f"{k} bp rule: {s['n_episodes']} episodes, median {s['median_months']:.0f} months"
    for k, s in sens.items()) + ".")

ui.section_heading("v", "What preceded recoveries, and where France stands")
cs, cond = f["conditions_share"], now["conditions"]
rows = [{"Condition (6 months before recovery)": "The ECB had cut the deposit rate during the episode",
         "Share of past recoveries": f"{cs['ecb_cut'][0]:.0%} of {cs['ecb_cut'][1]}",
         "France now": "yes" if cond["ecb_cut"] else "no"},
        {"Condition (6 months before recovery)": "Other countries' spreads were tightening",
         "Share of past recoveries": f"{cs['peers_tightening'][0]:.0%} of {cs['peers_tightening'][1]}",
         "France now": "yes" if cond["peers_tightening"] else "no"},
        {"Condition (6 months before recovery)": "The Eurosystem was a net buyer of the country's bonds",
         "Share of past recoveries": f"{cs['eurosystem_buying'][0]:.0%} of {cs['eurosystem_buying'][1]}",
         "France now": "yes" if cond["eurosystem_buying"] else "no"}]
ui.table(pd.DataFrame(rows))

ui.section_heading("vi", "Is French collateral now priced like Italian?")
r = f["repo"]
p_gap, adjusted = findings.adjusted_p(ui.results(), "chow_june2024_it_fr", r["chow_it_fr"]["p_value"])
ui.md(w.repo_treatment_sentence(r["fr_de_before"], r["fr_de_after"], r["it_de_before"], r["it_de_after"],
                                r["position_before"], r["position_after"], p_gap,
                                r["latest"]["fr_de"], r["latest"]["it_de"], adjusted))
panel = ui.csv("collateral/period_panel.csv")
if panel is not None:
    fig = go.Figure()
    for cty in ("IT", "FR"):
        fig.add_scatter(x=panel.index, y=panel[f"repo_{cty}"], name=w.COUNTRY_NAMES[cty] + " collateral",
                        line=dict(color=ui.COUNTRY_COLORS[cty], width=2))
    fig.add_vline(x=r["split_period"], line=ui.ref_line(dash="dash"), annotation_text="June 2024")
    fig.update_yaxes(title="repo premium over German collateral (bp)")
    ui.show_chart(fig, "French and Italian collateral in repo", height=300, sources=SRC)

ui.section_heading("vii", "Events")
st.markdown("Each event is confirmed by at least two independent reputable sources (official sites, Reuters, "
            "Bloomberg, the Financial Times, CNBC, Les Echos, Le Monde), listed below with the access date and method.")
daily_by_date = {ev["date"]: ev for ev in (fd or {}).get("events", [])}
monthly_by_date = {ev["date"]: ev for ev in f["events"]}
rows = []
for ev in events.EVENTS:
    d, m = daily_by_date.get(ev["date"]), monthly_by_date.get(ev["date"])
    rows.append({"Date": ev["date"], "Kind": ev["kind"], "Event": ev["event"],
                 "Two-day change (bp)": round(d["change_bp"], 1) if d else None,
                 "Percentile (two-day)": f"{d['percentile']:.0%}" if d else "n/a",
                 "Month change (bp)": round(m["change_bp"], 1) if m else None,
                 "Sources": "; ".join(f"{s['outlet']} ({s['method']}, {s['accessed']})" for s in ev["sources"])})
ui.table(pd.DataFrame(rows))
for ev in (fd or {}).get("events", []):
    ui.md("- " + w.daily_event_sentence(ev["event"], ev["event_day"], ev["change_bp"], ev["percentile"]))
if fd and fd.get("events_summary"):
    s = fd["events_summary"]
    ui.md(w.event_study_summary_sentence(s["n"], s["n_unusual"], s["mean_change"], s["n_widened"]))
with st.expander("Source links"):
    for ev in events.EVENTS:
        ui.md(f"- {ev['date']}, {ev['event']}: " + ", ".join(f"[{s['outlet']}]({s['url']})" for s in ev["sources"]))
st.caption(f"Sources checked on {events.CHECKED_ON}. Excluded: "
           + "; ".join(f"{x['event']} ({x['reason']})" for x in events.EXCLUDED) + ".")
ui.section_heading("viii", "Who absorbed France's new debt")
absorb = findings.france_absorption_line(ui.results())
hold = ui.results().get("holders")
if absorb is None or not hold["france_absorption"]:
    ui.missing_results("holders")
else:
    ui.md(absorb)
    a = hold["france_absorption"]
    ch = pd.Series(a["change_bn"]).sort_values()
    fig = go.Figure(go.Bar(x=ch.values, y=ch.index, orientation="h",
                           marker=dict(color=[ui.COUNTRY_COLORS["FR"] if v > 0 else ui.COLORS["slate"] for v in ch])))
    fig.add_vline(x=0, line=ui.ref_line())
    fig.update_xaxes(title=f"change in holdings, end-{a['base'][:4]} to end-{a['latest'][:4]} (EUR bn)")
    ui.show_chart(fig, "Change in holdings of French government debt by holder", height=300,
                  sources="Eurostat (gov_10dd_ggd)")
ui.footer()
