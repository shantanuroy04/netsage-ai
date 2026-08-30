"""
pages/responsible_ai.py — 🛡 Responsible AI.

The audit trail: how often the AI was right, how often a human corrected it, and
exactly what was wrong each time. Counts are read from the database — if there
are fewer than five real corrections, the page says so rather than inventing any.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database import db
from database.seed import SEED_REVIEWER
from utils.helpers import DECISION_LABELS, page_header, truncate
from utils.metrics import pct_label, responsible_ai_summary

page_header("🛡", "Responsible AI",
            "Human oversight, recorded. Every AI diagnosis a person changed is "
            "listed here with the reason.")

try:
    stats = db.get_stats()
    log = db.get_responsible_ai_log()
except Exception as exc:
    st.error(f"❌ Could not read the responsible-AI log: {exc}")
    st.stop()

summary = responsible_ai_summary(stats, log)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total AI diagnoses", summary["total_diagnoses"])
k2.metric("Accepted", summary["accepted"])
k3.metric("Edited", summary["edited"])
k4.metric("Rejected", summary["rejected"])

k5, k6, k7 = st.columns(3)
k5.metric("AI-human agreement", pct_label(summary["agreement_rate"], "Not enough data"))
k6.metric("Human correction rate", pct_label(summary["correction_rate"], "Not enough data"))
k7.metric("Documented corrections", summary["corrections"])

if summary["reviewed"] == 0:
    st.info("Not enough reviewed cases yet — rates appear once a human has "
            "reviewed at least one diagnosis.", icon="ℹ️")

if summary["target_met"]:
    st.success(
        f"✅ {summary['corrections']} corrections recorded — meets the "
        f"{summary['target']}-case responsible-AI requirement.",
    )
else:
    st.warning(
        f"⚠️ {summary['corrections']} correction(s) recorded — "
        f"{summary['shortfall']} more needed to reach the {summary['target']}-case "
        "requirement. Review more diagnoses on the Human Review page; nothing is "
        "generated to fill the gap.",
    )

st.divider()

st.markdown("### Cases where a human corrected the AI")
if not log:
    st.info("No corrections recorded yet.", icon="ℹ️")
    st.page_link("pages/review.py", label="Go to Human Review", icon="👨‍💻")
    st.stop()

seeded = [r for r in log if r.get("reviewer") == SEED_REVIEWER]
live = [r for r in log if r.get("reviewer") != SEED_REVIEWER]

if seeded:
    st.caption(
        f"{len(seeded)} of these are **pre-loaded demonstration records** carried over "
        f"from the original project (reviewer: “{SEED_REVIEWER}”), and {len(live)} "
        "come from live reviews in this app. Both are shown; the Source column "
        "distinguishes them."
    )


def rows(entries):
    return [
        {
            "Case ID": r.get("case_ref") or f"#{r['diagnosis_id']}",
            "AI Diagnosis": truncate(r.get("ai_diagnosis") or "", 80),
            "Human Diagnosis": truncate(r.get("human_diagnosis") or "", 80),
            "Why AI Was Wrong": truncate(r.get("reason") or "", 90),
            "Reviewer Decision": DECISION_LABELS.get(r.get("human_decision"),
                                                     r.get("human_decision") or "—"),
            "Source": "Pre-loaded" if r.get("reviewer") == SEED_REVIEWER else "Live review",
        }
        for r in entries
    ]


st.dataframe(rows(log), width="stretch", hide_index=True)

st.divider()
st.markdown("### Correction detail")
for r in log:
    header = (f"{r.get('case_ref') or '#' + str(r['diagnosis_id'])} · "
              f"{r.get('category') or '—'} · "
              f"{DECISION_LABELS.get(r.get('human_decision'), '')}")
    with st.expander(header):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**What the AI said**")
            st.error(r.get("ai_diagnosis") or "—")
            st.caption(f"OSI: {r.get('ai_osi_layer') or '—'} · "
                       f"Confidence: {r.get('ai_confidence') or '—'} · "
                       f"Model: {r.get('model') or '—'}")
        with c2:
            st.markdown("**What the engineer concluded**")
            st.success(r.get("human_diagnosis") or "—")
            st.caption(f"OSI: {r.get('human_osi_layer') or '—'} · "
                       f"Reviewer: {r.get('reviewer') or '—'}")
        if r.get("human_correction"):
            st.markdown(f"**Correction notes:** {r['human_correction']}")
        if r.get("reason"):
            st.markdown(f"**Why the AI was wrong:** {r['reason']}")
        st.caption(f"Reviewed at {r.get('reviewed_at')}")

st.divider()
st.markdown("### Operating principles")
st.markdown(
    """
- The AI **recommends**; it never applies a configuration change.
- NetSage AI does not execute Cisco commands and never connects to a device.
- A deterministic Python checker runs **before** the model on every case, and its
  findings are shown next to the AI's, including when they disagree.
- Every diagnosis requires a human decision before it counts as resolved.
- The original AI output is never overwritten — corrections are stored alongside it.
- API keys live in `.env` / Streamlit secrets and are never displayed or logged.
"""
)
