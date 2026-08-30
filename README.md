# 🌐 NetSage AI

[![Live Demo](https://img.shields.io/badge/demo-live-1a73e8?logo=streamlit&logoColor=white)](https://netsage-ai-public.streamlit.app)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](requirements.txt)
[![Built with Groq](https://img.shields.io/badge/AI-Groq-f55036)](https://groq.com)

**An evidence-first network troubleshooting assistant for Cisco / Packet Tracer faults.**


NetSage AI helps a junior network engineer go from *"PC1 can't reach the server"*
to a defensible root cause. It does this in a deliberate order: deterministic
Python checks run **first**, a Groq-hosted LLM reasons **second**, the two
answers are **compared**, and a human engineer **decides** last.

It is an advisory tool. It does not execute Cisco commands, does not connect to
devices, and never applies a fix on its own.

---

## Architecture

```text
Streamlit UI
     ↓
Deterministic rule checker      ← fixed Python logic, always runs first
     ↓
Groq AI diagnosis               ← receives the checker's findings as input
     ↓
Evidence comparison             ← agree, or flag a conflict
     ↓
Human review                    ← Accept / Edit / Reject (mandatory)
     ↓
SQLite
     ↓
Dashboard + Responsible-AI log
```

The ordering is the point. The LLM never replaces the deterministic checks — it
is given them, must reconcile with them, and is flagged when it doesn't.

---

## Features

- **AI troubleshooting** — structured diagnosis with root cause, OSI layer,
  confidence, severity, cited evidence, next command, fix steps, and the
  networking concept involved.
- **Groq integration** — fast inference via the official Groq SDK, JSON mode,
  configurable model, validated output.
- **Packet Tracer case dataset** — 32 troubleshooting cases spanning VLAN,
  Routing, DHCP, DNS, Gateway, ACL, NAT and Wireless.
- **Deterministic rule checker** — 16 fixed Python rules across IP addressing,
  VLAN/trunking, routing, and interface state. No LLM involved.
- **AI vs checker comparison** — explicit conflict banner when they disagree.
- **Human review** — Accept / Edit / Reject, with the original AI output never
  overwritten.
- **Responsible-AI logging** — every human correction recorded with the reason.
- **Analytics dashboard** — issue type, severity, OSI layer, decisions,
  agreement and correction rates, all computed from the database.

---

## Installation

```bash
git clone <repository>
cd netsage-ai
pip install -r requirements.txt
```

Requires Python 3.10+.

---

## Environment Variables

Create a `.env` file next to `app.py` (see `.env.example`):

```text
GROQ_API_KEY=your_key
GROQ_MODEL=openai/gpt-oss-120b
```

Optional: `GROQ_TIMEOUT` (seconds, default 60), `GROQ_TEMPERATURE` (default 0.2).

For Streamlit Community Cloud, put the same keys in `.streamlit/secrets.toml`
(see `.streamlit/secrets.toml.example`) or the app's Secrets settings.
`config.get_groq_api_key()` checks Streamlit secrets first, then the
environment, so the same code works locally and deployed.

The key is never hard-coded, never displayed in the UI, never logged, and never
written to the database. `.env` and `.streamlit/secrets.toml` are gitignored.

**Picking a model:** model availability on Groq changes over time. The System
page has a **List available models** button that queries your key live — set
`GROQ_MODEL` to any chat model it returns.

---

## Run

```bash
streamlit run app.py
```

The database is created, the case dataset loaded, and demonstration records
seeded automatically on first launch.

---

## Project Structure

```text
netsage-ai/
├── app.py                    # Streamlit entry point, sidebar, navigation
├── pages/
│   ├── dashboard.py          # 📊 KPIs and Plotly analytics
│   ├── analyze.py            # 🔍 checker → Groq → comparison
│   ├── cases.py              # 📁 dataset browser, "load into Analyze"
│   ├── review.py             # 👨‍💻 Accept / Edit / Reject
│   ├── responsible_ai.py     # 🛡 correction log and oversight metrics
│   └── system.py             # ⚙️ config status, connectivity, safety notes
├── ai/
│   ├── groq_client.py        # Groq SDK wrapper, key handling, error mapping
│   ├── diagnosis.py          # prompt assembly and the diagnose() entry point
│   └── schemas.py            # JSON schema, extraction, validation
├── checker/
│   ├── ip_checker.py         # duplicate IPs, masks, gateway mismatch
│   ├── vlan_checker.py       # VLAN presence, trunk allowed list, native VLAN
│   ├── route_checker.py      # default route, next-hop reachability, loops
│   ├── interface_checker.py  # up/down, unassigned IPs, duplex, error counters
│   └── runner.py             # aggregation, report shaping, conflict detection
├── database/
│   ├── db.py                 # SQLite access layer and aggregates
│   ├── schema.sql            # tables + responsible_ai_log view
│   └── seed.py               # dataset loading, demo correction records
├── data/cases.csv            # 32 troubleshooting cases
├── prompts/
│   ├── diagnose_prompt.md    # system prompt
│   └── examples.md           # three few-shot worked examples
├── utils/
│   ├── metrics.py            # rates, "not enough data" handling
│   ├── helpers.py            # formatting, badges, session plumbing
│   └── render.py             # shared evidence-first renderers
├── tests/
│   ├── test_pipeline.py      # end-to-end pipeline checks
│   └── test_ui_smoke.py      # renders every page headlessly
├── .streamlit/config.toml
└── requirements.txt
```

---

## Example Workflow

```text
Enter symptom
      ↓
Paste show output
      ↓
Run rule checker          ← deterministic, before any AI call
      ↓
Groq diagnosis            ← given the checker's findings
      ↓
Compare results           ← "✓ agree" or "⚠️ DIAGNOSIS CONFLICT"
      ↓
Human review
      ↓
Accept / Edit / Reject
      ↓
Dashboard updated
```

Or start from **📁 Troubleshooting Cases**, pick a dataset case, and click
*Load into Analyze Network* to run the same flow on known evidence.

---

## How the pieces fit

**Rule checker first.** Clicking *Analyze Network* runs `checker.analyze()`
before anything else. Its findings are rendered immediately and are valid even
if the AI call fails or no API key is configured.

**Checker findings feed the prompt.** `ai/diagnosis.py` formats them as
`[PASS] / [WARN] / [FAIL]` lines inside the prompt. The system prompt requires
the model to address any hard failure explicitly rather than ignore it.

**Every AI response is validated.** `ai/schemas.py` extracts JSON from the
response (tolerating fences, prose, and raw newlines inside strings), then
coerces every field. A malformed response raises `DiagnosisParseError`, which
the UI shows as a friendly message with a retry — it never crashes the app.

**Conflict detection.** If a rule hard-failed and the AI's root cause never
mentions that concept, the diagnosis is stored with `ai_conflict = 1` and the UI
shows a conflict banner. The flag feeds the dashboard's conflict metrics.

**Human review never overwrites the AI.** The `diagnoses` row is immutable; a
review is a separate `reviews` row holding the corrected fields, the correction
notes, and the reason. The `responsible_ai_log` view joins the two so the
original AI output and the human conclusion sit side by side forever.

**Nothing is fabricated.** Rates return "Not enough data" rather than 0% when
there is nothing to divide by. The six correction examples that ship with the
project are tagged `Pre-loaded demo record` and labelled as such in the UI and
in the Source column of the responsible-AI table; they can be removed from the
System page.

---

## Tests

```bash
python tests/test_pipeline.py    # dataset, checker, AI, conflicts, reviews, metrics
python tests/test_ui_smoke.py    # renders all 7 Streamlit pages headlessly
```

Module self-checks:

```bash
python ai/schemas.py
python -m checker.runner
python utils/metrics.py
python utils/helpers.py
```

`test_pipeline.py` uses a throwaway database and skips (rather than fails) the
live Groq leg when no API key is present.

---

## Safety

NetSage AI is an **advisory** assistant, not an autonomous configuration system.

- It does not execute Cisco commands.
- It does not connect to or modify any network device.
- Fix steps are recommendations for a human engineer to apply.
- Human approval is mandatory before a diagnosis is treated as resolved.
- Deterministic checks always run and are never replaced by the model.
- API keys are read from the environment or Streamlit secrets, and are never
  displayed, logged, or stored.
