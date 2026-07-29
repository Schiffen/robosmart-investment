"""
tabs/debate.py — the "Bull vs Bear" tab (Person 3).
===================================================
RENDER ONLY. The debate itself is produced by agents/debate.run_debate(); this
file just drives the UX: a start button, a progressive stage-by-stage reveal
(the build-up IS the demo), the two-column bull/bear layout, and the judge card.

Entry point (fixed signature — do not change):
    def render(context: dict) -> None

Nothing runs until the user clicks "Start the Debate". The result is cached in
st.session_state keyed by ticker, so switching tabs does not re-run it. All
colours come from the shared theme; raw JSON is NEVER shown to the user.
"""

from __future__ import annotations

import time

import streamlit as st

import theme
from agents.debate import run_debate


# --------------------------------------------------------------------------
# Small render helpers
# --------------------------------------------------------------------------

def _side_header(label: str, color: str) -> None:
    st.markdown(
        f"<h4 style='color:{color};margin:0 0 .35rem 0'>{label}</h4>",
        unsafe_allow_html=True,
    )


def _render_opening(opening: dict, color: str) -> None:
    """Thesis + a bordered container per claim (text, muted evidence, pill)."""
    opening = opening or {}
    thesis = opening.get("thesis")
    if thesis:
        st.markdown(
            f"<div style='color:{theme.INK};font-style:italic;"
            f"border-left:3px solid {color};padding:.15rem 0 .15rem .6rem;"
            f"margin-bottom:.6rem'>{thesis}</div>",
            unsafe_allow_html=True,
        )

    claims = opening.get("claims") or []
    if not claims:
        st.caption("No claims returned for this side.")
        return

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        with st.container(border=True):
            st.markdown(f"**{claim.get('claim', '')}**")
            evidence = claim.get("evidence")
            if evidence:
                st.markdown(
                    f"<span style='color:{theme.MUTED};font-size:13px'>"
                    f"{evidence}</span>",
                    unsafe_allow_html=True,
                )
            strength = str(claim.get("strength") or "medium").lower()
            st.markdown(theme.badge(strength.upper(), strength), unsafe_allow_html=True)


def _render_rebuttal(rebuttal: dict, color: str) -> None:
    """Each rebuttal point marked with what it is 'responding to:'."""
    rebuttal = rebuttal or {}
    points = rebuttal.get("points") or []
    if not points:
        st.caption("No rebuttal returned for this side.")
        return

    for point in points:
        if not isinstance(point, dict):
            continue
        with st.container(border=True):
            attacks = point.get("attacks")
            if attacks:
                st.markdown(
                    f"<span style='color:{theme.MUTED};font-size:12px;"
                    f"text-transform:uppercase;letter-spacing:.03em'>"
                    f"responding to:</span> "
                    f"<span style='color:{theme.INK_2};font-size:13px'>"
                    f"{attacks}</span>",
                    unsafe_allow_html=True,
                )
            counter = point.get("counter")
            if counter:
                st.markdown(counter)
            evidence = point.get("evidence")
            if evidence:
                st.markdown(
                    f"<span style='color:{color};font-size:12px'>▸ {evidence}</span>",
                    unsafe_allow_html=True,
                )


def _render_judge(judge: dict) -> None:
    """Full-width, visually distinct verdict card."""
    judge = judge or {}
    verdict = str(judge.get("verdict") or "inconclusive").lower()

    with st.container(border=True):
        st.markdown("### ⚖️ The Judge's Verdict")

        head_l, head_r = st.columns([1, 2])
        with head_l:
            st.markdown(
                "<div style='font-size:11px;color:{};text-transform:uppercase;"
                "letter-spacing:.04em;margin-bottom:.3rem'>Verdict</div>".format(theme.MUTED),
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<span style='font-size:20px'>"
                f"{theme.badge(verdict.upper(), verdict)}</span>",
                unsafe_allow_html=True,
            )
        with head_r:
            conf = judge.get("confidence")
            if isinstance(conf, (int, float)):
                conf_i = max(0, min(100, int(conf)))
                st.markdown(
                    "<div style='font-size:11px;color:{};text-transform:uppercase;"
                    "letter-spacing:.04em;margin-bottom:.3rem'>Confidence in the "
                    "verdict</div>".format(theme.MUTED),
                    unsafe_allow_html=True,
                )
                st.progress(conf_i / 100.0)
                st.markdown(
                    f"<div style='color:{theme.INK};font-weight:700'>{conf_i}%</div>",
                    unsafe_allow_html=True,
                )

        reasoning = judge.get("reasoning")
        if reasoning:
            st.markdown(
                f"<div style='color:{theme.INK_2};margin:.6rem 0'>{reasoning}</div>",
                unsafe_allow_html=True,
            )

        st.markdown("**Weakest argument on each side**")
        weak_l, weak_r = st.columns(2)
        with weak_l:
            st.markdown(
                f"<span style='color:{theme.GOOD};font-weight:700'>🐂 Weakest bull "
                f"claim</span>",
                unsafe_allow_html=True,
            )
            st.caption(judge.get("weakest_bull_claim") or "—")
        with weak_r:
            st.markdown(
                f"<span style='color:{theme.BAD};font-weight:700'>🐻 Weakest bear "
                f"claim</span>",
                unsafe_allow_html=True,
            )
            st.caption(judge.get("weakest_bear_claim") or "—")

        falsifiers = judge.get("falsifiers") or []
        st.markdown("**🔮 What would change my mind**")
        if falsifiers:
            items = "".join(
                f"<li style='margin-bottom:.3rem'>{f}</li>" for f in falsifiers
            )
            st.markdown(
                f"<ol style='color:{theme.INK_2};padding-left:1.2rem;margin:.2rem 0'>"
                f"{items}</ol>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("No falsifiers returned.")

        key_uncertainty = judge.get("key_uncertainty")
        if key_uncertainty:
            st.markdown(
                f"<div style='margin-top:.5rem;padding:.5rem .7rem;"
                f"border-left:3px solid {theme.WARN};background:{theme.SURFACE};"
                f"color:{theme.INK_2}'>"
                f"<b style='color:{theme.WARN}'>Key uncertainty:</b> "
                f"{key_uncertainty}</div>",
                unsafe_allow_html=True,
            )


def _stage(fresh: bool, label: str, done_label: str, seconds: float = 0.7) -> None:
    """Show a short status spinner between reveals — only on a fresh run."""
    if not fresh:
        return
    with st.status(label, expanded=False) as status:
        time.sleep(seconds)
        status.update(label=done_label, state="complete")


def _render_debate(result: dict, fresh: bool) -> None:
    """Progressive reveal: openings -> rebuttals -> judge."""
    bull = result.get("bull") or {}
    bear = result.get("bear") or {}
    judge = result.get("judge") or {}

    # Demo mode serves one recorded debate. When the user is looking at a different
    # ticker, say so up front — the arguments below cite the recorded company's
    # numbers, and presenting them under another ticker would read as fabrication.
    recorded_for = result.get("recorded_for")
    if result.get("is_mock") and recorded_for and recorded_for != result.get("ticker"):
        st.warning(
            f"**Demo mode.** This is a recorded debate about **{recorded_for}**, shown "
            f"here because no API key is set. It is *not* an analysis of "
            f"**{result.get('ticker')}** — the claims below cite {recorded_for}'s figures. "
            f"Set `ANTHROPIC_API_KEY` to run a real debate on any ticker."
        )
    elif result.get("is_mock"):
        st.info(
            f"**Demo mode.** Recorded {recorded_for} debate — no API call was made. "
            f"Figures reflect when it was recorded, not today's prices."
        )

    # ---- Openings (bull, then bear) ---------------------------------------
    _stage(fresh, "🐂 Bull analyst is making the opening case...",
           "🐂 Bull opening ready")
    _stage(fresh, "🐻 Bear analyst is responding...",
           "🐻 Bear opening ready")

    st.markdown("#### Opening arguments")
    open_l, open_r = st.columns(2)
    with open_l:
        _side_header("🐂 Bull", theme.GOOD)
        _render_opening(bull.get("opening"), theme.GOOD)
    with open_r:
        _side_header("🐻 Bear", theme.BAD)
        _render_opening(bear.get("opening"), theme.BAD)

    st.divider()

    # ---- Rebuttals --------------------------------------------------------
    _stage(fresh, "⚔️ Rebuttals incoming...", "⚔️ Rebuttals ready")

    st.markdown("#### Rebuttals")
    reb_l, reb_r = st.columns(2)
    with reb_l:
        _side_header("🐂 Bull rebuts", theme.GOOD)
        _render_rebuttal(bull.get("rebuttal"), theme.GOOD)
    with reb_r:
        _side_header("🐻 Bear rebuts", theme.BAD)
        _render_rebuttal(bear.get("rebuttal"), theme.BAD)

    st.divider()

    # ---- Judge ------------------------------------------------------------
    _stage(fresh, "⚖️ The judge is deliberating...", "⚖️ Verdict reached")
    _render_judge(judge)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(context: dict) -> None:
    # ---- Empty state ------------------------------------------------------
    if not context or not context.get("ticker"):
        st.info("🔎 Pick a ticker from the sidebar to stage a Bull vs Bear debate "
                "on it.")
        return

    ticker = context.get("ticker")
    name = context.get("company_name") or ticker
    price = context.get("price") or {}

    # ---- Header -----------------------------------------------------------
    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.subheader(f"⚔️ Bull vs Bear — {name}")
        st.caption(f"{ticker} · two AI analysts argue from the SAME data; an "
                   f"impartial judge scores it.")
    with head_r:
        st.metric(
            "Price",
            theme.fmt_money(price.get("current")),
            delta=theme.fmt_pct(price.get("day_change_pct")),
            delta_color="normal",
        )

    st.divider()

    # ---- Cache keyed by ticker (survives tab switches) --------------------
    store = st.session_state.setdefault("debate_results", {})
    result = store.get(ticker)
    fresh = False

    # ---- Start / empty state ---------------------------------------------
    if result is None:
        if st.button("⚔️ Start the Debate", type="primary", use_container_width=True,
                     key=f"start_debate_{ticker}"):
            try:
                with st.spinner(f"Staging the {ticker} debate..."):
                    result = run_debate(context)
                store[ticker] = result
                fresh = True
            except Exception as e:  # noqa: BLE001 — never crash the tab
                st.error(f"Couldn't run the debate: {e}")
                return
        else:
            st.info("Press **Start the Debate** to watch the bull and bear argue "
                    "this ticker, then let the judge rule.")
            return

    # ---- Re-run control ---------------------------------------------------
    _, rerun_col = st.columns([5, 1])
    with rerun_col:
        if st.button("🔄 Re-run", key=f"rerun_debate_{ticker}",
                     help="Discard this debate and run a fresh one."):
            store.pop(ticker, None)
            st.rerun()

    # ---- Reveal -----------------------------------------------------------
    try:
        _render_debate(result, fresh)
    except Exception as e:  # noqa: BLE001 — degrade gracefully, show nothing raw
        st.error(f"Couldn't render the debate: {e}")


if __name__ == "__main__":
    import data_layer

    render(data_layer.get_context("NVDA"))
