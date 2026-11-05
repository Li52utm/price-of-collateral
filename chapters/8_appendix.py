"""Appendix: robustness checks and every hypothesis test (raw and Holm-adjusted p-values)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402
import wording as w  # noqa: E402

ui.apply_theme()
ui.chapter_heading(**ui.APPENDIX)

res = ui.results()
rob = ui.read_result_json("robustness/table.json")
ui.section_heading("i", "Robustness checks")
if rob is None:
    ui.missing_results("robustness")
else:
    st.markdown("Each headline finding is re-derived under alternative specifications fixed in advance "
                "(docs/METHODOLOGY.md, U3), with everything else unchanged.")
    for key, s in rob["summary"].items():
        ui.md(f"**{key}.** {s['finding']}: {w.robustness_badge_text(s['holds'], s['n'], s['not_computable'])}.")
    rows = [{"Finding": r["finding"], "Alternative": r["spec"],
             "Conclusion holds": {True: "yes", False: "no", None: "not computable"}[r["holds"]],
             "Result": r["value"]} for r in rob["rows"]]
    ui.table(pd.DataFrame(rows))

ui.section_heading("ii", "Every hypothesis test")
tests = (res.get("tests") or {}).get("tests")
if not tests:
    ui.missing_results("hypothesis tests")
else:
    st.markdown("Holm's correction is applied within each family (docs/METHODOLOGY.md, U2). Every sentence in the "
                "dashboard that calls a result significant uses the adjusted p-value.")
    ui.table(pd.DataFrame([{"Family": t["family"], "Test": t["what"], "Tests in family": t["m"],
                            "p-value": None if t["p"] is None else round(t["p"], 4),
                            "Holm-adjusted p": None if t["p_holm"] is None else round(t["p_holm"], 4),
                            "Significant at 5% (adjusted)": "n/a" if t["p_holm"] is None
                            else ("yes" if t["p_holm"] < 0.05 else "no")} for t in tests]))
ui.footer()
