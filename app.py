"""
app.py — NetSage AI (Streamlit entry point).

Run with:  streamlit run app.py

Pipeline:  Evidence -> Deterministic rule checker -> Groq AI -> Comparison
           -> Human review -> SQLite -> Dashboard
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import streamlit as st

import config

st.set_page_config(
    page_title="NetSage AI — Network Troubleshooting Assistant",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
  section[data-testid="stSidebar"] { min-width: 265px; }
  div[data-testid="stMetric"] {
      background: rgba(128,128,128,0.08);
      border: 1px solid rgba(128,128,128,0.20);
      border-radius: 10px;
      padding: 14px 16px;
  }
  div[data-testid="stMetricLabel"] p {
      font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em;
      opacity: .75;
  }
  .ns-brand { line-height: 1.25; padding: 4px 0 10px 0; }
  .ns-brand h1 { font-size: 1.35rem; margin: 0; }
  .ns-brand span { font-size: 0.78rem; opacity: .7; }
  .ns-panel {
      border: 1px solid rgba(128,128,128,0.25);
      border-left: 4px solid var(--ns-accent, #1a73e8);
      border-radius: 8px; padding: 12px 16px; margin-bottom: 10px;
      background: rgba(128,128,128,0.05);
  }
  .ns-panel h5 { margin: 0 0 6px 0; font-size: .82rem; text-transform: uppercase;
      letter-spacing: .07em; opacity: .8; }
  .ns-panel p { margin: 0; font-size: 1rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner="Initialising NetSage AI database…")
def _bootstrap() -> dict:
    """Schema + dataset + pre-loaded demo corrections. Runs once per server."""
    from database.seed import bootstrap

    return bootstrap()


def _sidebar_status() -> None:
    st.sidebar.markdown(
        "<div class='ns-brand'><h1>🌐 NetSage AI</h1>"
        "<span>Network Troubleshooting Assistant</span></div>",
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
    with st.sidebar:
        st.caption("AI PROVIDER")
        if config.api_key_configured():
            st.success(f"Groq · `{config.get_groq_model()}`", icon="✅")
        else:
            st.warning("GROQ_API_KEY not configured", icon="⚠️")
        st.caption(
            "Advisory only — NetSage AI never executes Cisco commands. "
            "Every diagnosis requires human review."
        )


def main() -> None:
    try:
        boot = _bootstrap()
    except Exception as exc:  # database is fatal — say so clearly, don't crash
        st.error(f"❌ Database initialisation failed: {exc}")
        st.stop()
        return

    st.session_state.setdefault("boot_info", boot)
    _sidebar_status()

    pages = [
        st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True),
        st.Page("pages/analyze.py", title="Analyze Network", icon="🔍"),
        st.Page("pages/cases.py", title="Troubleshooting Cases", icon="📁"),
        st.Page("pages/review.py", title="Human Review", icon="👨‍💻"),
        st.Page("pages/responsible_ai.py", title="Responsible AI", icon="🛡"),
        st.Page("pages/system.py", title="System", icon="⚙️"),
    ]
    st.navigation(pages).run()


main()
