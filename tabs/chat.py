"""
tabs/chat.py — "Ask the analyst" (the tool-using agent view).
=============================================================
RENDER ONLY. The agent lives in agents/analyst.py; this file drives the UX.

The design job here is making the agent's work VISIBLE. A chat box that returns
a paragraph is indistinguishable from a model making things up — and this
product's whole claim is that it doesn't. So every answer carries the tool calls
that produced it, named in plain language, expandable to the raw figures that
came back. That turns "trust me" into "here is what I looked at", and it is the
same groundedness argument the debate makes with its cited claims.

Progress is reported from the REAL tool boundaries via the agent's on_event
callback — never a fake staged spinner.
"""

from __future__ import annotations

import json

import streamlit as st

import theme
from agents.analyst import ask

# Plain-language labels for the tool names. A user watching the agent work
# should read "Checking what moved you today", not `get_day_contributions`.
_TOOL_LABEL = {
    "get_portfolio_summary": "Reading your holdings",
    "get_day_contributions": "Checking what moved you today",
    "get_risk_metrics": "Measuring your risk",
    "get_correlations": "Checking how your holdings move together",
    "decompose_stock_move": "Splitting the move into market, sector and company",
    "get_stock_details": "Pulling the company's numbers and headlines",
    "simulate_trade": "Recomputing your book under that change",
}

_STARTERS = [
    "Why is my portfolio down today?",
    "How risky is this portfolio, really?",
    "Am I actually diversified?",
    "What if I sold half my largest holding?",
]


def _label(name: str, tool_input: dict | None = None) -> str:
    label = _TOOL_LABEL.get(name, name)
    ticker = (tool_input or {}).get("ticker")
    if ticker:
        return f"{label} ({str(ticker).upper()})"
    return label


def _render_tool_trace(tool_calls: list) -> None:
    """The receipts.

    OPEN by default, and that is a deliberate reversal. "Collapsed — the
    beginner wants the answer, the evaluator wants to see it is real" sounded
    like progressive disclosure, but it hid the single strongest piece of
    evidence this project has: the agent choosing tools, and every figure it
    states being traceable to a computed return. One click away is, in
    practice, invisible — nobody opens the expander during a five-minute demo,
    so the grounding was claimed rather than shown.

    The compromise that keeps the beginner's reading intact: the answer is
    still ABOVE this, and what opens is a summary strip of which tools ran. The
    raw JSON stays one level deeper, where it belongs.
    """
    if not tool_calls:
        return
    n = len(tool_calls)

    # Visible without any interaction at all — even if the reader collapses the
    # section below, they have already seen that real calls happened.
    names = " ".join(f":blue-badge[{_label(c.get('name'), c.get('input'))}]"
                     for c in tool_calls)
    st.markdown(names)

    with st.expander(f"How I worked this out · {n} "
                     f"{'calculation' if n == 1 else 'calculations'} on your "
                     f"real portfolio",
                     expanded=True, icon=":material/function:"):
        st.caption(
            "Every figure in the answer came from these. The analyst has no "
            "market data of its own — it can only report what these returned."
        )
        for call in tool_calls:
            st.markdown(f"**{_label(call.get('name'), call.get('input'))}**")
            result = call.get("result")
            try:
                body = json.dumps(result, indent=2, default=str)
            except Exception:  # noqa: BLE001
                body = str(result)
            if len(body) > 4000:
                body = body[:4000] + "\n… (truncated)"
            st.code(body, language="json")


def render(portfolio: dict) -> None:
    if not portfolio or not portfolio.get("positions"):
        st.info("Load a portfolio from the sidebar and I can answer questions "
                "about it.")
        return

    st.header("Ask the analyst")
    st.markdown(
        "Ask about your holdings, your risk, or what moved you today. The "
        "analyst runs real calculations on **your** portfolio to answer — it "
        "has no figures of its own, so it can't invent one."
    )
    st.caption("Educational only. The analyst will not tell you what to buy or sell.")

    history = st.session_state.setdefault("analyst_history", [])

    # ---- Starters (only before the first question) ------------------------
    pending = None
    if not history:
        theme.section("Try one of these")
        cols = st.columns(2)
        for i, starter in enumerate(_STARTERS):
            if cols[i % 2].button(starter, key=f"starter_{i}",
                                  use_container_width=True):
                pending = starter

    # ---- Transcript -------------------------------------------------------
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(theme.safe_md(turn["content"])
                        if turn["role"] == "assistant" else turn["content"])
            if turn["role"] == "assistant":
                _render_tool_trace(turn.get("tool_calls") or [])

    typed = st.chat_input("Ask about your portfolio…")
    question = typed or pending
    if not question:
        return

    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # ---- Run the agent ----------------------------------------------------
    with st.chat_message("assistant"):
        status = st.empty()
        steps: list[str] = []

        def _on_event(kind: str, payload: dict) -> None:
            """Real progress, from the agent's actual tool boundaries."""
            if kind == "tool":
                steps.append(_label(payload.get("name"), payload.get("input")))
                status.caption(" · ".join(steps[-3:]) + " …")
            elif kind == "thinking" and not steps:
                status.caption("Working out what to check …")

        # `history[:-1]` — the current question is passed separately, so
        # including it here too would duplicate the user turn.
        try:
            result = ask(portfolio, question, history=history[:-1],
                         on_event=_on_event)
        except Exception as e:  # noqa: BLE001 — never crash the view
            status.empty()
            st.error(
                f"I couldn't reach the analyst: {e}\n\n"
                f"Your portfolio and the other views are unaffected — "
                f"ask again to retry."
            )
            history.pop()          # don't strand a question with no reply
            return

        status.empty()
        answer = result.get("answer") or ""
        st.markdown(theme.safe_md(answer))

        if result.get("is_mock"):
            st.caption("🧪 Demo mode — no API key set, so the wording is "
                       "recorded. The figures are computed live from your book.")
        if result.get("stopped_early"):
            st.caption("I stopped after several rounds of checking — the answer "
                       "above may be partial.")

        _render_tool_trace(result.get("tool_calls") or [])

    history.append({"role": "assistant", "content": answer,
                    "tool_calls": result.get("tool_calls") or []})

    if len(history) >= 2:
        _, right = st.columns([5, 1])
        with right:
            if st.button("Clear chat", use_container_width=True):
                st.session_state["analyst_history"] = []
                st.rerun()
