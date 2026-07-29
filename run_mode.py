"""run_mode.py — which sources this process reads from.

Two INDEPENDENT axes, because they fail for different reasons and you want to
pin them separately:

    market data : live yfinance    | recorded fixture
    AI output   : live Anthropic   | recorded fixture

`USE_MOCK=1` flips BOTH to recorded — the single switch for a fully offline
demo, and what `app.py` has always claimed it does.

`USE_MOCK_DATA` / `USE_MOCK_LLM` override their own axis and BEAT `USE_MOCK`,
so you can pin one without the other. The combination that earns its keep is
live LLM + fixture data: the model's input is then frozen, so an output change
is attributable to the prompt rather than to the market having moved.

Every read happens at CALL time, never at import. `app.py` calls `load_dotenv()`
after this module may already be imported, and tests flip these with
`monkeypatch.setenv` — caching the answer at import would silently ignore both.
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _flag(name: str) -> bool | None:
    """Tri-state read: True, False, or None when unset/unrecognised.

    The None case is what makes override precedence work — an unset specific
    flag must defer to USE_MOCK, while an explicit `USE_MOCK_DATA=0` must not.
    """
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return None


def _resolve(specific: str) -> bool:
    """Specific flag if it was set explicitly, else fall back to USE_MOCK."""
    explicit = _flag(specific)
    if explicit is not None:
        return explicit
    return _flag("USE_MOCK") is True


def use_fixture_data() -> bool:
    """True when market data should be replayed from the recorded fixture."""
    return _resolve("USE_MOCK_DATA")


def use_recorded_llm() -> bool:
    """True when the AI tabs should serve recorded output instead of calling out.

    No API key means no choice — recorded, regardless of any flag. This
    preserves the original `llm.use_mock()` behaviour, which is what keeps the
    app demoable for someone who just cloned it.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return True
    return _resolve("USE_MOCK_LLM")


def describe() -> dict:
    """Resolved mode, for the sidebar and for startup logging.

    Returned rather than printed so the caller decides how loudly to say it.
    """
    return {
        "data": "fixture" if use_fixture_data() else "live",
        "llm": "recorded" if use_recorded_llm() else "live",
    }


def summary_line() -> str | None:
    """One human sentence for the sidebar, or None when fully live.

    Naming the snapshot date is the point: recorded data that looks live is the
    failure mode worth designing against.
    """
    mode = describe()
    if mode["data"] == "live" and mode["llm"] == "live":
        return None

    parts = []
    if mode["data"] == "fixture":
        from market_data import fixture
        stamp = fixture.snapshot_date() or "unknown date"
        parts.append(f"recorded market data from {stamp}")
    else:
        parts.append("live market data")
    parts.append("recorded AI output" if mode["llm"] == "recorded" else "live AI")
    return "🧪 " + " · ".join(parts)
