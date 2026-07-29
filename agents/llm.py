"""
agents/llm.py — shared LLM client + JSON parsing for the two AI tabs.
====================================================================
Mock-first: if USE_MOCK=1 or no ANTHROPIC_API_KEY is present, callers fall back
to their mock outputs, so the whole app runs end-to-end with NO key and NO
network (critical for demo reliability and for local dev). When a key IS set,
the same code path calls the real Anthropic API.
"""

from __future__ import annotations

import json
import os
import re

# Per the project plan. Overridable via env so the team can pin a valid model id.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


class LLMUnavailable(Exception):
    """Raised when the SDK/key is missing and a real call was attempted."""


def use_mock() -> bool:
    """True when callers should serve their recorded output instead of calling the API.

    Delegates to `run_mode` so the LLM axis and the market-data axis follow one
    precedence rule: an explicit USE_MOCK_LLM wins, USE_MOCK is the both-axes
    shortcut, and no API key means recorded regardless.
    """
    import run_mode
    return run_mode.use_recorded_llm()


def _client():
    try:
        from anthropic import Anthropic
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(f"anthropic SDK not installed: {e}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    return Anthropic()


def call_text(system: str, user: str, max_tokens: int = 4096) -> str:
    resp = _client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(getattr(b, "text", "") for b in resp.content
                   if getattr(b, "type", "") == "text")


_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Strip ```json fences and pull the first {...} block, then parse."""
    t = _FENCE.sub("", text).strip().strip("`").strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


def call_json(system: str, user: str, max_tokens: int = 4096, retries: int = 1) -> dict:
    """Call the model and parse JSON; retry once with a 'valid JSON only' nudge."""
    text = call_text(system, user, max_tokens)
    try:
        return extract_json(text)
    except Exception:
        if retries > 0:
            fixed = user + "\n\nReturn VALID JSON only — no prose, no markdown fences."
            return call_json(system, fixed, max_tokens, retries - 1)
        raise
