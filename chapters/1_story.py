"""I. The Story: what is repo, and why does the bond you hand over matter? (for readers new to finance)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

ui.apply_theme()
ui.chapter_heading(**ui.CHAPTERS["story"])
ui.question_box("story")

r = ui.results()
corr, col, fr, fc, frozen = (r.get(k) for k in ("corridors", "collateral", "france", "forecast", "frozen"))

ui.section_heading("i", "A pawn shop for government bonds")
st.markdown(
    "A bank or a fund that owns government bonds but needs cash for a night can hand the bonds to a lender, "
    "take the cash, and buy the bonds back the next morning for slightly more. That is a **repo** (a sale and "
    "repurchase). The extra paid back is the interest. Like a pawn shop, the lender keeps the bonds if the "
    "borrower does not come back, and lends a little less than the bonds are worth (the **haircut**).")
st.markdown("Trillions of dollars and euros are borrowed this way every day. It is how banks, funds and "
            "governments' bond markets stay supplied with cash overnight.")

ui.section_heading("ii", "The price follows the central bank")
eur = ui.csv("corridors/corridor_EUR.csv")
if corr and eur is not None:
    s = corr["stats"]["EUR"]
    st.markdown(f"The overnight rate is set, in practice, by the central bank. In the euro area, banks can always "
                f"leave cash at the European Central Bank and earn its deposit rate, so market rates stay close to it. "
                f"Over the past year the euro overnight rate sat {w.bp(s['recent_median_bp'])} "
                f"{w.above_or_below(s['recent_median_bp'])} that deposit rate.")
    d = eur.loc["2019-10-01":]
    fig = go.Figure()
    fig.add_scatter(x=d.index, y=d["floor"], name="ECB deposit rate", line=dict(color=ui.COLORS["ink"], shape="hv"))
    fig.add_scatter(x=d.index, y=d["market"], name="euro overnight rate (€STR)",
                    line=dict(color=ui.CURRENCY_COLORS["EUR"], width=1.5))
    fig.update_yaxes(title="percent a year")
    ui.show_chart(fig, "The euro overnight rate follows the ECB's deposit rate", height=300)
else:
    ui.missing_results("corridors")

ui.section_heading("iii", "Why the bond you hand over matters")
panel = ui.csv("collateral/period_panel.csv")
if panel is not None and col:
    last = panel.iloc[-1]
    end = panel.index[-1]
    it = col["regressions"]["IT"]
    st.markdown(f"Not all bonds are equally welcome. German government bonds are the safest and the most wanted, "
                f"so lenders accept the lowest return against them. Lending against Italian bonds has earned "
                f"{w.bp(it['mean_spread'])} more on average since 2018. In the period to {ui.day(end)}, the extra "
                f"return was {w.signed_bp(last['repo_IT'])} for Italian, {w.signed_bp(last['repo_FR'])} for French "
                f"and {w.signed_bp(last['repo_ES'])} for Spanish bonds.")
    fig = go.Figure()
    for cty in ("IT", "FR", "ES"):
        fig.add_bar(x=[w.COUNTRY_NAMES[cty]], y=[last[f"repo_{cty}"]], marker_color=ui.COUNTRY_COLORS[cty],
                    name=w.COUNTRY_NAMES[cty], showlegend=False)
    fig.update_yaxes(title="extra repo return over German bonds (bp)")
    ui.show_chart(fig, "What lenders earn on top of German collateral, latest period", height=280,
                  sources="ECB Data Portal (MMSR)")

ui.section_heading("iv", "The calendar matters too")
if fc:
    usd_t, eur_t = fc["currencies"]["USD"]["turns"]["ye"], fc["currencies"]["EUR"]["turns"]["ye"]
    st.markdown("Banks tidy up their balance sheets for the year-end snapshot that regulators and shareholders "
                "see. On the last day of the year they lend less, and the price of overnight cash jumps. "
                + w.yearend_contrast_sentence(usd_t["mean"], usd_t["share_up"], usd_t["n"], eur_t["mean"],
                                              eur_t["share_up"], eur_t["n"]))
    fig = go.Figure()
    fig.add_bar(x=["Dollar", "Euro"], y=[usd_t["mean"], eur_t["mean"]],
                marker_color=[ui.CURRENCY_COLORS["USD"], ui.CURRENCY_COLORS["EUR"]])
    fig.update_yaxes(title="average year-end jump (bp)")
    ui.show_chart(fig, "On an average year-end the dollar rate jumps; the euro rate does not", height=260)

ui.section_heading("v", "When a government worries lenders")
spreads = ui.csv("collateral/yield_spreads_monthly.csv")
if spreads is not None and fr:
    d = fr["decomposition"]
    st.markdown(f"Investors also demand more to hold a government's bonds when its finances or politics worry them. "
                f"France pays {w.bp(d['spread_last'], 0)} more than Germany to borrow for ten years, up from "
                f"{w.bp(d['spread_base'], 0)} in {d['base_month']}, while Italy's gap has narrowed.")
    s = spreads.loc["2015-01-01":]
    fig = go.Figure()
    for cty in ("IT", "FR"):
        fig.add_scatter(x=s.index, y=s[cty], name=w.COUNTRY_NAMES[cty], line=dict(color=ui.COUNTRY_COLORS[cty],
                                                                                  width=2))
    fig.update_yaxes(title="extra 10-year borrowing cost over Germany (bp)")
    ui.show_chart(fig, "French and Italian borrowing costs above Germany's", height=300, sources="ECB Data Portal")

ui.section_heading("vi", "The bet on this year-end")
if frozen:
    u, e = frozen["currencies"]["USD"], frozen["currencies"]["EUR"]
    st.markdown("Before 31 December 2026 this project froze a forecast of the year-end jump, to be checked "
                "against what actually happens. Chapter VII is the full note.")
    ui.kpi_row([("Dollar, 31 Dec 2026", w.signed_bp(u["q50"]), None,
                 f"Most likely; 90% range {w.signed_bp(u['q05'])} to {w.signed_bp(u['q95'])}."),
                ("Euro, 31 Dec 2026", w.signed_bp(e["q50"]), None,
                 f"Most likely; 90% range {w.signed_bp(e['q05'])} to {w.signed_bp(e['q95'])}.")])

with st.expander("Glossary"):
    st.markdown(
        "- **Repo**: a loan of cash against a bond, unwound the next day (or later).\n"
        "- **Collateral**: the bond handed over to secure the loan.\n"
        "- **Haircut**: how much less than the bond's value the lender is willing to lend.\n"
        "- **Basis point (bp)**: one hundredth of a percentage point; 25 bp = 0.25%.\n"
        "- **€STR, SOFR, TONA**: the euro, dollar and yen overnight reference rates.\n"
        "- **Deposit facility rate (DFR)**: what the ECB pays banks on overnight deposits.\n"
        "- **Interest on reserves (IOR)**: what the Fed pays banks on their reserves.\n"
        "- **Spread**: the difference between two rates or yields.\n"
        "- **OAT, BTP, Bund**: French, Italian and German government bonds.\n"
        "- **Quantitative tightening (QT)**: a central bank shrinking its bond holdings.")
ui.footer()
