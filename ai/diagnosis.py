"""
ai/diagnosis.py — AI Diagnosis Engine (Groq).

Pipeline position:
    rule checker results  ->  diagnose()  ->  validated diagnosis dict

The deterministic checker always runs first; its findings are handed to the
model as evidence it must reconcile with, never as something it may overrule
silently. No mock/fallback diagnosis is ever fabricated — on failure this
raises so the UI can show an error and offer a retry.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from ai.groq_client import GroqError, chat_json
from ai.schemas import DIAGNOSIS_JSON_SCHEMA, DiagnosisParseError, parse_diagnosis

_prompt_cache: dict[str, str] = {}


def load_system_prompt() -> str:
    """Master prompt + few-shot examples, read once from prompts/."""
    if "system" not in _prompt_cache:
        base = config.PROMPTS_DIR
        system = (base / "diagnose_prompt.md").read_text(encoding="utf-8")
        examples = (base / "examples.md").read_text(encoding="utf-8")
        _prompt_cache["system"] = f"{system}\n\n---\n\n{examples}"
    return _prompt_cache["system"]


def format_rule_results(rule_results: list[dict]) -> str:
    """Render checker output as plain text for the prompt."""
    if not rule_results:
        return "No deterministic checks were applicable to this input."
    lines = []
    for r in rule_results:
        status = str(r.get("status", "")).upper()
        lines.append(f"[{status}] {r.get('rule')}: {r.get('detail')}")
    return "\n".join(lines)


def build_user_message(symptom: str, topology: str, show_output: str,
                       category: str, rule_results: list[dict],
                       case_information: str = "") -> str:
    """Assemble the INPUT block described in prompts/diagnose_prompt.md."""
    return (
        f"CATEGORY:\n{category or 'Unspecified'}\n\n"
        f"SYMPTOM:\n{symptom.strip()}\n\n"
        f"TOPOLOGY:\n{topology.strip() or 'Not supplied.'}\n\n"
        f"SHOW COMMAND OUTPUT:\n{show_output.strip() or 'Not supplied.'}\n\n"
        f"DETERMINISTIC RULE CHECKER RESULTS:\n{format_rule_results(rule_results)}\n\n"
        f"KNOWN CASE INFORMATION, IF AVAILABLE:\n{case_information.strip() or 'None.'}\n\n"
        f"Return a single JSON object matching this schema:\n{DIAGNOSIS_JSON_SCHEMA}"
    )


def diagnose(symptom: str, topology: str, show_output: str,
             category: str = "General", rule_results: list[dict] | None = None,
             case_information: str = "", model: str | None = None) -> dict:
    """
    Produce a validated structured diagnosis.

    Raises:
        ValueError        — empty symptom (caller supplied nothing to analyse)
        GroqError         — key missing / API failure (has .retryable)
        DiagnosisParseError — model returned unusable output
    """
    if not symptom or not symptom.strip():
        raise ValueError("A symptom description is required before analysis.")

    user_message = build_user_message(
        symptom, topology, show_output, category, rule_results or [], case_information
    )
    raw, model_used = chat_json(load_system_prompt(), user_message, model=model)
    diag = parse_diagnosis(raw)
    diag["model"] = model_used
    diag["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return diag


__all__ = [
    "diagnose",
    "load_system_prompt",
    "build_user_message",
    "format_rule_results",
    "GroqError",
    "DiagnosisParseError",
]
