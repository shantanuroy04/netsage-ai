"""
pages/dashboard.py — 📊 Dashboard.

Every figure on this page is computed from the SQLite rows. Where there is not
enough data, the page says so instead of showing a number.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go
import streamlit as st

from database import db
from utils.helpers import DECISION_LABELS, page_header
from utils.metrics import (
    agreement_rate,
    conflict_rate,
    correction_rate,
    distribution,
    pct_label,
)

PALETTE = ["#1a73e8", "#00897b", "#7b1fa2", "#e8710a", "#c62828",
           "#546e7a", "#2e7d32", "#5e35b1"]
SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]
SEVERITY_COLORS = {"Low": "#1a73e8", "Medium": "#e8710a",
                   "High": "#d93025", "Critical": "#7b1029"}

page_header("📊", "Dashboard",
            "Dataset coverage, AI behaviour, and human oversight — all derived "
            "from stored records.")


def _style(fig, height: int = 330):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _bar(pairs, title, color_map=None, order=None):
    if not pairs:
        st.caption(f"{title}: no data yet.")
        return
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    colors = ([color_map.get(l, "#1a73e8") for l in labels]
              if color_map else PALETTE * (len(labels) // len(PALETTE) + 1))
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors[: len(labels)],
                           text=values, textposition="outside"))
    fig.update_layout(title=title, yaxis_title="Cases", xaxis_title="")
    if order:
        fig.update_xaxes(categoryorder="array", categoryarray=order)
    st.plotly_chart(_style(fig), width="stretch")


def _donut(pairs, title, color_map=None):
    if not pairs:
        st.caption(f"{title}: no data yet.")
        return
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    colors = ([color_map.get(l, "#1a73e8") for l in labels]
              if color_map else PALETTE * (len(labels) // len(PALETTE) + 1))
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55,
                           marker_colors=colors[: len(labels)]))
    fig.update_layout(title=title, showlegend=True,
                      legend=dict(orientation="h", y=-0.12))
    fig.update_traces(textinfo="value+percent")
    st.plotly_chart(_style(fig, 360), width="stretch")


def _gauge(value: float, title: str, good_high: bool = True):
    color = "#1e8e3e" if (value >= 60) == good_high else "#d93025"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%"},
        title={"text": title, "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [{"range": [0, 100], "color": "rgba(128,128,128,0.12)"}],
        },
    ))
    st.plotly_chart(_style(fig, 260), width="stretch")


try:
    stats = db.get_stats()
except Exception as exc:
    st.error(f"❌ Could not read the database: {exc}")
    st.stop()

# ── KPI row ──────────────────────────────────────────────────────────────────
agreement = agreement_rate(stats)
corrections = correction_rate(stats)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Cases", stats["total_cases"], help="Rows in the troubleshooting dataset.")
k2.metric("AI Diagnoses", stats["total_diagnoses"],
          help="Diagnoses produced and stored, including pre-loaded demo records.")
k3.metric("AI-Human Agreement", pct_label(agreement, "Not enough data"),
          help="Reviewed diagnoses accepted unchanged.")
k4.metric("Human Corrections", stats["corrections"],
          help="Reviewed diagnoses that were edited or rejected.")

s1, s2, s3, s4 = st.columns(4)
s1.metric("Reviewed", stats["reviewed"])
s2.metric("Awaiting review", stats["pending_review"])
s3.metric("AI/checker conflicts", stats["conflicts"])
s4.metric("Conflict rate", pct_label(conflict_rate(stats), "—"))

if stats["reviewed"] == 0:
    st.info("Not enough reviewed cases yet — agreement and correction rates appear "
            "once a human has reviewed at least one diagnosis.", icon="ℹ️")

st.divider()

# ── Charts ───────────────────────────────────────────────────────────────────
tab_dataset, tab_ai, tab_oversight = st.tabs(
    ["Dataset coverage", "AI behaviour", "Human oversight"]
)

with tab_dataset:
    c1, c2 = st.columns(2)
    with c1:
        _bar(distribution(stats["cases_by_category"]), "Issue type distribution")
    with c2:
        _bar(distribution(stats["cases_by_severity"]), "Severity distribution",
             SEVERITY_COLORS, SEVERITY_ORDER)
    _bar(distribution(stats["cases_by_osi"]), "OSI layer distribution")

with tab_ai:
    c1, c2 = st.columns(2)
    with c1:
        _bar(distribution(stats["diagnoses_by_category"]), "Diagnoses by issue type")
    with c2:
        _donut(distribution(stats["diagnoses_by_confidence"]),
               "AI confidence distribution",
               {"High": "#1e8e3e", "Medium": "#e8710a", "Low": "#d93025"})
    if stats["total_diagnoses"] == 0:
        st.caption("No diagnoses recorded yet. Run one from the Analyze Network page.")

with tab_oversight:
    decisions = [(DECISION_LABELS.get(l, l), c)
                 for l, c in distribution(stats["decisions"])]
    c1, c2 = st.columns(2)
    with c1:
        _donut(decisions, "AI vs human decisions",
               {"✓ Accepted": "#1e8e3e", "✎ Edited": "#e8710a", "✕ Rejected": "#d93025"})
    with c2:
        _bar(distribution(stats["corrections_by_category"]),
             "Human corrections by issue type")

    if stats["reviewed"]:
        g1, g2 = st.columns(2)
        with g1:
            _gauge(agreement or 0.0, "AI agreement rate", good_high=True)
        with g2:
            _gauge(corrections or 0.0, "Human correction rate", good_high=False)
    else:
        st.info("Not enough reviewed cases yet.", icon="ℹ️")

st.divider()
st.markdown("### Recent diagnoses")
try:
    recent = db.get_all_diagnoses()[:15]
except Exception as exc:
    st.error(f"❌ Could not read diagnoses: {exc}")
    recent = []

if not recent:
    st.info("No diagnoses recorded yet.", icon="ℹ️")
else:
    st.dataframe(
        [
            {
                "ID": d["id"],
                "Case": d.get("case_ref") or "—",
                "Category": d.get("category") or "—",
                "Root cause (AI)": d.get("root_cause") or "—",
                "Confidence": d.get("confidence") or "—",
                "Conflict": "⚠️" if d.get("ai_conflict") else "",
                "Review": DECISION_LABELS.get(d.get("decision"), "Pending"),
                "Created": d.get("created_at"),
            }
            for d in recent
        ],
        width="stretch",
        hide_index=True,
    )
