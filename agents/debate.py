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


def _ratio_pct(v, digits: int = 1) -> str:
    """A 0-1 ratio as a human percentage: 0.62966 -> '63.0%'."""
    try:
        return f"{float(v) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _big_money(v) -> str:
    """A market cap as a human figure: 4523000000000 -> '$4.52 trillion'."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "n/a"
    for cutoff, unit in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if abs(x) >= cutoff:
            return f"${x / cutoff:,.2f} {unit}"
    return f"${x:,.0f}"


def _num(v, digits: int = 2) -> str:
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _context_block(context: dict) -> str:
    """Render the context dict as a compact, number-rich text block the agents
    cite from. Every field uses a safe fallback so a missing key never crashes.

    Numbers are rendered the way a person says them, not the way the API
    returns them. The prompts tell each analyst to quote "the exact number from
    the CONTEXT", and they obey — so when this block said `profit_margin:
    0.62966`, that exact string was what a beginner read on screen as the
    evidence for a claim. The fix belongs here, at the model's input, rather
    than in a render-time cleanup of whatever the model happened to echo.
    """
    ticker = _g(context, "ticker", default="?")
    f = context.get("fundamentals") or {}
    lines = [
        f"Ticker: {ticker}",
        f"Company: {_g(context, 'company_name')}",
        f"Sector: {_g(context, 'sector')}",
        "",
        "PRICE:",
        f"  current price: ${_num(_g(context, 'price', 'current'))}",
        f"  previous close: ${_num(_g(context, 'price', 'prev_close'))}",
        f"  change today: {_num(_g(context, 'price', 'day_change_pct'))}%",
        "",
        "RETURNS:",
        f"  1 day: {_num(_g(context, 'returns', '1d'))}%"
        f"   5 days: {_num(_g(context, 'returns', '5d'))}%"
        f"   1 month: {_num(_g(context, 'returns', '1m'))}%"
        f"   year to date: {_num(_g(context, 'returns', 'ytd'))}%",
        "",
        "FUNDAMENTALS:",
        f"  P/E ratio: {_num(f.get('pe'))}"
        f"   forward P/E: {_num(f.get('forward_pe'))}",
        f"  market cap: {_big_money(f.get('market_cap'))}",
        f"  profit margin: {_ratio_pct(f.get('profit_margin'))}"
        f"   revenue growth: {_ratio_pct(f.get('revenue_growth'))}",
        f"  debt-to-equity: {_num(f.get('debt_to_equity'))}",
        "",
        "TECHNICALS:",
        f"  RSI (14-day): {_num(_g(context, 'technicals', 'rsi_14'))}"
        f"   ATR: {_num(_g(context, 'technicals', 'atr'))}",
        f"  50-day moving average: ${_num(_g(context, 'technicals', 'sma_50'))}"
        f"   200-day moving average: ${_num(_g(context, 'technicals', 'sma_200'))}",
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

# The five turns, in order, as (key, human label). Exposed so the UI can show
# the real shape of the work BEFORE it starts — "~5 model calls" is the single
# most impressive fact about this engine and the interface used to never say it.
STAGES = (
    ("bull_opening", "Bull analyst builds the opening case"),
    ("bear_opening", "Bear analyst responds"),
    ("bull_rebuttal", "Bull rebuts"),
    ("bear_rebuttal", "Bear rebuts"),
    ("judge", "Judge weighs the exchange"),
)


def run_debate(context: dict, on_stage=None) -> dict:
    """Run the five-turn Bull vs Bear debate and return the strict output schema.

    In mock mode (llm.use_mock()) this returns mock_debate.json — NO API call is made.
    The fixture was recorded for one ticker only; see `recorded_for` in the result.

    `on_stage(index, key, label, done)` is called around each of the five real
    calls: once with done=False as the call starts, once with done=True when it
    returns. It exists so the UI can report ACTUAL progress. The tab previously
    faked this with three `time.sleep(0.7)` calls AFTER all five calls had
    already completed — 2.1 seconds of theatre charged to the user for data that
    was already in hand, while the 25 seconds of real work showed one spinner.
    """
    context = context or {}
    ticker = context.get("ticker") or "?"

    def _stage(i, done=False):
        if on_stage is not None:
            key, label = STAGES[i]
            try:
                on_stage(i, key, label, done)
            except Exception:  # noqa: BLE001 — progress reporting never breaks a run
                pass

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
    _stage(0)
    bull_open = _pick(
        llm.call_json(_load("bull_opening").format(ticker=ticker, context=ctx), user),
        "opening",
    )
    _stage(0, done=True)

    # 2. Bear opening — sees the context + bull opening.
    _stage(1)
    bear_open = _pick(
        llm.call_json(
            _load("bear_opening").format(ticker=ticker, context=ctx, bull=_dumps(bull_open)),
            user,
        ),
        "opening",
    )
    _stage(1, done=True)

    # 3. Bull rebuttal — sees the context + both openings.
    _stage(2)
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
    _stage(2, done=True)

    # 4. Bear rebuttal — sees the context + both openings + bull rebuttal.
    _stage(3)
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
    _stage(3, done=True)

    # 5. Judge — sees everything and scores it.
    _stage(4)
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
    _stage(4, done=True)

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
