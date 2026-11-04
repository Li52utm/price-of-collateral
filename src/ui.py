"""Shared helpers for the Streamlit dashboard: theme, page furniture, formatting.

This module only caches, formats and plots. Every model lives in the other src
modules; every verdict sentence lives in src/wording.py. Adapted from the design
system of the KO/PEP project (same tokens, fonts and components), with a new
palette for currencies and collateral countries.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
REPO_URL = "https://github.com/labeebbhat/price-of-collateral"

# --------------------------------------------------------------------------- #
# Theme tokens: the only place colours and fonts are defined.
# .streamlit/config.toml repeats the colours because Streamlit reads it before
# any Python runs; keep the two in step.
# --------------------------------------------------------------------------- #
COLORS = {
    "paper": "#F6F7F9",    # page background
    "surface": "#FFFFFF",  # sidebar, chart hover labels
    "ink": "#15213B",      # text and the main series in a chart
    "slate": "#6A7385",    # muted text, secondary series
    "mist": "#B4BAC6",     # background series
    "rule": "#DDE1E8",     # thin borders
    "gain": "#1E8A6E",     # favourable outcome
    "loss": "#8E2C3A",     # unfavourable outcome
    "amber": "#B7791F",    # warnings, stressed regimes
    "amber_light": "#DDB874",
}

# Currencies and collateral countries. Okabe-Ito based (colour-blind safe); the three
# currencies and the four main collateral countries are mutually distinct, and each
# colour is used ONLY for its own series.
CURRENCY_COLORS = {"EUR": "#0072B2", "USD": "#009E73", "JPY": "#D55E00"}
COUNTRY_COLORS = {
    "DE": "#15213B",   # Bund: ink, the reference everything is measured against
    "FR": "#56B4E9",   # sky blue
    "IT": "#E69F00",   # orange
    "ES": "#CC79A7",   # reddish purple
    "PT": "#8C6D31",
    "BE": "#7F7F7F",
    "NL": "#A6761D",
    "AT": "#666666",
    "GR": "#9E3D22",
    "IE": "#2F7F5F",
    "FI": "#4A6FA5",
}
HEADING_FONT = "'Libre Caslon Text', Georgia, serif"
BODY_FONT = "'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif"
GRID_COLOR = "rgba(106, 115, 133, 0.16)"


def ref_line(color: str = COLORS["slate"], dash: str | None = None, width: float = 1) -> dict:
    """Line style for reference lines (zero, policy rates, thresholds)."""
    return dict(color=color, dash=dash, width=width)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#0072B2', 0.2 -> 'rgba(0, 114, 178, 0.2)' (for interval bands)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


# --------------------------------------------------------------------------- #
# Plotly template
# --------------------------------------------------------------------------- #
_AXIS = dict(gridcolor=GRID_COLOR, linecolor=COLORS["rule"], zeroline=False,
             tickfont=dict(color=COLORS["slate"]), title=dict(font=dict(color=COLORS["slate"])))
pio.templates["collateral"] = go.layout.Template(layout=dict(
    font=dict(family=BODY_FONT, size=12, color=COLORS["ink"]),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    colorway=[CURRENCY_COLORS["EUR"], CURRENCY_COLORS["USD"], CURRENCY_COLORS["JPY"], COLORS["ink"], COLORS["slate"]],
    xaxis=_AXIS,
    yaxis=_AXIS,
    hoverlabel=dict(bgcolor=COLORS["surface"], bordercolor=COLORS["rule"],
                    font=dict(family=BODY_FONT, color=COLORS["ink"])),
))


def style_figure(fig: go.Figure, title: str | None = None, height: int = 380) -> go.Figure:
    """Apply the "collateral" template plus title, legend and margins to any figure."""
    fig.update_layout(
        template="collateral",
        title=dict(text=title, x=0, xanchor="left", font=dict(family=BODY_FONT, size=15)) if title else None,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=BODY_FONT, size=12, color=COLORS["ink"]),
        margin=dict(l=8, r=8, t=78 if title else 40, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=COLORS["slate"]), bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=COLORS["surface"], bordercolor=COLORS["rule"]),
    )
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


# --------------------------------------------------------------------------- #
# As-of date and source lines
# --------------------------------------------------------------------------- #
MANIFEST_PATH = RESULTS_DIR / "snapshots" / "manifest.json"
STALE_DAYS = 7  # calendar days after which the snapshot is flagged as possibly stale


def load_manifest() -> dict | None:
    """results/snapshots/manifest.json (written by the refresh), or None if missing."""
    if not MANIFEST_PATH.exists():
        return None
    return _read_json(str(MANIFEST_PATH), MANIFEST_PATH.stat().st_mtime)


def data_as_of() -> pd.Timestamp | None:
    """The as-of date of the committed snapshots (latest common daily observation)."""
    manifest = load_manifest()
    if not manifest or not manifest.get("as_of"):
        return None
    return pd.Timestamp(manifest["as_of"])


def is_stale(as_of: pd.Timestamp | None, today: pd.Timestamp, max_days: int = STALE_DAYS) -> bool:
    """True when the snapshot is more than `max_days` calendar days old (or missing)."""
    if as_of is None:
        return True
    return (today.normalize() - as_of.normalize()).days > max_days


def day(ts: pd.Timestamp | None, long_month: bool = True) -> str:
    """'31 December 2026' (or '31 Dec 2026'); 'n/a' when missing."""
    if ts is None or pd.isna(ts):
        return NA
    ts = pd.Timestamp(ts)
    return f"{ts.day} {ts:%B %Y}" if long_month else f"{ts.day} {ts:%b %Y}"


DEFAULT_SOURCES = "ECB Data Portal, New York Fed, FRED, Bank of Japan"


def source_line(sources: str = DEFAULT_SOURCES) -> str:
    """The source line under every chart."""
    return f"Source: {sources}; project calculations. Data as of {day(data_as_of())}."


def show_chart(fig: go.Figure, title: str | None = None, height: int = 380, sources: str = DEFAULT_SOURCES,
               container=None) -> None:
    """Title as HTML (wraps on phones), the styled figure, then the source line."""
    target = container if container is not None else st
    if title:
        target.html(f'<div class="chart-title">{html.escape(title)}</div>')
    target.plotly_chart(style_figure(fig, height=height), width="stretch")
    target.caption(source_line(sources))


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
NA = "n/a"


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def fmt_bp(x: float, decimals: int = 1, sign: bool = False) -> str:
    """Basis points: 3.2 -> '3.2 bp' (sign=True -> '+3.2 bp')."""
    if _missing(x):
        return NA
    return f"{x:+.{decimals}f} bp" if sign else f"{x:.{decimals}f} bp"


def fmt_pct(x: float, decimals: int = 1, sign: bool = False) -> str:
    if _missing(x):
        return NA
    return f"{x:+.{decimals}%}" if sign else f"{x:.{decimals}%}"


def fmt_rate(x: float, decimals: int = 2) -> str:
    """A rate already in percent: 1.93 -> '1.93%'."""
    if _missing(x):
        return NA
    return f"{x:.{decimals}f}%"


def fmt_num(x: float, decimals: int = 2) -> str:
    if _missing(x):
        return NA
    return f"{x:.{decimals}f}"


def escape_dollars(text: str) -> str:
    """Escape "$" for st.markdown, which reads text between two "$" as LaTeX."""
    return text.replace("$", "\\$")


def md(text: str) -> None:
    st.markdown(escape_dollars(text))


# --------------------------------------------------------------------------- #
# Page furniture
# --------------------------------------------------------------------------- #
SERIES_TITLE = "The Price of Collateral"

CHAPTERS = {
    "story": dict(numeral="I", title="The Story",
                  subtitle="What is repo, and why does the bond you hand over matter?"),
    "corridors": dict(numeral="II", title="Three Corridors",
                      subtitle="The ECB, the Fed and the Bank of Japan, and what happens as balance sheets shrink"),
    "collateral": dict(numeral="III", title="The Price of Collateral",
                       subtitle="Italian and French against German collateral: credit risk or scarcity?"),
    "france": dict(numeral="IV", title="Italy Then, France Now",
                   subtitle="Will French OATs bounce back, and what would it take?"),
    "calendar": dict(numeral="V", title="The Calendar",
                     subtitle="Why euro and dollar year-ends behave differently, and whether spikes can be forecast"),
    "japan": dict(numeral="VI", title="Japan",
                  subtitle="Does Japanese money-market pricing follow the BoJ out of negative rates?"),
    "desk_note": dict(numeral="VII", title="The Year-End 2026 Desk Note",
                      subtitle="Euro and dollar funding over 31 December 2026, published before year-end"),
}

QUESTIONS = {
    "story": "What is repo, and why does the bond you hand over matter?",
    "corridors": "Do the ECB, the Fed and the BoJ keep overnight rates where they want them?",
    "collateral": "Is the extra cost of Italian and French collateral about credit risk or scarcity?",
    "france": "Will French OATs bounce back, and what would it take?",
    "calendar": "Can year-end funding spikes be forecast, and why do euro and dollar year-ends differ?",
    "japan": "Does Japanese overnight pricing follow the BoJ out of negative rates?",
    "desk_note": "How should a client fund across the 2026 year-end?",
}

_CSS = f"""
<style>
:root {{
  --paper: {COLORS["paper"]}; --surface: {COLORS["surface"]}; --ink: {COLORS["ink"]};
  --slate: {COLORS["slate"]}; --rule: {COLORS["rule"]}; --amber: {COLORS["amber"]};
  --loss: {COLORS["loss"]};
}}
[data-testid="stMainBlockContainer"] {{ max-width: 1100px; padding: 2.5rem 1.5rem 5rem 1.5rem; }}
[data-testid="stMain"] h2 {{ margin-top: 2.75rem; }}
[data-testid="stMain"] h3 {{ margin-top: 1.5rem; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"] {{ max-width: 72ch; }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ line-height: 1.6; }}
h1, h2, h3, h4 {{ font-family: {HEADING_FONT}; color: var(--ink); text-transform: none; letter-spacing: 0; }}
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], [data-testid="stTable"],
[data-testid="stDataFrame"], .stPlotlyChart {{ font-variant-numeric: tabular-nums; }}
footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stMetric"] {{
  background: transparent; border: none; box-shadow: none; border-radius: 0;
  border-top: 1px solid var(--ink); padding: 0.6rem 0 0 0;
}}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{ color: var(--slate); font-size: 0.85rem; }}
[data-testid="stMetricValue"] {{ font-family: {BODY_FONT}; font-weight: 400; color: var(--ink); }}
[class*="st-key-kpis-"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; row-gap: 1.25rem; }}
[class*="st-key-kpis-"] [data-testid="stColumn"] {{ flex: 1 1 10.5rem !important; min-width: 10.5rem !important; }}
[data-testid="stSidebar"] {{ background: var(--surface); border-right: 1px solid var(--rule); }}
.chapter-kicker {{ font-family: {BODY_FONT}; color: var(--slate); font-size: 0.85rem; margin-bottom: 0.75rem; }}
.chapter {{ display: flex; flex-wrap: wrap; align-items: baseline; column-gap: 1.25rem; }}
.chapter-numeral {{ font-family: {HEADING_FONT}; color: var(--slate); font-size: 4.5rem; line-height: 1; }}
.chapter-title {{ font-family: {HEADING_FONT}; color: var(--ink); font-size: 2.6rem; line-height: 1.1; }}
.chapter-subtitle {{ font-family: {BODY_FONT}; color: var(--slate); font-size: 1.05rem; margin: 0.6rem 0 0 0; max-width: 72ch; }}
.chapter-rule {{ border: none; border-top: 1px solid var(--rule); margin: 1.5rem 0 1rem 0; }}
@media (max-width: 640px) {{
  .chapter-numeral {{ font-size: 3.25rem; }}
  .chapter-title {{ font-size: 2rem; }}
  [data-testid="stMainBlockContainer"] {{ padding: 1.5rem 1rem 4rem 1rem; }}
  [data-testid="stMetricValue"] {{ font-size: 1.45rem !important; }}
}}
[class*="st-key-note-"] {{ margin: 0.5rem 0 1rem 0; }}
[class*="st-key-note-"] [data-testid="stMarkdownContainer"] {{ border-left: 2px solid var(--slate); padding: 0.15rem 0 0.15rem 1rem; }}
[class*="st-key-note-warning"] [data-testid="stMarkdownContainer"] {{ border-left-color: var(--amber); }}
[class*="st-key-note-error"] [data-testid="stMarkdownContainer"] {{ border-left-color: var(--loss); }}
[class*="st-key-note-"] p {{ color: var(--ink); margin-bottom: 0; }}
[class*="st-key-answer-"] {{
  border-top: 2px solid var(--ink); border-bottom: 1px solid var(--rule);
  padding: 0.75rem 0 0.5rem 0; margin: 0.5rem 0 1.5rem 0;
}}
[class*="st-key-answer-"] p {{ color: var(--ink); margin-bottom: 0.35rem; max-width: 72ch; }}
.section-heading {{
  font-family: {HEADING_FONT}; font-weight: 400; font-size: 1.65rem; color: var(--ink);
  margin: 3.5rem 0 0.25rem 0; padding: 0;
}}
.section-numeral {{ color: var(--slate); margin-right: 0.35rem; }}
.desk-title {{ font-family: {HEADING_FONT}; font-size: 1.65rem; color: var(--ink); margin: 0; }}
.desk-meta {{ font-family: {BODY_FONT}; color: var(--slate); font-size: 0.9rem; margin: 0.2rem 0 0 0; }}
.chart-title {{ font-family: {BODY_FONT}; font-weight: 500; font-size: 0.95rem; color: var(--ink); margin: 0.75rem 0 -0.25rem 0; }}
</style>
"""


def apply_theme() -> None:
    """Inject the dashboard CSS. Call at the top of every page."""
    st.html(_CSS)


def chapter_heading(numeral: str, title: str, subtitle: str) -> None:
    """Large Roman numeral, title, one-line subtitle, a thin rule, then the as-of line."""
    st.html(
        f'<div class="chapter-kicker">{SERIES_TITLE}</div>'
        f'<div class="chapter"><div class="chapter-numeral">{numeral}</div>'
        f'<div class="chapter-title">{html.escape(title)}</div></div>'
        f'<p class="chapter-subtitle">{html.escape(subtitle)}</p>'
        '<hr class="chapter-rule">'
    )
    data_as_of_note()


def data_as_of_note() -> None:
    """One as-of line under every chapter heading, and a warning if the data is old."""
    last = data_as_of()
    if last is None:
        note("No data snapshot found. Run `scripts/refresh_snapshots.py` to create one.", "warning")
        return
    st.caption(f"Data as of {day(last)}, refreshed automatically each weekday.")
    today = pd.Timestamp.now(tz="Europe/Berlin").tz_localize(None)
    if is_stale(last, today):
        note(f"The data may be stale: the latest observation is {(today.normalize() - last).days} days old. "
             "The scheduled refresh may have failed; see the repository's Actions tab.", "warning")


NOTE_KINDS = ("info", "warning", "error")


def _key(prefix: str, *parts: object) -> str:
    """A stable element key from its content (Streamlit needs unique keys per run)."""
    digest = hashlib.md5(repr(parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def note(text: str, kind: str = "info", container=None) -> None:
    """A quiet note: markdown beside a thin left rule (slate, amber or loss red)."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"kind must be one of {NOTE_KINDS}, got {kind!r}")
    target = container if container is not None else st
    with target.container(key=_key(f"note-{kind}", text)):
        st.markdown(escape_dollars(text))


def answer_box(question: str, answer: str, explanation: str = "",
               labels: tuple[str, str] = ("The question", "The answer")) -> None:
    """A boxed question and its generated answer (one bold phrase, then the reason)."""
    with st.container(key=_key("answer", question, answer)):
        st.markdown(escape_dollars(f"**{labels[0]}:** {question}"))
        st.markdown(escape_dollars(f"**{labels[1]}: {answer}.** {explanation}".rstrip()))


def verdict_box(label: str, verdict: str, sentence: str) -> None:
    """A boxed one-line verdict, e.g. 'Would I advise ...? Partly.' plus its generated reason."""
    with st.container(key=_key("answer", label, verdict)):
        separator = "" if label.endswith("?") else ":"
        st.markdown(escape_dollars(f"**{label}{separator} {verdict}.** {sentence}"))


def kpi_row(items: list[tuple]) -> None:
    """A row of metric cards. Each item is (label, value, delta or None[, sentence])."""
    with st.container(key=_key("kpis", items)):
        for column, item in zip(st.columns(len(items)), items):
            label, value, delta = item[:3]
            column.metric(label, value, delta)
            if len(item) > 3:
                column.caption(escape_dollars(item[3]))


def section_heading(numeral: str, title: str) -> None:
    """A quiet numbered section heading, e.g. 'iv. The year-end turn'."""
    number = f'<span class="section-numeral">{numeral}.</span> ' if numeral else ""
    st.html(f'<h2 class="section-heading">{number}{html.escape(title)}</h2>')


VALIDATION_PATH = RESULTS_DIR / "data_validation.json"


def load_validation() -> dict | None:
    """results/data_validation.json (written by the refresh), or None if missing."""
    if not VALIDATION_PATH.exists():
        return None
    return _read_json(str(VALIDATION_PATH), VALIDATION_PATH.stat().st_mtime)


def validation_summary_line(rep: dict | None) -> str:
    """'Data checks: 12 passed, 2 warnings, as of 3 November 2026' (failures named if any)."""
    if not rep:
        return "Data checks: not run."
    c = rep["counts"]
    failed = f", {c['FAIL']} failed" if c.get("FAIL") else ""
    plural = "warning" if c.get("WARN", 0) == 1 else "warnings"
    return f"Data checks: {c.get('PASS', 0)} passed, {c.get('WARN', 0)} {plural}{failed}, as of {day(pd.Timestamp(rep['as_of']))}."


def footer(lead: str = "Educational project. Not investment advice.") -> None:
    st.divider()
    st.caption(f"{lead} Data: ECB Data Portal, Federal Reserve Bank of New York, FRED (St. Louis Fed), "
               f"Bank of Japan. Source code: [GitHub]({REPO_URL}).")
    st.caption(validation_summary_line(load_validation()))


@st.cache_data(show_spinner=False)
def _read_json(path: str, stamp: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def _read_csv(path: str, stamp: float) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)


def read_result_csv(name: str) -> pd.DataFrame | None:
    """A CSV under results/ (cached on its modification time), or None if missing."""
    path = RESULTS_DIR / name
    if not path.exists():
        return None
    return _read_csv(str(path), path.stat().st_mtime)


def read_result_json(name: str) -> dict | None:
    """A JSON file under results/ (cached on its modification time), or None if missing."""
    path = RESULTS_DIR / name
    if not path.exists():
        return None
    return _read_json(str(path), path.stat().st_mtime)
