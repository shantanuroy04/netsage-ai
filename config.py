"""
config.py — NetSage AI configuration.

Secrets are read from (in order): Streamlit secrets -> environment / .env file.
Nothing is ever hard-coded and nothing is echoed back to the UI.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── Groq defaults ────────────────────────────────────────────────────────────
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

# Models known to work well for structured JSON reasoning on Groq.
# Editable — GROQ_MODEL always wins.
SUGGESTED_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "groq/compound",
]

REQUEST_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "60"))
TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))

# ── Paths ────────────────────────────────────────────────────────────────────
DB_PATH = BASE_DIR / "database" / "netsage.db"
CASES_CSV = BASE_DIR / "data" / "cases.csv"
PROMPTS_DIR = BASE_DIR / "prompts"

CATEGORIES = ["VLAN", "Routing", "DHCP", "DNS", "Gateway", "ACL", "NAT", "Wireless"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]


def _from_secrets(key: str) -> str | None:
    """Read a Streamlit secret without exploding when secrets.toml is absent."""
    try:
        import streamlit as st

        return st.secrets[key] if key in st.secrets else None
    except Exception:
        return None


def secrets_diagnostic() -> dict:
    """
    Never-values report of what st.secrets actually sees, for the System page.
    _from_secrets() above swallows every exception into None so a malformed
    secrets.toml looks identical to "no secret set" — this surfaces the
    difference without ever printing a secret value.
    """
    try:
        import streamlit as st

        keys = sorted(st.secrets.keys())
        return {
            "secrets_readable": True,
            "keys_present": keys,
            "has_groq_api_key": "GROQ_API_KEY" in keys,
            "has_groq_model": "GROQ_MODEL" in keys,
            "error": None,
        }
    except Exception as exc:
        return {
            "secrets_readable": False,
            "keys_present": [],
            "has_groq_api_key": False,
            "has_groq_model": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def get_groq_api_key() -> str | None:
    return _from_secrets("GROQ_API_KEY") or os.getenv("GROQ_API_KEY") or None


def get_groq_model() -> str:
    return _from_secrets("GROQ_MODEL") or os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL


def api_key_configured() -> bool:
    key = get_groq_api_key()
    return bool(key and key.strip())


def masked_api_key() -> str:
    """Never render the key itself — only proof that one is present."""
    return "configured (hidden)" if api_key_configured() else "not configured"
