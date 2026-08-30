"""
ai/schemas.py — structure + validation for the AI diagnosis payload.

The LLM is untrusted input: every field is coerced to the expected type and
range before anything reaches the UI or the database.
"""
import json
import re

REQUIRED_FIELDS = [
    "root_cause",
    "osi_layer",
    "confidence",
    "severity",
    "evidence",
    "next_command",
    "fix_steps",
    "concept",
]

CONFIDENCE_LEVELS = ["Low", "Medium", "High"]
SEVERITY_LEVELS = ["Low", "Medium", "High", "Critical"]

# JSON schema advertised to the model in the prompt (and usable with
# Groq's json_schema response format on models that support it).
DIAGNOSIS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string"},
        "osi_layer": {"type": "string"},
        "confidence": {"type": "string", "enum": CONFIDENCE_LEVELS},
        "severity": {"type": "string", "enum": SEVERITY_LEVELS},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "next_command": {"type": "string"},
        "fix_steps": {"type": "array", "items": {"type": "string"}},
        "concept": {"type": "string"},
    },
    "required": REQUIRED_FIELDS,
    "additionalProperties": False,
}


class DiagnosisParseError(ValueError):
    """The model produced something that is not a usable diagnosis."""


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a response that may carry fences/prose."""
    if not text or not text.strip():
        raise DiagnosisParseError("The AI returned an empty response.")

    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    # strict=False tolerates the raw newlines LLMs often leave inside strings.
    try:
        obj = json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise DiagnosisParseError("No JSON object found in the AI response.")
        try:
            obj = json.loads(match.group(0), strict=False)
        except json.JSONDecodeError as exc:
            raise DiagnosisParseError(f"AI response was not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise DiagnosisParseError("AI response was JSON but not an object.")
    return obj


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        # Accept newline / numbered lists as a courtesy.
        parts = [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", p).strip()
            for p in value.splitlines() if p.strip()]
        return [p for p in parts if p]
    return []


def _pick(value, allowed: list[str], fallback: str) -> str:
    text = str(value or "").strip().capitalize()
    return text if text in allowed else fallback


def validate_diagnosis(raw: dict) -> dict:
    """Coerce a raw model dict into a safe, complete diagnosis dict."""
    if not isinstance(raw, dict):
        raise DiagnosisParseError("Diagnosis payload is not an object.")

    root_cause = str(raw.get("root_cause", "")).strip()
    if not root_cause:
        raise DiagnosisParseError("AI response is missing 'root_cause'.")

    diag = {
        "root_cause": root_cause,
        "osi_layer": str(raw.get("osi_layer", "") or "Unknown").strip(),
        "confidence": _pick(raw.get("confidence"), CONFIDENCE_LEVELS, "Low"),
        "severity": _pick(raw.get("severity"), SEVERITY_LEVELS, "Medium"),
        "evidence": _as_list(raw.get("evidence")),
        "next_command": str(raw.get("next_command", "") or "show ip interface brief").strip(),
        "fix_steps": _as_list(raw.get("fix_steps")),
        "concept": str(raw.get("concept", "") or "General networking").strip(),
    }
    if not diag["fix_steps"]:
        diag["fix_steps"] = ["Gather more evidence before applying any change."]
    return diag


def parse_diagnosis(text: str) -> dict:
    """extract_json + validate_diagnosis in one step."""
    return validate_diagnosis(extract_json(text))


def demo():
    good = '```json\n{"root_cause":"VLAN 30 missing from trunk","osi_layer":"Layer 2",' \
           '"confidence":"HIGH","severity":"high","evidence":["allowed list excludes 30"],' \
           '"next_command":"show interfaces trunk","fix_steps":"1. add vlan 30\n2. verify",' \
           '"concept":"Trunk allowed VLAN list"}\n```'
    d = parse_diagnosis(good)
    assert d["confidence"] == "High" and d["severity"] == "High"
    assert d["fix_steps"] == ["add vlan 30", "verify"]
    assert set(REQUIRED_FIELDS) <= set(d)

    # Prose-wrapped JSON still parses.
    assert parse_diagnosis('Sure! {"root_cause":"x"} hope that helps')["root_cause"] == "x"
    # Bad confidence falls back, never crashes.
    assert parse_diagnosis('{"root_cause":"x","confidence":"banana"}')["confidence"] == "Low"

    for bad in ["", "no json here", '{"osi_layer":"Layer 2"}', "[1,2,3]"]:
        try:
            parse_diagnosis(bad)
            raise AssertionError(f"expected failure for {bad!r}")
        except DiagnosisParseError:
            pass
    print("ai/schemas.py self-check OK")


if __name__ == "__main__":
    demo()
