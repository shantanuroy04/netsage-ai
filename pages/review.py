"""
pages/review.py — 👨‍💻 Human Review.

Every AI diagnosis needs a human decision: Accept, Edit or Reject. The AI record
is never overwritten — corrections are stored alongside it so the responsible-AI
log can compare what the AI said with what the engineer concluded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

import config
from database import db
from utils.helpers import (
    DECISION_LABELS,
    LAST_DIAGNOSIS_KEY,
    cisco_block,
    numbered,
    page_header,
    parse_lines,
    truncate,
)
from utils.render import render_diagnosis, render_human_correction

page_header("👨‍💻", "Human Review",
            "Mandatory oversight. No fix is ever applied by NetSage AI — a human "
            "engineer decides what is correct.")

try:
    pending = db.get_unreviewed_diagnoses()
    all_diagnoses = db.get_all_diagnoses()
except Exception as exc:
    st.error(f"❌ Could not read diagnoses: {exc}")
    st.stop()

if not all_diagnoses:
    st.info("No diagnoses to review yet. Run one from the Analyze Network page.", icon="ℹ️")
    st.page_link("pages/analyze.py", label="Go to Analyze Network", icon="🔍")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Awaiting review", len(pending))
c2.metric("Reviewed", len(all_diagnoses) - len(pending))
c3.metric("Total diagnoses", len(all_diagnoses))

tab_pending, tab_history = st.tabs(
    [f"Pending ({len(pending)})", f"Review history ({len(all_diagnoses) - len(pending)})"]
)

# ── Pending queue ────────────────────────────────────────────────────────────
with tab_pending:
    if not pending:
        st.success("Nothing awaiting review — every diagnosis has a human decision.",
                   icon="✅")
    else:
        last_id = st.session_state.get(LAST_DIAGNOSIS_KEY)
        ids = [d["id"] for d in pending]
        default_index = ids.index(last_id) if last_id in ids else 0

        chosen = st.selectbox(
            "Diagnosis to review",
            ids,
            index=default_index,
            format_func=lambda i: (
                f"#{i} — {truncate(next(d['root_cause'] or '' for d in pending if d['id'] == i), 70)}"
            ),
        )
        diag = next(d for d in pending if d["id"] == chosen)

        if diag.get("ai_conflict"):
            st.error(
                "⚠️ **DIAGNOSIS CONFLICT** — the AI and the deterministic checker "
                "disagreed on this case. Read both before deciding.",
            )

        with st.expander("Original evidence submitted", expanded=False):
            st.markdown(f"**Category:** {diag.get('category') or '—'}  ·  "
                        f"**Dataset case:** {diag.get('case_ref') or '—'}")
            st.markdown(f"**Symptom:** {diag.get('symptom')}")
            st.markdown("**Topology notes**")
            cisco_block(diag.get("topology") or "")
            st.markdown("**Show command output**")
            cisco_block(diag.get("show_output") or "")

        with st.expander("Deterministic checker findings", expanded=True):
            failures = [r for r in diag.get("rule_results", [])
                        if r.get("status") in ("warn", "fail")]
            if failures:
                for r in failures:
                    icon = "❌" if r["status"] == "fail" else "⚠️"
                    st.markdown(f"{icon} **`{r['rule']}`** — {r['detail']}")
            else:
                st.caption("The checker reported no warnings or failures for this case.")

        st.divider()
        render_diagnosis(diag)
        st.divider()

        st.markdown("### Your decision")
        decision_label = st.radio(
            "Decision",
            ["✓ ACCEPT", "✎ EDIT", "✕ REJECT"],
            horizontal=True,
            captions=[
                "The AI diagnosis is correct as written.",
                "Mostly right, but fields need correcting.",
                "Wrong — record the correct diagnosis instead.",
            ],
        )
        decision = {"✓ ACCEPT": "accept", "✎ EDIT": "edit", "✕ REJECT": "reject"}[decision_label]

        with st.form(f"review_form_{chosen}", clear_on_submit=False):
            reviewer = st.text_input("Reviewer name", placeholder="e.g. N. Engineer")

            human = {}
            reason = ""
            correction = ""

            if decision == "accept":
                st.success("Accepting stores the AI diagnosis unchanged as the agreed "
                           "outcome. Nothing is applied to any device.", icon="✅")
            else:
                if decision == "edit":
                    st.caption("Adjust only what is wrong. Blank fields keep the AI value.")
                else:
                    st.caption("Record the correct diagnosis. The AI's original output "
                               "stays stored for responsible-AI analysis.")

                e1, e2 = st.columns(2)
                human["human_root_cause"] = e1.text_area(
                    "Correct root cause", value=diag.get("root_cause") or "", height=110)
                human["human_osi_layer"] = e2.text_input(
                    "Correct OSI layer", value=diag.get("osi_layer") or "")

                e3, e4 = st.columns(2)
                human["human_confidence"] = e3.selectbox(
                    "Corrected confidence", ["Low", "Medium", "High"],
                    index=["Low", "Medium", "High"].index(diag.get("confidence") or "Low")
                    if (diag.get("confidence") or "Low") in ["Low", "Medium", "High"] else 0)
                human["human_severity"] = e4.selectbox(
                    "Corrected severity", config.SEVERITIES,
                    index=config.SEVERITIES.index(diag.get("severity"))
                    if diag.get("severity") in config.SEVERITIES else 1)

                human["human_evidence"] = parse_lines(st.text_area(
                    "Correct evidence (one per line)",
                    value="\n".join(diag.get("evidence") or []), height=110))
                human["human_next_command"] = st.text_input(
                    "Correct next command", value=diag.get("next_command") or "")
                human["human_fix_steps"] = parse_lines(st.text_area(
                    "Correct fix steps (one per line)",
                    value=numbered(diag.get("fix_steps") or []), height=130))

                correction = st.text_area(
                    "Correction notes — what the AI got wrong", height=90,
                    placeholder="e.g. 'show interfaces trunk' shows VLAN 30 excluded; "
                                "the ACL was not involved.")
                reason = st.text_area(
                    "Reason for the correction (recorded in the responsible-AI log)",
                    height=80,
                    placeholder="e.g. AI ignored the deterministic checker's trunk finding.")

            st.markdown("**Verification (optional)**")
            v1, v2, v3 = st.columns(3)
            verified_before = v1.selectbox("Verified before fix", ["", "pass", "fail"])
            fix_applied = v2.text_input("Fix actually applied", placeholder="optional")
            verified_after = v3.selectbox("Verified after fix", ["", "pass", "fail"])

            submitted = st.form_submit_button(
                f"Submit review — {decision.upper()}", type="primary",
                width="stretch")

        if submitted:
            if decision != "accept" and not (human.get("human_root_cause") or "").strip():
                st.error("⚠️ A corrected root cause is required for an EDIT or REJECT.")
            elif decision != "accept" and not reason.strip():
                st.error("⚠️ Give a reason — the responsible-AI log depends on it.")
            else:
                record = {
                    "diagnosis_id": chosen,
                    "decision": decision,
                    "human_correction": correction or None,
                    "reason": reason or None,
                    "reviewer": reviewer.strip() or "Unnamed reviewer",
                    "verified_before": verified_before or None,
                    "fix_applied": fix_applied.strip() or None,
                    "verified_after": verified_after or None,
                    **({k: v for k, v in human.items()} if decision != "accept" else {
                        "human_root_cause": diag.get("root_cause"),
                        "human_osi_layer": diag.get("osi_layer"),
                    }),
                }
                try:
                    db.insert_review(record)
                except Exception as exc:
                    st.error(f"❌ Could not save the review: {exc}")
                else:
                    st.session_state.pop(LAST_DIAGNOSIS_KEY, None)
                    st.success(f"Review submitted — {decision.upper()}.", icon="✅")
                    st.rerun()

# ── History ──────────────────────────────────────────────────────────────────
with tab_history:
    reviewed = [d for d in all_diagnoses if d.get("decision")]
    if not reviewed:
        st.info("No reviews recorded yet.", icon="ℹ️")
    else:
        st.dataframe(
            [
                {
                    "ID": d["id"],
                    "Case": d.get("case_ref") or "—",
                    "Category": d.get("category") or "—",
                    "AI root cause": truncate(d.get("root_cause") or "", 70),
                    "Decision": DECISION_LABELS.get(d["decision"], d["decision"]),
                    "Conflict": "⚠️" if d.get("ai_conflict") else "",
                    "Reviewed": d.get("reviewed_at"),
                }
                for d in reviewed
            ],
            width="stretch",
            hide_index=True,
        )

        pick = st.selectbox("Inspect a reviewed diagnosis",
                            [d["id"] for d in reviewed],
                            format_func=lambda i: f"#{i}")
        detail = db.get_diagnosis(pick)
        review = db.get_review_for_diagnosis(pick)
        if detail:
            left, right = st.columns(2)
            with left:
                render_diagnosis(detail, title="AI diagnosis (original, unaltered)")
            with right:
                if review:
                    render_human_correction(review)
