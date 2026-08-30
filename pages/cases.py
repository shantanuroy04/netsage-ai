"""
pages/cases.py — 📁 Troubleshooting Cases.

Browses data/cases.csv (loaded into SQLite at startup). "Load into Analyze"
hands a case to the Analyze page via session state — the dataset is never
duplicated.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database import db
from utils.helpers import cisco_block, page_header, set_prefill, truncate

page_header("📁", "Troubleshooting Cases",
            "The Packet Tracer case dataset that backs NetSage AI. Load any case "
            "straight into the analyzer.")

try:
    cases = db.get_all_cases()
except Exception as exc:
    st.error(f"❌ Could not read the case dataset: {exc}")
    st.stop()

if not cases:
    st.warning(
        "No cases found. Check that `data/cases.csv` exists, then restart the app.",
        icon="⚠️",
    )
    st.stop()


def options(field: str) -> list[str]:
    return sorted({(c.get(field) or "").strip() for c in cases if c.get(field)})


f1, f2, f3, f4 = st.columns(4)
sel_category = f1.multiselect("Category", options("category"))
sel_severity = f2.multiselect("Severity", options("severity"))
sel_osi = f3.multiselect("OSI Layer", options("osi_layer"))
sel_concept = f4.multiselect("Concept", options("concept"))
search = st.text_input("Search symptom or expected fault", placeholder="e.g. trunk, gateway, dhcp")

filtered = [
    c for c in cases
    if (not sel_category or c["category"] in sel_category)
    and (not sel_severity or c["severity"] in sel_severity)
    and (not sel_osi or c["osi_layer"] in sel_osi)
    and (not sel_concept or c["concept"] in sel_concept)
    and (not search or search.lower() in
         f"{c['symptom']} {c['expected_fault']} {c['concept']}".lower())
]

st.caption(f"Showing **{len(filtered)}** of **{len(cases)}** cases.")

if not filtered:
    st.info("No cases match these filters.", icon="ℹ️")
    st.stop()

st.dataframe(
    [
        {
            "Case ID": c["case_id"],
            "Category": c["category"],
            "Symptom": truncate(c["symptom"], 80),
            "Expected fault": truncate(c["expected_fault"], 70),
            "OSI layer": c["osi_layer"],
            "Severity": c["severity"],
            "Concept": c["concept"],
        }
        for c in filtered
    ],
    width="stretch",
    hide_index=True,
)

st.divider()
st.markdown("### Case detail")

selected_id = st.selectbox(
    "Select a case",
    [c["case_id"] for c in filtered],
    format_func=lambda cid: f"{cid} — {truncate(next(c['symptom'] for c in filtered if c['case_id'] == cid), 70)}",
)
case = next(c for c in filtered if c["case_id"] == selected_id)

m1, m2, m3 = st.columns(3)
m1.metric("Category", case["category"])
m2.metric("Severity", case["severity"])
m3.metric("OSI layer", case["osi_layer"])

st.markdown(f"**Symptom** — {case['symptom']}")
st.markdown(f"**Concept** — {case['concept']}")

with st.expander("Topology notes", expanded=True):
    cisco_block(case["topology"])
with st.expander("Show command output", expanded=True):
    cisco_block(case["show_output"])
with st.expander("Expected fault (dataset ground truth)"):
    st.warning(case["expected_fault"], icon="🎯")
    st.caption(
        "Ground truth from the dataset. It is shown to the AI only as 'known case "
        "information' when the case is loaded — it is not used to score the AI here."
    )

if st.button(f"🔍 Load case {case['case_id']} into Analyze Network",
             type="primary", width="stretch"):
    set_prefill(case)
    st.switch_page("pages/analyze.py")
