"""
utils/render.py — shared evidence-first renderers.

Used by both the Analyze page and the Human Review page so a diagnosis always
looks the same, and so the three kinds of statement stay visually distinct:

    OBSERVED EVIDENCE   — lines taken from the supplied show output
    AI INFERENCE        — the model's conclusion, always labelled as such
    RECOMMENDATION      — proposed remediation, never applied automatically
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from utils.helpers import (
    STATUS_ICONS,
    cisco_block,
    confidence_badge,
    severity_badge,
)


def panel(label: str, value: str, accent: str = "#1a73e8") -> None:
    st.markdown(
        f"<div class='ns-panel' style='--ns-accent:{accent}'>"
        f"<h5>{label}</h5><p>{value}</p></div>",
        unsafe_allow_html=True,
    )


# ── Rule checker ─────────────────────────────────────────────────────────────

def render_rule_report(report: dict, raw_results: list[dict]) -> None:
    """Deterministic checker output. Runs and displays before any AI call."""
    counts = report.get("counts", {})
    status = report.get("status", "ok")

    c1, c2, c3 = st.columns(3)
    c1.metric("Checks passed", counts.get("pass", 0))
    c2.metric("Warnings", counts.get("warn", 0))
    c3.metric("Failures", counts.get("fail", 0))

    if status == "fail":
        st.error(
            f"{STATUS_ICONS['fail']} Deterministic checker found "
            f"{counts.get('fail', 0)} configuration fault(s).",
        )
    elif status == "warning":
        st.warning(
            f"{STATUS_ICONS['warn']} Deterministic checker raised "
            f"{counts.get('warn', 0)} warning(s) — evidence may be incomplete.",
        )
    else:
        st.success(f"{STATUS_ICONS['pass']} No deterministic faults detected.")

    for finding in report.get("findings", []):
        icon = "❌" if finding["severity"] == "high" else "⚠️"
        st.markdown(
            f"{icon} {severity_badge(finding['severity'])} "
            f"**`{finding['type']}`** — {finding['message']}<br>"
            f"<span style='opacity:.65;font-size:.82rem'>Evidence from: "
            f"<code>{finding['evidence']}</code></span>",
            unsafe_allow_html=True,
        )

    with st.expander("All deterministic checks (including passes)"):
        for r in raw_results:
            st.markdown(
                f"{STATUS_ICONS.get(r['status'], 'ℹ️')} **`{r['rule']}`** — {r['detail']}"
            )


# ── AI diagnosis ─────────────────────────────────────────────────────────────

def render_diagnosis(diag: dict, title: str = "AI NETWORK DIAGNOSIS",
                     show_model: bool = True) -> None:
    """Evidence-first layout: inference, then evidence, then recommendation."""
    st.markdown(f"### {title}")
    if show_model and diag.get("model"):
        st.caption(f"AI Provider: Groq · Model: `{diag['model']}`")

    st.markdown(
        f"{confidence_badge(diag.get('confidence'))} &nbsp; "
        f"{severity_badge(diag.get('severity'))}",
        unsafe_allow_html=True,
    )
    st.write("")

    panel("Root cause (AI inference)", diag.get("root_cause") or "—", "#1a73e8")

    c1, c2 = st.columns(2)
    with c1:
        panel("OSI layer", diag.get("osi_layer") or "Unknown", "#7b1fa2")
    with c2:
        panel("Networking concept", diag.get("concept") or "—", "#00796b")

    st.markdown("##### Evidence — observed in the supplied output")
    evidence = diag.get("evidence") or []
    if evidence:
        for item in evidence:
            st.markdown(f"- ✓ {item}")
    else:
        st.caption("The AI cited no specific evidence — treat this diagnosis with caution.")

    st.markdown("##### Next command — run this to confirm")
    cisco_block(diag.get("next_command") or "—")

    st.markdown("##### Recommended fix — proposal only, not applied")
    steps = diag.get("fix_steps") or []
    if steps:
        for i, step in enumerate(steps, 1):
            st.markdown(f"{i}. {step}")
    else:
        st.caption("No remediation steps were returned.")

    st.info(
        "These steps are a recommendation. NetSage AI does not execute Cisco "
        "commands or modify any network. A human engineer must review and apply them.",
        icon="🛡",
    )


# ── AI vs rule checker ───────────────────────────────────────────────────────

def render_comparison(summary: dict) -> None:
    """Phase 12 conflict banner — stored on the diagnosis for dashboard metrics."""
    st.markdown("### AI vs deterministic checker")
    if summary["conflict"]:
        st.error("⚠️ **DIAGNOSIS CONFLICT** — human review is required.")
        c1, c2 = st.columns(2)
        with c1:
            panel("AI diagnosis", summary["ai_root_cause"] or "—", "#d93025")
        with c2:
            findings = summary["checker_findings"] or ["—"]
            panel("Deterministic checker", "<br>".join(findings), "#e8710a")
        st.caption(
            "The two sources disagree. The deterministic checker is fixed logic over "
            "the supplied output; the AI answer is an inference. Resolve on the Human "
            "Review page."
        )
    else:
        st.success("✓ AI and rule checker agree")
        if summary["checker_findings"]:
            st.caption(
                "Both point at: " + "; ".join(summary["checker_rules"])
            )
        else:
            st.caption(
                "The checker found no hard failures, so there is nothing to contradict "
                "the AI diagnosis. Agreement here is weak evidence — confirm with the "
                "recommended next command."
            )


def render_human_correction(review: dict) -> None:
    """Show the human record beside the AI record; the AI row is never altered."""
    st.markdown("### Human review record")
    decision = (review.get("decision") or "").lower()
    label = {"accept": ("✓ ACCEPTED", "#1e8e3e"),
             "edit": ("✎ EDITED", "#e8710a"),
             "reject": ("✕ REJECTED", "#d93025")}.get(decision, ("—", "#5f6368"))
    panel("Decision", label[0], label[1])

    if review.get("reviewer"):
        st.caption(f"Reviewer: {review['reviewer']}")

    if decision != "accept":
        if review.get("human_root_cause"):
            panel("Corrected root cause", review["human_root_cause"], "#1e8e3e")
        if review.get("human_osi_layer"):
            st.markdown(f"**Corrected OSI layer:** {review['human_osi_layer']}")
        if review.get("human_evidence"):
            st.markdown("**Corrected evidence**")
            for e in review["human_evidence"]:
                st.markdown(f"- ✓ {e}")
        if review.get("human_next_command"):
            st.markdown("**Corrected next command**")
            cisco_block(review["human_next_command"])
        if review.get("human_fix_steps"):
            st.markdown("**Corrected fix steps**")
            for i, s in enumerate(review["human_fix_steps"], 1):
                st.markdown(f"{i}. {s}")
        if review.get("human_correction"):
            st.markdown(f"**Correction notes:** {review['human_correction']}")
        if review.get("reason"):
            st.markdown(f"**Why the AI was wrong:** {review['reason']}")
