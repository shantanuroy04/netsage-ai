"""
ai/groq_client.py — thin Groq API wrapper.

Owns every network call to Groq. Raises GroqError (never leaks the key) so the
UI layer can render a friendly message and offer a retry.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


class GroqError(RuntimeError):
    """Any Groq failure, already reduced to a user-safe message."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _client():
    if not config.api_key_configured():
        raise GroqError(
            "GROQ_API_KEY is not configured. Add it to .env or .streamlit/secrets.toml.",
            retryable=False,
        )
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover - install-time issue
        raise GroqError(f"Groq SDK is not installed: {exc}", retryable=False) from exc

    return Groq(api_key=config.get_groq_api_key(), timeout=config.REQUEST_TIMEOUT)


def chat_json(system_prompt: str, user_message: str, model: str | None = None) -> tuple[str, str]:
    """
    Send one JSON-mode completion to Groq.

    Returns (raw_response_text, model_used).
    """
    model = model or config.get_groq_model()
    client = _client()

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=config.TEMPERATURE,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise GroqError(_friendly(exc), retryable=_is_retryable(exc)) from exc

    if not resp.choices:
        raise GroqError("Groq returned an empty response. Please retry.")
    return resp.choices[0].message.content or "", model


def _is_retryable(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return not any(k in name for k in ("authentication", "permission", "notfound", "badrequest"))


def _friendly(exc: Exception) -> str:
    """Map SDK exception types to messages a network engineer can act on."""
    name = type(exc).__name__
    detail = str(exc)
    mapping = {
        "AuthenticationError": "Groq rejected the API key. Check GROQ_API_KEY.",
        "PermissionDeniedError": "This Groq API key is not allowed to use the selected model.",
        "NotFoundError": "The configured GROQ_MODEL does not exist. Pick a current model on the System page.",
        "RateLimitError": "Groq rate limit reached. Wait a moment and retry.",
        "APITimeoutError": "Groq request timed out. Retry, or raise GROQ_TIMEOUT.",
        "APIConnectionError": "Could not reach Groq. Check your network connection.",
        "BadRequestError": f"Groq rejected the request: {detail}",
    }
    return mapping.get(name, f"Groq request failed ({name}). Please retry.")


def list_models() -> list[str]:
    """Live model IDs available to this API key (System page uses this)."""
    try:
        return sorted(m.id for m in _client().models.list().data)
    except GroqError:
        raise
    except Exception as exc:
        raise GroqError(_friendly(exc), retryable=_is_retryable(exc)) from exc


def ping() -> tuple[bool, str]:
    """Cheap connectivity check used by the System page."""
    try:
        raw, model = chat_json(
            'Reply with the JSON object {"ok": true} and nothing else.',
            "ping",
        )
        return True, f"Groq reachable — model '{model}' responded."
    except GroqError as exc:
        return False, str(exc)
