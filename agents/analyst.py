"""
agents/analyst.py — the tool-using analyst agent.
=================================================
A manual tool-use loop over agents/tools.py. This is the app's one piece of
genuinely agentic AI: unlike the debate (a fixed five-call chain) and the
explainer (one call), the analyst DECIDES which questions to ask and how many
turns to take.

Manual loop rather than the SDK's tool runner, for one reason: the UI reports
each tool call as it happens ("Checking what moved you today…"), which needs a
hook between the model choosing a tool and the tool running. The runner has
per-turn hooks, but it is a beta surface and this loop is ~40 lines.

What keeps this honest:
  * The model is given NO portfolio data in its prompt. Every figure has to come
    back from a tool call, so it cannot recite a number it was handed.
  * `max_iterations` bounds the loop. A model that keeps calling tools stops.
  * Tool errors are returned to the model as `is_error` results rather than
    raised, so it can recover or say it could not find out.
  * Nothing here writes to session state. `simulate_trade` returns a
    hypothetical; only the user can apply one.

Mock mode: with no API key (or USE_MOCK=1) this returns a canned reply that says
so, rather than pretending. The three tools the reply is based on ARE run, so
the demo still shows real computed numbers.
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents import llm, tools as agent_tools

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "analyst.txt")

# Bounds the agentic loop. Five turns is comfortably more than any question the
# tool surface supports needs (the deepest realistic chain is summary ->
# contributions -> decompose -> details), while still terminating on a model
# that will not stop calling tools.
MAX_ITERATIONS = 5

# Generous, because on current models `max_tokens` caps thinking AND response
# text together — a tight budget can spend the whole allowance on thinking and
# truncate the answer mid-sentence.
MAX_TOKENS = 8000


def _system_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def _mock_answer(portfolio: dict, question: str, on_event=None) -> dict:
    """No API key: run the tools for real, then say plainly that the wording is
    canned. Recorded output that looks live is the failure this codebase exists
    to design against (docs/PRODUCT.md principle 4), so it is labelled, not hidden."""
    calls = []
    for name in ("get_portfolio_summary", "get_day_contributions"):
        if on_event:
            on_event("tool", {"name": name, "input": {}})
        try:
            result = agent_tools.run_tool(name, {}, portfolio)
        except Exception as e:  # noqa: BLE001
            result = {"error": str(e)}
        calls.append({"name": name, "input": {}, "result": result})

    summary = calls[0]["result"]
    contrib = calls[1]["result"]
    bits = []
    if summary.get("total_value") is not None:
        bits.append(
            f"The book is worth ${summary['total_value']:,.2f} right now, "
            f"across {len(summary.get('positions') or [])} holdings plus "
            f"${(summary.get('cash') or 0):,.2f} in cash.")
    if contrib.get("available") and contrib.get("contributions"):
        top = contrib["contributions"][0]
        verb = "added" if (top["contribution_pct"] or 0) >= 0 else "cost you"
        bits.append(
            f"Today {top['ticker']} {verb} "
            f"{abs(top['contribution_pct']):.2f}% of the portfolio's move — it "
            f"moved {top['own_move_pct']:+.2f}% and is "
            f"{top['weight_pct_of_equity']:.0f}% of what you hold.")
    bits.append(
        "This is demo mode: the figures above are really computed from your "
        "loaded portfolio, but the wording is canned because no API key is set. "
        "Set ANTHROPIC_API_KEY to ask the analyst your own questions.")

    return {"answer": " ".join(bits), "tool_calls": calls,
            "is_mock": True, "iterations": 0, "stopped_early": False}


def ask(portfolio: dict, question: str, history: list | None = None,
        on_event=None) -> dict:
    """Answer one question about `portfolio`, using tools.

    `history` is prior [{"role", "content"}] turns as plain text, so follow-ups
    ("what about the second one?") resolve. `on_event(kind, payload)` is called
    with ("tool", {...}) as each tool call starts and ("thinking", {...}) between
    model turns, so the UI can report real progress instead of a spinner.

    Returns {answer, tool_calls, is_mock, iterations, stopped_early}.
    """
    portfolio = portfolio or {}
    if llm.use_mock():
        return _mock_answer(portfolio, question, on_event)

    messages = []
    for turn in (history or []):
        role, content = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    client = llm._client()
    system = _system_prompt()
    executed = []
    stopped_early = False
    response = None
    turns = 0

    for iteration in range(MAX_ITERATIONS):
        turns = iteration + 1
        if on_event:
            on_event("thinking", {"iteration": iteration})

        response = client.messages.create(
            model=llm.MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=agent_tools.TOOLS,
            messages=messages,
        )

        # A safety classifier can decline; content is empty or partial.
        if response.stop_reason == "refusal":
            return {"answer": "I can't answer that one. Try asking about your "
                              "holdings, your risk, or what moved you today.",
                    "tool_calls": executed, "is_mock": False,
                    "iterations": iteration + 1, "stopped_early": True}

        if response.stop_reason != "tool_use":
            break

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        # The assistant turn must be appended WITH its tool_use blocks, or the
        # tool_result blocks below have nothing to pair against.
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in tool_uses:
            if on_event:
                on_event("tool", {"name": block.name, "input": block.input})
            try:
                payload = agent_tools.run_tool(block.name, block.input, portfolio)
                is_error = False
            except KeyError:
                payload = {"error": f"No tool named {block.name}."}
                is_error = True
            except Exception as e:  # noqa: BLE001 — hand the model the failure
                payload = {"error": str(e)}
                is_error = True

            executed.append({"name": block.name, "input": dict(block.input or {}),
                             "result": payload})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(payload, default=str),
                "is_error": is_error,
            })

        # ALL results go back in ONE user message. Splitting them across several
        # messages trains the model out of calling tools in parallel.
        messages.append({"role": "user", "content": results})
    else:
        # Loop exhausted while the model still wanted tools.
        stopped_early = True

    answer = ""
    if response is not None:
        answer = "\n\n".join(b.text for b in response.content
                             if getattr(b, "type", "") == "text" and b.text).strip()

    if not answer:
        answer = ("I couldn't put an answer together for that one. Try asking "
                  "about your holdings, your risk, or what moved you today.")

    return {"answer": answer, "tool_calls": executed, "is_mock": False,
            "iterations": turns, "stopped_early": stopped_early}
