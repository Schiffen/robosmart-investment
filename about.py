"""about.py — the "What is this?" dialog.

WHY A DIALOG AND NOT A FIFTH VIEW
---------------------------------
The router already carries four items and, measured at 390px, wraps to two
rows. A fifth would push it to three rows of chrome above the content on the
narrowest screen — paying the permanent cost of a nav slot for a panel each
reader opens once. A dialog costs one sidebar button and nothing on the page.

THREE THINGS ABOUT st.dialog THAT ARE NOT OBVIOUS
-------------------------------------------------
All three verified against Streamlit 1.60 rather than assumed, because each
one fails quietly rather than loudly.

1. A DIALOG DOES NOT SURVIVE A RERUN. It has no open/closed state of its own —
   it exists only for the script run in which the decorated function is called.
   `if st.button("About"): _about()` therefore gives you a dialog that vanishes
   the next time anything reruns, and in THIS app the view router reruns on
   every sidebar interaction. So the open state has to live in session_state
   and be re-asserted on each run.

2. on_dismiss DEFAULTS TO "ignore", which closes the dialog CLIENT-SIDE with no
   rerun. Combined with (1) that produces a genuinely confusing bug: the flag
   in session_state is still True, so the dialog reappears the next time
   anything else causes a rerun. It reads as a modal that will not stay shut.
   The dismissal has to clear the flag, hence the callback.

3. IT RENDERS OUTSIDE `section.stMain`, in a portal. This app's entire CSS
   layer is scoped to `section.stMain` (deliberately — see theme.py rule 0 on
   the stAppScrollToBottomContainer rename), so NONE of it reaches inside a
   dialog. That is why everything below is built from native Streamlit
   elements: they pick up .streamlit/config.toml, which is global, instead of
   depending on app CSS that stops at the portal boundary.
"""

from __future__ import annotations

import streamlit as st

import brand

_FLAG = "show_about"

# One entry per router view, in router order. Each says what the view COMPUTES,
# not what it is "for" — a reader deciding where to click needs the output, and
# an evaluator reading it cold needs to know the numbers are derived rather
# than asserted.
VIEWS = [
    (":material/analytics:", "Dashboard",
     "Your book, priced and decomposed. Total value and today's move, the "
     "holding that caused that move, a sector breakdown, a correlation matrix "
     "between your holdings, per-holding contribution to the day, and a "
     "one-year backtest of your current weights against the S&P 500. Every "
     "figure is computed from prices — none of it is model-authored."),
    (":material/forum:", "Ask the analyst",
     "A question-answering agent with seven tools over your actual holdings. "
     "It is given NO portfolio data in its prompt, so every number it states "
     "has to come back from a tool call it chose to make. The "
     "“How I worked this out” panel lists the calls it ran, which is what "
     "makes the grounding checkable instead of merely claimed. It declines to "
     "give investment advice."),
    (":material/balance:", "Bull vs Bear",
     "Two analysts argue over the selected stock and a third judges them. "
     "Five model calls: each side opens with claims and evidence, each "
     "rebuts the other, then a judge picks a side, states a confidence, names "
     "the weakest claim on BOTH sides and says what would falsify the "
     "verdict. The disagreement is the point — a single summary hides it."),
    (":material/troubleshoot:", "What Happened Today",
     "Splits one stock's daily move into three parts by ordinary least "
     "squares: how much was the whole market, how much was its sector, and "
     "how much was the stock itself. Only the leftover — the part the market "
     "and sector do not explain — is handed to a model to explain from the "
     "day's news, and it is allowed to answer “no clear cause found”."),
]


def open_button(*, key: str = "about_btn") -> None:
    """Render the trigger. Safe to call from inside `with st.sidebar:`."""
    if st.button(":material/help: What is this?", key=key,
                 use_container_width=True,
                 help="What each view computes, and how to drive the app."):
        st.session_state[_FLAG] = True


def maybe_render() -> None:
    """Re-assert the dialog on every run while the flag is set. See note 1."""
    if st.session_state.get(_FLAG):
        _dialog()


def _dismiss() -> None:
    """Clear the flag when the reader closes the dialog. See note 2."""
    st.session_state[_FLAG] = False


@st.dialog("About this app", width="large", on_dismiss=_dismiss)
def _dialog() -> None:
    st.markdown(
        f"**{brand.PRODUCT}** takes a stock portfolio and runs four different "
        f"analyses over it — three that compute, and two that argue. It is a "
        f"university project built to show an AI layer that is *grounded*: "
        f"every number on screen comes from market data or from a tool call, "
        f"never from a model's memory."
    )
    st.caption("Educational university project. **This is not investment advice.**")

    st.divider()
    st.markdown("#### The four views")
    for icon, name, what in VIEWS:
        st.markdown(f"{icon} **{name}** — {what}")

    st.divider()
    st.markdown("#### Driving it")
    st.markdown(
        "- **Pick a view** with the row of buttons under the title.\n"
        "- **Switch investor** from the sidebar. Five sample books run through "
        "one engine and reach five different verdicts — that contrast is what "
        "they are there to show.\n"
        "- **Load your own** portfolio from the sidebar: a CSV of "
        "`ticker,shares,cost_basis`, with an optional `sector` column and an "
        "optional `CASH` row. A template is downloadable there.\n"
        "- **Choose the stock** that Bull vs Bear and What Happened Today "
        "analyse, using the sidebar selector.\n"
        "- **Change the time window** on the performance chart with the "
        "`1M / 3M / 6M / YTD / 1Y` buttons above it. `1Y` is the view it "
        "starts on, so it is also the reset — one tap returns you to where "
        "you began.\n"
        "- **On a phone**, open the sidebar from the top-left arrows and tap "
        "anywhere outside it to close it again."
    )

    st.divider()
    st.markdown("#### Reading the line under the title")
    st.markdown(
        "Everything here is **close-to-close**, so “today's move” is the last "
        "settled close against the one before it. On a Monday morning the "
        "current price is Friday's, and the date in that line says which close "
        "you are actually looking at. It also states whether prices are **live** "
        "or a **recorded snapshot** — recorded data must never be able to look "
        "live, which is why the source is named rather than implied."
    )

    if st.button("Close", type="primary", key="about_close"):
        _dismiss()
        st.rerun()
