"""
pages/analyze.py — 🔍 Analyze Network.

Order of operations is deliberate and never changes:
    1. deterministic Python rule checker
    2. Groq AI diagnosis (given the checker findings as input)
    3. comparison of the two
    4. persist, then hand off to human review
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

import config
from ai.diagnosis import diagnose
from ai.groq_client import GroqError
from ai.schemas import DiagnosisParseError
from checker import analyze as run_checker, conflict_summary
from database import db
from utils.helpers import (
    LAST_DIAGNOSIS_KEY,
    page_header,
    pop_prefill,
    section,
)
from utils.render import render_comparison, render_diagnosis, render_rule_report

SHOW_COMMAND_HINT = """show vlan brief
show interfaces trunk
show ip route
show ip interface brief
show access-lists
show running-config
show ip dhcp binding"""

page_header(
    "🔍",
    "Analyze Network",
    "Paste Packet Tracer evidence. The deterministic checker runs first; the AI "
    "diagnoses second; a human decides last.",
)

prefill = pop_prefill()
if prefill:
    st.session_state["an_category"] = prefill.get("category", config.CATEGORIES[0])
    st.session_state["an_symptom"] = prefill.get("symptom", "")
    st.session_state["an_topology"] = prefill.get("topology", "")
    st.session_state["an_show"] = prefill.get("show_output", "")
    st.session_state["an_severity"] = prefill.get("severity", "Medium")
    st.session_state["an_case_ref"] = prefill.get("case_id", "")
    st.session_state["an_case_info"] = (
        f"Expected fault: {prefill.get('expected_fault', '')}\n"
        f"OSI layer: {prefill.get('osi_layer', '')}\n"
        f"Concept: {prefill.get('concept', '')}"
    )
    st.success(f"Loaded dataset case **{prefill.get('case_id')}** into the form.", icon="📁")

# ── Case information ─────────────────────────────────────────────────────────
section("Case information", "Classify the fault so the right rule sets run.")

col1, col2, col3 = st.columns([2, 2, 2])
with col1:
    category = st.selectbox(
        "Category", config.CATEGORIES,
        index=config.CATEGORIES.index(st.session_state.get("an_category", "VLAN"))
        if st.session_state.get("an_category") in config.CATEGORIES else 0,
        key="an_category",
    )
with col2:
    severity = st.selectbox(
        "Reported severity (optional)", config.SEVERITIES,
        index=config.SEVERITIES.index(st.session_state.get("an_severity", "Medium"))
        if st.session_state.get("an_severity") in config.SEVERITIES else 1,
        key="an_severity",
    )
with col3:
    case_ref = st.text_input(
        "Dataset case ID (optional)", key="an_case_ref",
        placeholder="e.g. 004",
        help="Set automatically when a case is loaded from the Cases page.",
    )

with st.expander("Client addressing (optional — enables the gateway-mismatch check)"):
    a1, a2, a3 = st.columns(3)
    pc_ip = a1.text_input("PC IP address", key="an_pc_ip", placeholder="192.168.10.10")
    pc_mask = a2.text_input("Subnet mask", key="an_pc_mask", placeholder="255.255.255.0")
    gateway = a3.text_input("Default gateway", key="an_gateway", placeholder="192.168.10.1")

# ── Evidence ─────────────────────────────────────────────────────────────────
section("Evidence", "Only what you paste here is analysed. Nothing is invented.")

tab_symptom, tab_topology, tab_output = st.tabs(
    ["Symptom", "Topology notes", "Show command output"]
)

with tab_symptom:
    symptom = st.text_area(
        "What is observed?", key="an_symptom", height=130,
        placeholder="PC gets an IP address but cannot reach the server.\nGateway ping works.",
    )
with tab_topology:
    topology = st.text_area(
        "Topology notes", key="an_topology", height=130,
        placeholder="PC1 -> Switch1 -> Router1 -> Server1\nPC1 belongs to VLAN 30.",
    )
with tab_output:
    show_output = st.text_area(
        "Paste Cisco / Packet Tracer show-command output", key="an_show", height=300,
        placeholder=SHOW_COMMAND_HINT,
    )
    st.caption("Useful commands: " + " · ".join(
        f"`{c}`" for c in SHOW_COMMAND_HINT.splitlines()))

case_information = st.session_state.get("an_case_info", "")

st.divider()
run = st.button("🔍 Analyze Network", type="primary", width="stretch")

# ── Run the pipeline ─────────────────────────────────────────────────────────
if run:
    if not (symptom or "").strip():
        st.error("⚠️ Enter a symptom description before running an analysis.")
        st.stop()

    extra = {"pc_ip": pc_ip, "pc_mask": pc_mask, "gateway": gateway}
    raw_results, report = run_checker(symptom, show_output, category, extra)

    st.session_state["an_results"] = {
        "raw_results": raw_results,
        "report": report,
        "inputs": {
            "symptom": symptom, "topology": topology, "show_output": show_output,
            "category": category, "severity": severity,
            "case_ref": case_ref or None, "case_information": case_information,
        },
        "diagnosis": None,
        "error": None,
        "diag_id": None,
    }

    if not (show_output or "").strip():
        st.warning(
            "No show-command output supplied — the deterministic checker has little to "
            "work with and the AI will be reasoning from the symptom alone.",
            icon="⚠️",
        )

    if not config.api_key_configured():
        st.session_state["an_results"]["error"] = (
            "⚠️ GROQ_API_KEY is not configured. Add it to `.env` or "
            "`.streamlit/secrets.toml`, then retry. Deterministic checker results "
            "below are still valid."
        )
    else:
        try:
            with st.spinner("Querying Groq for a structured diagnosis…"):
                diag = diagnose(
                    symptom=symptom, topology=topology, show_output=show_output,
                    category=category, rule_results=raw_results,
                    case_information=case_information,
                )
            summary = conflict_summary(raw_results, diag.get("root_cause", ""))
            record = {
                "case_ref": case_ref or None, "category": category,
                "symptom": symptom, "topology": topology, "show_output": show_output,
                **diag,
                "rule_results": raw_results,
                "ai_conflict": summary["conflict"],
            }
            diag_id = db.insert_diagnosis(record)
            st.session_state["an_results"].update(
                diagnosis=diag, summary=summary, diag_id=diag_id
            )
            st.session_state[LAST_DIAGNOSIS_KEY] = diag_id
        except ValueError as exc:
            st.session_state["an_results"]["error"] = f"⚠️ {exc}"
        except GroqError as exc:
            st.session_state["an_results"]["error"] = (
                f"❌ {exc}" + ("" if exc.retryable else " (not retryable until fixed)")
            )
        except DiagnosisParseError as exc:
            st.session_state["an_results"]["error"] = (
                f"❌ The AI response could not be parsed: {exc} "
                "Press **Analyze Network** again to retry."
            )
        except db.DatabaseError as exc:
            st.session_state["an_results"]["error"] = f"❌ Could not save the diagnosis: {exc}"

# ── Results ──────────────────────────────────────────────────────────────────
results = st.session_state.get("an_results")
if results:
    st.divider()
    st.markdown("## Analysis results")

    st.markdown("### Step 1 — Deterministic rule checker")
    st.caption("Fixed Python logic over the pasted output. Runs before the AI, always.")
    render_rule_report(results["report"], results["raw_results"])

    st.divider()
    st.markdown("### Step 2 — AI diagnosis")
    if results.get("error"):
        st.error(results["error"])
        st.caption(
            "The deterministic findings above are unaffected — they never depend on the AI."
        )
    elif results.get("diagnosis"):
        render_diagnosis(results["diagnosis"])
        st.divider()
        render_comparison(results["summary"])
        st.divider()
        st.success(
            f"Saved as diagnosis **#{results['diag_id']}** — awaiting human review.",
            icon="💾",
        )
        st.page_link("pages/review.py", label="Go to Human Review", icon="👨‍💻")
