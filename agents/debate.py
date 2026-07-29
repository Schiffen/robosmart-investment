"""
agents/debate.py — the "Bull vs Bear" debate engine (Person 3).
================================================================
Runs a five-turn adversarial debate over a SINGLE ticker's market context and
returns a strict JSON verdict that tabs/debate.py renders. The whole flow is
MOCK-FIRST: when `llm.use_mock()` is True (USE_MOCK=1 or no API key) we serve
mock_debate.json instead of touching the network, so the app demos with no key.

Turn order (real mode — 5 LLM calls, each sees strictly more than the last):
    1. Bull opening   — sees the context
    2. Bear opening   — sees the context + bull opening
    3. Bull rebuttal  — sees the context + both openings
    4. Bear rebuttal  — sees the context + both openings + bull rebuttal
    5. Judge          — sees everything and scores it

The persona and every rule (cite a number, no hallucination, bear never
concedes, judge may be inconclusive + 3 falsifiers, JSON-only) live in
prompts/*.txt as system prompts — NOT hardcoded here. This file only wires the
data in and assembles the output.
"""

from __future__ import annotations

import json
import os
import sys

# Make the file runnable both as a package module (`python3 -m agents.debate`)
# and directly (`python3 agents/debate.py`): ensure the repo root — where the
# `agents`, `data_layer`, and `theme` modules live — is importable.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents import llm

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
_MOCK_PATH = os.path.join(os.path.dirname(__file__), "..", "mock_debate.json")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _load(name: str) -> str:
    """Read a prompt template (system prompt) from prompts/<name>.txt."""
    with open(os.path.join(_PROMPT_DIR, name + ".txt"), encoding="utf-8") as f:
        return f.read()


def _g(d: dict, *path, default="n/a"):
    """Nested .get() that never raises and reports missing fields as 'n/a'."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _dumps(obj) -> str:
    """Pretty JSON for feeding a prior turn's output into the next prompt."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _pick(resp, key: str) -> dict:
    """Normalize a model response: if it wrapped the payload under `key`
    (e.g. {"opening": {...}}), unwrap it; otherwise return it as-is."""
    if isinstance(resp, dict):
        if key in resp and isinstance(resp[key], dict):
            return resp[key]
        return resp
    return {}


def _context_block(context: dict) -> str:
    """Render the context dict as a compact, number-rich text block the agents
    cite from. Every field uses a safe fallback so a missing key never crashes."""
    ticker = _g(context, "ticker", default="?")
    lines = [
        f"Ticker: {ticker}",
        f"Company: {_g(context, 'company_name')}",
        f"Sector: {_g(context, 'sector')}",
        "",
        "PRICE:",
        f"  current: {_g(context, 'price', 'current')}",
        f"  prev_close: {_g(context, 'price', 'prev_close')}",
        f"  day_change_pct: {_g(context, 'price', 'day_change_pct')}%",
        "",
        "RETURNS (%):",
        f"  1d: {_g(context, 'returns', '1d')}   5d: {_g(context, 'returns', '5d')}"
        f"   1m: {_g(context, 'returns', '1m')}   ytd: {_g(context, 'returns', 'ytd')}",
        "",
        "FUNDAMENTALS:",
        f"  pe: {_g(context, 'fundamentals', 'pe')}   forward_pe: {_g(context, 'fundamentals', 'forward_pe')}",
        f"  market_cap: {_g(context, 'fundamentals', 'market_cap')}",
        f"  profit_margin: {_g(context, 'fundamentals', 'profit_margin')}"
        f"   revenue_growth: {_g(context, 'fundamentals', 'revenue_growth')}",
        f"  debt_to_equity: {_g(context, 'fundamentals', 'debt_to_equity')}",
        "",
        "TECHNICALS:",
        f"  rsi_14: {_g(context, 'technicals', 'rsi_14')}   atr: {_g(context, 'technicals', 'atr')}",
        f"  sma_50: {_g(context, 'technicals', 'sma_50')}   sma_200: {_g(context, 'technicals', 'sma_200')}",
    ]

    benchmarks = context.get("benchmarks")
    if isinstance(benchmarks, dict) and benchmarks:
        bench = "   ".join(f"{k}: {v}%" for k, v in benchmarks.items())
        lines += ["", "BENCHMARKS (day %):", f"  {bench}"]

    news = context.get("news")
    if isinstance(news, list) and news:
        lines += ["", "RECENT HEADLINES:"]
        for item in news[:6]:
            if isinstance(item, dict):
                title = item.get("title", "")
                pub = item.get("publisher", "")
                date = item.get("published", "")
                lines.append(f'  - "{title}" ({pub}, {date})')

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def run_debate(context: dict) -> dict:
    """Run the five-turn Bull vs Bear debate and return the strict output schema.

    In mock mode (llm.use_mock()) this returns mock_debate.json — NO API call is made.
    The fixture was recorded for one ticker only; see `recorded_for` in the result.
    """
    context = context or {}
    ticker = context.get("ticker") or "?"

    # ---- Mock path: serve the fixture, never touch the network -------------
    if llm.use_mock():
        with open(_MOCK_PATH, encoding="utf-8") as f:
            mock = json.load(f)
        # The fixture is NVDA-specific all the way down: its claims cite NVDA's market
        # cap, margins and SMAs. Previously we overwrote `ticker` and returned it, so
        # picking JNJ produced a debate about "the AI compute build-out" under a JNJ
        # header — indistinguishable from the model fabricating. Carry the provenance
        # instead and let the UI say plainly what the reader is looking at.
        mock["recorded_for"] = mock.get("ticker") or "NVDA"
        mock["is_mock"] = True
        mock["ticker"] = ticker
        return mock

    # ---- Real path: 5 chained LLM calls, each seeing strictly more ---------
    ctx = _context_block(context)
    user = f"Deliver your JSON for the {ticker} debate now."

    # 1. Bull opening — sees the context.
    bull_open = _pick(
        llm.call_json(_load("bull_opening").format(ticker=ticker, context=ctx), user),
        "opening",
    )

    # 2. Bear opening — sees the context + bull opening.
    bear_open = _pick(
        llm.call_json(
            _load("bear_opening").format(ticker=ticker, context=ctx, bull=_dumps(bull_open)),
            user,
        ),
        "opening",
    )

    # 3. Bull rebuttal — sees the context + both openings.
    bull_reb = _pick(
        llm.call_json(
            _load("bull_rebuttal").format(
                ticker=ticker, context=ctx,
                bull_opening=_dumps(bull_open), bear_opening=_dumps(bear_open),
            ),
            user,
        ),
        "rebuttal",
    )

    # 4. Bear rebuttal — sees the context + both openings + bull rebuttal.
    bear_reb = _pick(
        llm.call_json(
            _load("bear_rebuttal").format(
                ticker=ticker, context=ctx,
                bull_opening=_dumps(bull_open), bear_opening=_dumps(bear_open),
                bull_rebuttal=_dumps(bull_reb),
            ),
            user,
        ),
        "rebuttal",
    )

    # 5. Judge — sees everything and scores it.
    judge = _pick(
        llm.call_json(
            _load("judge").format(
                ticker=ticker, context=ctx,
                bull_opening=_dumps(bull_open), bear_opening=_dumps(bear_open),
                bull_rebuttal=_dumps(bull_reb), bear_rebuttal=_dumps(bear_reb),
            ),
            user,
        ),
        "judge",
    )

    return {
        "ticker": ticker,
        "bull": {"opening": bull_open, "rebuttal": bull_reb},
        "bear": {"opening": bear_open, "rebuttal": bear_reb},
        "judge": judge,
    }


if __name__ == "__main__":
    import data_layer

    result = run_debate(data_layer.get_context("NVDA"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
