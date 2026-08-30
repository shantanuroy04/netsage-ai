"""
pages/system.py — ⚙️ System.

Configuration status and connectivity checks. The API key itself is never
rendered — only whether one is present.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

import config
from ai.groq_client import GroqError, list_models, ping
from database import db
from database.seed import RESPONSIBLE_AI_SEEDS, SEED_REVIEWER, clear_seed_data, seed_responsible_ai

st.markdown("## ⚙️ System")
st.caption("Provider configuration, database state, and the safety boundaries "
           "this application operates within.")
st.divider()

# ── AI provider ──────────────────────────────────────────────────────────────
st.markdown("### AI provider")
c1, c2, c3 = st.columns(3)
c1.metric("Provider", "Groq")
c2.metric("Model", config.get_groq_model())
c3.metric("API key", config.masked_api_key())

if not config.api_key_configured():
    st.warning(
        "⚠️ GROQ_API_KEY is not configured. Analysis will run the deterministic "
        "checker but cannot produce an AI diagnosis.",
    )
    st.markdown(
        """
**Local development** — create a `.env` file next to `app.py`:

```
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

**Streamlit deployment** — add the same keys under `.streamlit/secrets.toml`
or in the app's Secrets settings.
"""
    )
else:
    st.success("API key detected. It is read from Streamlit secrets or the "
               "environment and is never displayed or written to the database.",
               icon="🔐")

t1, t2 = st.columns(2)
if t1.button("Test Groq connection", width="stretch"):
    with st.spinner("Contacting Groq…"):
        ok, message = ping()
    (st.success if ok else st.error)(message)

if t2.button("List available models", width="stretch"):
    try:
        with st.spinner("Fetching model list…"):
            models = list_models()
    except GroqError as exc:
        st.error(f"❌ {exc}")
    else:
        st.caption(f"{len(models)} models available to this key. Set `GROQ_MODEL` "
                   "in `.env` or secrets to change the one in use.")
        st.code("\n".join(models), language="text")

st.caption("Suggested models for structured reasoning: " +
           " · ".join(f"`{m}`" for m in config.SUGGESTED_MODELS))

st.divider()

# ── Database ─────────────────────────────────────────────────────────────────
st.markdown("### Database")
try:
    stats = db.get_stats()
except Exception as exc:
    st.error(f"❌ Could not read the database: {exc}")
    st.stop()

d1, d2, d3, d4 = st.columns(4)
d1.metric("Cases", stats["total_cases"])
d2.metric("Diagnoses", stats["total_diagnoses"])
d3.metric("Reviews", stats["reviewed"])
d4.metric("Conflicts", stats["conflicts"])
st.caption(f"SQLite file: `{db.DB_PATH}` — no API keys are stored in it.")

st.markdown("#### Pre-loaded demonstration records")
st.caption(
    f"{len(RESPONSIBLE_AI_SEEDS)} correction examples ship with the project so the "
    "responsible-AI log is populated on a fresh install. They are tagged "
    f"“{SEED_REVIEWER}” and labelled as pre-loaded wherever they appear — they are "
    "never counted as live human reviews."
)
s1, s2 = st.columns(2)
if s1.button("Re-insert demo corrections", width="stretch"):
    inserted = seed_responsible_ai(force=True)
    st.success(f"Inserted {inserted} demonstration record(s).")
    st.rerun()
if s2.button("Remove demo corrections", width="stretch"):
    removed = clear_seed_data()
    st.success(f"Removed {removed} demonstration record(s). Only live reviews remain.")
    st.rerun()

st.divider()

# ── Safety ───────────────────────────────────────────────────────────────────
st.markdown("### Safety boundaries")
st.markdown(
    """
NetSage AI is an **advisory** troubleshooting assistant, not an autonomous network
configuration system.

- It does **not** execute Cisco commands.
- It does **not** connect to, or modify, any network device.
- Fix steps are recommendations for a human engineer to review and apply.
- Human approval is mandatory before any diagnosis is treated as resolved.
- Deterministic Python checks run before every AI call and are never replaced by it.
"""
)

st.markdown("### Pipeline")
st.code(
    "Evidence (symptom + topology + show output)\n"
    "        |\n"
    "        v\n"
    "Deterministic Python rule checker      <- fixed logic, runs first\n"
    "        |\n"
    "        v\n"
    "Groq AI diagnosis (structured JSON)    <- receives checker findings\n"
    "        |\n"
    "        v\n"
    "Evidence comparison (agree / conflict)\n"
    "        |\n"
    "        v\n"
    "Human review (accept / edit / reject)  <- mandatory\n"
    "        |\n"
    "        v\n"
    "SQLite  ->  Dashboard + Responsible-AI log",
    language="text",
)
