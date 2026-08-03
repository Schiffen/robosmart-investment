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
import theme

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
    """The header trigger, beside the export.

    Both actions are global — this explains all four views, the export carries
    all four — so they belong next to the product name rather than in the
    sidebar among the controls that change what is on screen. A reader looking
    for "what am I looking at" looks up, not down a list of portfolios.
    """
    if st.button(":material/explore: Guide", key=key,
                 use_container_width=True,
                 help="A map of the app: what each view computes and how to "
                      "drive it."):
        st.session_state[_FLAG] = True


def maybe_render() -> None:
    """Re-assert the dialog on every run while the flag is set. See note 1."""
    if st.session_state.get(_FLAG):
        _dialog()


def _dismiss() -> None:
    """Clear the flag when the reader closes the dialog. See note 2."""
    st.session_state[_FLAG] = False


@st.dialog("Guide", width="large", on_dismiss=_dismiss)
def _dialog() -> None:
    # The mirror opens it. This is the one surface in the app with room for the
    # ceremonial mark — LOGOS.md gives it splash and title pages, bans it from
    # mastheads, and it is the mark that SAYS what the product is about: every
    # claim answered by its opposite. Decorative here, so alt="" and
    # aria-hidden; the heading beside it carries the name in text.
    st.markdown(
        f"<div style='display:flex;justify-content:center;padding:.2rem 0 1rem'>"
        f"{brand.logo('mirror', 96, alt='')}</div>",
        unsafe_allow_html=True)

    st.markdown(
        f"<p style='text-align:center;color:{theme.INK_2};font-size:1.02rem;"
        f"line-height:1.6;max-width:60ch;margin:0 auto 1.4rem'>"
        f"Four ways to look at one portfolio — three that <b>compute</b>, and "
        f"two that <b>argue</b>. Every number on screen comes from market data "
        f"or from a tool call, never from a model's memory.</p>",
        unsafe_allow_html=True)

    # ---- The map ---------------------------------------------------------
    # A two-column grid of real cards, not a bulleted list. The reader's
    # question here is "which of these four do I want", which is a COMPARISON —
    # and a comparison read down a single column of prose is the one shape that
    # makes it hard. Cards put them side by side, in router order, so the map
    # matches the control it describes.
    st.markdown(f"<div class='rs-guide-head'>The four views</div>",
                unsafe_allow_html=True)
    for row in (VIEWS[:2], VIEWS[2:]):
        cols = st.columns(2, gap="medium")
        for col, (icon, name, what) in zip(cols, row):
            with col:
                st.markdown(
                    f"<div class='rs-guide-card'>"
                    f"<div class='rs-guide-title'>{name}</div>"
                    f"<div class='rs-guide-body'>{what}</div></div>",
                    unsafe_allow_html=True)

    # ---- Driving it ------------------------------------------------------
    st.markdown("<div class='rs-guide-head'>Driving it</div>",
                unsafe_allow_html=True)
    steps = [
        ("Pick a view", "the row of buttons under the title."),
        ("Switch investor", "five sample books in the sidebar. One engine "
                            "reaches five different verdicts — that contrast "
                            "is what they are there to show."),
        ("Load your own", "a CSV of <code>ticker,shares,cost_basis</code>, "
                          "with an optional <code>sector</code> column and an "
                          "optional <code>CASH</code> row. Template in the "
                          "sidebar."),
        ("Choose the stock", "the sidebar selector drives both Bull vs Bear "
                             "and What Happened Today."),
        ("Change the window", "<code>1M / 3M / 6M / YTD / 1Y</code> above the "
                              "performance chart. <b>1Y is where it starts, so "
                              "it is also the reset</b> — one tap back to the "
                              "beginning."),
        ("Export", "the button beside this one builds a branded PDF of "
                   "everything the app currently knows — charts, tables and "
                   "any debate you have run."),
    ]
    st.markdown(
        "<ol class='rs-guide-steps'>"
        + "".join(f"<li><b>{t}</b> — {d}</li>" for t, d in steps)
        + "</ol>", unsafe_allow_html=True)

    # ---- The one thing worth reading twice --------------------------------
    st.markdown("<div class='rs-guide-head'>The line under the title</div>",
                unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:{theme.INK_2};line-height:1.6;max-width:68ch'>"
        f"Everything here is <b>close-to-close</b>, so “today's move” is the "
        f"last settled close against the one before it — on a Monday morning "
        f"the current price is Friday's. That line names the date you are "
        f"actually looking at, and whether prices are <b>live</b> or a "
        f"<b>recorded snapshot</b>. Recorded data must never be able to look "
        f"live, so the source is stated rather than implied.</p>",
        unsafe_allow_html=True)

    st.caption("Educational university project. **This is not investment advice.**")

    if st.button("Start exploring", type="primary", key="about_close",
                 use_container_width=True):
        _dismiss()
        st.rerun()
