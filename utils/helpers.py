"""
utils/helpers.py — small shared UI helpers (formatting, session plumbing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

# Session keys used to hand a case from the Cases page to the Analyze page,
# and a fresh diagnosis from Analyze to Review.
PREFILL_KEY = "netsage_prefill_case"
LAST_DIAGNOSIS_KEY = "netsage_last_diagnosis_id"

SEVERITY_COLORS = {
    "critical": "#b3261e",
    "high": "#d93025",
    "medium": "#e8710a",
    "low": "#1a73e8",
    "info": "#5f6368",
}
CONFIDENCE_COLORS = {"high": "#1e8e3e", "medium": "#e8710a", "low": "#d93025"}
STATUS_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌", "ok": "✅",
                "warning": "⚠️", "info": "ℹ️"}
DECISION_LABELS = {"accept": "✓ Accepted", "edit": "✎ Edited", "reject": "✕ Rejected"}


def badge(text: str, color: str) -> str:
    """Inline coloured pill. Returned as HTML for st.markdown(unsafe_allow_html)."""
    return (
        f"<span style='background:{color};color:#fff;padding:2px 10px;"
        f"border-radius:10px;font-size:0.78rem;font-weight:600;"
        f"white-space:nowrap;'>{text}</span>"
    )


def severity_badge(severity: str) -> str:
    key = (severity or "info").strip().lower()
    return badge(key.upper(), SEVERITY_COLORS.get(key, SEVERITY_COLORS["info"]))


def confidence_badge(confidence: str) -> str:
    key = (confidence or "low").strip().lower()
    return badge(f"CONFIDENCE: {key.upper()}",
                 CONFIDENCE_COLORS.get(key, CONFIDENCE_COLORS["low"]))


def cisco_block(text: str, height: int | None = None) -> None:
    """Render show-command output in a monospace, scrollable block."""
    st.code(text or "(no output supplied)", language="text", height=height)


def numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(items, 1)) if items else ""


def bulleted(items: list[str], marker: str = "✓") -> str:
    return "\n".join(f"- {marker} {s}" for s in items) if items else ""


def parse_lines(text: str) -> list[str]:
    """Turn a reviewer's multi-line text area into a clean list."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-*").strip()
        while line[:1].isdigit():
            stripped = line.lstrip("0123456789").lstrip()
            if stripped.startswith((".", ")")):
                line = stripped[1:].strip()
            else:
                break
        if line:
            out.append(line)
    return out


def truncate(text: str, limit: int = 90) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def set_prefill(case: dict) -> None:
    st.session_state[PREFILL_KEY] = case


def pop_prefill() -> dict | None:
    return st.session_state.pop(PREFILL_KEY, None)


def peek_prefill() -> dict | None:
    return st.session_state.get(PREFILL_KEY)


def section(title: str, subtitle: str = "") -> None:
    """Consistent section header used across pages."""
    st.markdown(f"#### {title}")
    if subtitle:
        st.caption(subtitle)


def page_header(icon: str, title: str, subtitle: str) -> None:
    st.markdown(f"## {icon} {title}")
    st.caption(subtitle)
    st.divider()


def empty_state(message: str, hint: str = "") -> None:
    st.info(message + (f"\n\n{hint}" if hint else ""))


def demo():
    assert parse_lines("1. one\n2) two\n- three\n\n") == ["one", "two", "three"]
    assert parse_lines("") == []
    assert truncate("abc", 10) == "abc"
    assert truncate("a" * 20, 10).endswith("…")
    assert "CRITICAL" in severity_badge("Critical")
    assert numbered(["a", "b"]) == "1. a\n2. b"
    print("utils/helpers.py self-check OK")


if __name__ == "__main__":
    demo()
