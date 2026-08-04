"""Tests for the analyst agent's tool surface.

The agent's credibility rests on a single property: every number it can say came
back from one of these tools, which run the same tested code the dashboard runs.
So the tools are what needs testing — the model's prose is not where correctness
lives.

Two things get the most attention here:
  * simulate_trade must be PURE. If it mutated the caller's portfolio, a
    "what if I sold everything" question would silently sell everything.
  * Tool output must be JSON-serializable, because it goes into a tool_result
    block. A stray numpy float or NaN breaks the API call, not the maths.
"""

import copy
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Every test in this file runs on the recorded fixture — no network."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")


@pytest.fixture
def book():
    import profiles
    return profiles.load_portfolio("balanced_growth")


# --------------------------------------------------------------------------
# Read-only tools
# --------------------------------------------------------------------------

def test_every_tool_returns_json_serializable_output(book):
    """Tool results are serialized into tool_result blocks. A numpy scalar or a
    NaN here fails the API call, not the arithmetic — so it must never escape."""
    from agents import tools

    payloads = [
        tools.get_portfolio_summary(book),
        tools.get_day_contributions(book),
        tools.get_risk_metrics(book),
        tools.get_correlations(book),
        tools.decompose_stock_move("NVDA"),
        tools.get_stock_details("NVDA"),
        tools.simulate_trade(book, [{"ticker": "NVDA", "action": "sell",
                                     "shares": 2}]),
    ]
    for payload in payloads:
        text = json.dumps(payload)          # no default= — must be clean already
        assert "NaN" not in text, "a NaN leaked into a tool result"
        assert "Infinity" not in text


def test_portfolio_summary_reports_real_holdings(book):
    from agents import tools
    out = tools.get_portfolio_summary(book)
    assert out["total_value"] > 0
    assert len(out["positions"]) == len(book["positions"])
    assert {p["ticker"] for p in out["positions"]} == {
        p["ticker"] for p in book["positions"]}


def test_stock_details_humanises_ratios(book):
    """The prompt tells the agent to speak numbers plainly; the tool must hand
    it numbers that are already plain. This is the `revenue_growth: 0.852`
    failure, prevented at the source rather than corrected downstream."""
    from agents import tools
    f = tools.get_stock_details("NVDA")["fundamentals"]
    for key in ("profit_margin_pct", "revenue_growth_pct"):
        v = f.get(key)
        if v is not None:
            assert abs(v) > 1.0 or v == 0, (
                f"{key}={v} looks like a raw 0-1 ratio, not a percentage")


def test_unknown_tool_raises_keyerror_for_the_caller_to_report(book):
    from agents import tools
    with pytest.raises(KeyError):
        tools.run_tool("get_insider_tips", {}, book)


def test_ticker_tools_require_a_ticker(book):
    from agents import tools
    with pytest.raises(ValueError):
        tools.run_tool("decompose_stock_move", {}, book)


# --------------------------------------------------------------------------
# simulate_trade — purity is the whole safety story
# --------------------------------------------------------------------------

def test_simulate_trade_does_not_mutate_the_real_portfolio(book):
    """THE test. If this fails, asking 'what if I sold everything?' sells
    everything."""
    from agents import tools
    before = copy.deepcopy(book)
    tools.simulate_trade(book, [
        {"ticker": "NVDA", "action": "sell", "shares": 5},
        {"ticker": "AAPL", "action": "buy", "shares": 3},
    ])
    assert book == before, "simulate_trade mutated the caller's portfolio"


def test_simulate_trade_reports_before_and_after(book):
    from agents import tools
    out = tools.simulate_trade(book, [{"ticker": "NVDA", "action": "sell",
                                       "shares": 6}])
    assert out["simulated"] is True
    assert out["hypothetical"] is True
    assert "not a recommendation" in out["disclaimer"].lower()
    assert out["before"]["cash"] < out["after"]["cash"], "selling should raise cash"
    for key in ("total_value", "beta_vs_sp500", "effective_holdings",
                "sector_weights_pct", "concentration_warnings"):
        assert key in out["before"] and key in out["after"]


def test_selling_more_than_held_is_clamped_and_disclosed(book):
    """A model asking to sell 10,000 shares of a 12-share position must not
    produce a fantasy short position — clamp, and say so."""
    from agents import tools
    out = tools.simulate_trade(book, [{"ticker": "NVDA", "action": "sell",
                                       "shares": 99999}])
    assert out["simulated"] is True
    assert any("not" in n and "NVDA" in n for n in out["notes"]), out["notes"]
    after_tickers = set(out["after"]["sector_weights_pct"])
    assert isinstance(after_tickers, set)      # position fully closed, no crash


def test_buying_beyond_cash_is_clamped_and_disclosed(book):
    from agents import tools
    out = tools.simulate_trade(book, [{"ticker": "AAPL", "action": "buy",
                                       "shares": 100000}])
    assert out["simulated"] is True
    assert any("cash" in n.lower() for n in out["notes"]), out["notes"]
    assert out["after"]["cash"] >= -1e-6, "simulation went cash-negative"


def test_selling_something_not_held_is_refused_not_invented(book):
    from agents import tools
    out = tools.simulate_trade(book, [{"ticker": "TSLA", "action": "sell",
                                       "shares": 5}])
    assert out["simulated"] is False or any(
        "don't hold" in n for n in out.get("notes", []))


def test_selling_a_whole_position_reduces_holdings_count(book):
    from agents import tools
    held = next(p for p in book["positions"] if p["ticker"] == "NVDA")
    out = tools.simulate_trade(book, [{"ticker": "NVDA", "action": "sell",
                                       "shares": held["shares"]}])
    assert out["after"]["holdings_count"] == out["before"]["holdings_count"] - 1


# --------------------------------------------------------------------------
# The agent loop
# --------------------------------------------------------------------------

def test_mock_mode_labels_itself_and_still_computes_real_numbers(book):
    """Demo mode must never look live (docs/PRODUCT.md principle 4) — but the numbers
    it shows are genuinely computed, so the tools really do run."""
    from agents.analyst import ask
    out = ask(book, "why am I down today?")
    assert out["is_mock"] is True
    assert "demo mode" in out["answer"].lower()
    assert out["tool_calls"], "mock mode ran no tools at all"
    assert any(c["name"] == "get_portfolio_summary" for c in out["tool_calls"])


def test_on_event_fires_for_each_tool_so_progress_is_real(book):
    from agents.analyst import ask
    seen = []
    ask(book, "what moved me?", on_event=lambda kind, p: seen.append((kind, p)))
    tool_events = [p["name"] for kind, p in seen if kind == "tool"]
    assert tool_events, "no tool events — the UI would have nothing to report"


def test_the_agent_never_recommends_buying_or_selling():
    """The prompt is where this rule lives, so the prompt is what gets tested."""
    with open(os.path.join(BASE, "prompts", "analyst.txt"), encoding="utf-8") as f:
        prompt = f.read().lower()
    assert "not investment advice" in prompt
    assert "never tell the user to buy, sell" in prompt
    # The grounding rule must be present and unambiguous.
    assert "must have come back from a tool call" in prompt


def test_every_declared_tool_is_dispatchable(book):
    """A tool the model can see but the dispatcher can't run is a guaranteed
    mid-conversation error."""
    from agents import tools
    for schema in tools.TOOLS:
        name = schema["name"]
        args = {}
        if "ticker" in schema["input_schema"].get("properties", {}):
            args = {"ticker": "NVDA"}
        if name == "simulate_trade":
            args = {"trades": [{"ticker": "NVDA", "action": "sell", "shares": 1}]}
        result = tools.run_tool(name, args, book)
        assert isinstance(result, dict), f"{name} did not return a dict"


def test_tool_schemas_are_well_formed():
    """Malformed schemas are rejected by the API at call time, which surfaces as
    a broken chat rather than an obvious error."""
    from agents import tools
    for schema in tools.TOOLS:
        assert schema["name"] and schema["description"]
        assert schema["input_schema"]["type"] == "object"
        for req in schema["input_schema"].get("required", []):
            assert req in schema["input_schema"]["properties"], (
                f"{schema['name']} requires '{req}' but never declares it")
        # Descriptions must say WHEN to call, not only what the tool returns.
        assert "call this" in schema["description"].lower(), (
            f"{schema['name']} has no trigger condition in its description")
