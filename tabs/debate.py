"""
tabs/debate.py — the "Bull vs Bear" tab (Person 3).
===================================================
RENDER ONLY. The debate itself is produced by agents/debate.run_debate(); this
file just drives the UX: a start button that states the cost up front, a
progress bar driven by the FIVE REAL CALL BOUNDARIES, the verdict, and then the
exchange that produced it.

Entry point (fixed signature — do not change):
    def render(context: dict) -> None

Nothing runs until the user presses the button. The result is cached in
st.session_state keyed by ticker, so switching views does not re-run it. All
colours come from the shared theme; raw JSON is NEVER shown to the user, and
every model-authored string passes through theme.safe/safe_md before it reaches
the page.

Two things here are deliberate reversals of the original design:
  * The reveal used to run openings -> rebuttals -> judge, which put the ANSWER
    at the end of a ~4,200px scroll after a 25-second wait. The verdict now
    leads and the debate sits underneath it.
  * The staging used to be three `time.sleep(0.7)` calls AFTER all five model
    calls had already returned — 2.1 seconds of theatre charged to the user for
    data that was already in hand.
"""

from __future__ import annotations

import streamlit as st

import theme
from agents.debate import STAGES, run_debate


# --------------------------------------------------------------------------
# Small render helpers
# --------------------------------------------------------------------------

def _side_header(label: str, color: str, side: str) -> None:
    """Side header. `side` is repeated on every card below as a marker, because
    this header scrolls away after roughly one screen and the claim cards were
    otherwise identical grey boxes across ~4,200px of scroll."""
    st.markdown(
        f"<h4 style='color:{color};margin:0 0 .35rem 0;font-size:1.05rem'>"
        f"{theme.safe(label)}</h4>",
        unsafe_allow_html=True,
    )


def _card_marker(side: str, color: str) -> None:
    """The per-card side marker. Small, uppercase, coloured — enough to tell a
    reader which column they are in without relying on the scrolled-away header
    or on column position alone."""
    st.markdown(
        f"<div style='color:{color};font-size:10px;font-weight:700;"
        f"letter-spacing:.09em;text-transform:uppercase;margin-bottom:.25rem'>"
        f"{theme.safe(side)}</div>",
        unsafe_allow_html=True,
    )


def _render_opening(opening: dict, color: str, side: str) -> None:
    """Thesis + a bordered container per claim (text, muted evidence, pill).

    Every string below is model-authored and goes through theme.safe/safe_md.
    """
    opening = opening or {}
    thesis = opening.get("thesis")
    if thesis:
        st.markdown(
            f"<div style='color:{theme.INK};font-style:italic;"
            f"border-left:1px solid {color};padding:.15rem 0 .15rem .7rem;"
            f"margin-bottom:.6rem'>{theme.safe(thesis)}</div>",
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
            _card_marker(side, color)
            st.markdown(f"**{theme.safe_md(claim.get('claim', ''))}**")
            evidence = claim.get("evidence")
            if evidence:
                st.markdown(
                    f"<span style='color:{theme.MUTED};font-size:13px'>"
                    f"{theme.safe(evidence)}</span>",
                    unsafe_allow_html=True,
                )
            strength = str(claim.get("strength") or "medium").lower()
            st.markdown(theme.badge(strength.upper(), strength), unsafe_allow_html=True)


def _render_rebuttal(rebuttal: dict, color: str, side: str) -> None:
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
            _card_marker(f"{side} rebuts", color)
            attacks = point.get("attacks")
            if attacks:
                st.markdown(
                    f"<span style='color:{theme.MUTED};font-size:12px;"
                    f"text-transform:uppercase;letter-spacing:.03em'>"
                    f"responding to:</span> "
                    f"<span style='color:{theme.INK_2};font-size:13px'>"
                    f"{theme.safe(attacks)}</span>",
                    unsafe_allow_html=True,
                )
            counter = point.get("counter")
            if counter:
                st.markdown(theme.safe_md(counter))
            evidence = point.get("evidence")
            if evidence:
                st.markdown(
                    f"<span style='color:{color};font-size:12px'>▸ "
                    f"{theme.safe(evidence)}</span>",
                    unsafe_allow_html=True,
                )


_VERDICT_GLOSS = {
    "bull": "the bull case survived the exchange better",
    "bear": "the bear case survived the exchange better",
    "inconclusive": "neither side landed a decisive argument",
    "neutral": "neither side landed a decisive argument",
}


def _render_judge(judge: dict) -> None:
    """The verdict — the payoff of a five-call orchestration.

    Rendered as ONE authored block rather than Streamlit widgets, for two
    reasons. It previously used st.container(border=True), the exact container
    every claim and rebuttal card above it uses, so the "visually distinct
    verdict card" the docstring promised was visually identical to twelve boxes
    the reader had already scrolled past. And the verdict itself — the answer —
    rendered as an 11px pill, the smallest text on the screen.

    Every model-authored string goes through theme.safe. This function is where
    the "$5B" markdown corruption surfaced.
    """
    judge = judge or {}
    verdict = str(judge.get("verdict") or "inconclusive").lower()
    color = theme.SIDE_COLOR.get(verdict, theme.MUTED)
    gloss = _VERDICT_GLOSS.get(verdict, "")

    conf = judge.get("confidence")
    conf_i = max(0, min(100, int(conf))) if isinstance(conf, (int, float)) else None

    parts = [
        "<div class='rs-verdict' style='background:{};border:1px solid {};"
        "border-radius:14px;padding:1.35rem 1.5rem;margin-top:.5rem'>".format(
            theme.SURFACE, theme.AXIS),
        "<hr class='rs-verdict-rule'/>",
        # An <h3>, so a screen-reader user can navigate straight to the answer
        # rather than scrolling the whole exchange to find it.
        "<h3 style='font-size:11px;color:{};text-transform:uppercase;"
        "letter-spacing:.09em;font-weight:700;margin:0;padding:0'>"
        "The judge's verdict</h3>".format(theme.MUTED),
        # The answer, at the size an answer deserves.
        "<div style='display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;"
        "margin:.5rem 0 .1rem'>"
        "<span style='font-size:2.1rem;font-weight:700;letter-spacing:-.02em;"
        "color:{}'>{}</span>".format(color, theme.safe(verdict.upper())),
        "<span style='color:{};font-size:.95rem'>{}</span>".format(
            theme.INK_2, theme.safe(gloss)),
        "</div>",
    ]

    if conf_i is not None:
        # A bare 58% bar has no calibration anchor — 58% of what? Name the scale.
        parts += [
            "<div style='margin:.9rem 0 1.1rem;max-width:30rem'>",
            "<div style='display:flex;justify-content:space-between;"
            "align-items:baseline;margin-bottom:.35rem'>"
            "<span style='font-size:11px;color:{};text-transform:uppercase;"
            "letter-spacing:.05em'>Confidence in this verdict</span>"
            "<span style='color:{};font-weight:700;font-variant-numeric:tabular-nums'>"
            "{}%</span></div>".format(theme.MUTED, theme.INK, conf_i),
            "<div style='height:6px;border-radius:999px;background:{};"
            "overflow:hidden'><div style='height:100%;width:{}%;background:{};"
            "border-radius:999px'></div></div>".format(theme.AXIS, conf_i, color),
            "<div style='font-size:11px;color:{};margin-top:.35rem'>"
            "How strongly the evidence in this debate favours that side — not a "
            "probability that the stock rises.</div>".format(theme.MUTED),
            "</div>",
        ]

    reasoning = judge.get("reasoning")
    if reasoning:
        parts.append(
            "<div style='color:{};margin:.5rem 0 1.1rem;max-width:68ch;"
            "line-height:1.6'>{}</div>".format(theme.INK_2, theme.safe(reasoning)))

    weak_bull = judge.get("weakest_bull_claim")
    weak_bear = judge.get("weakest_bear_claim")
    if weak_bull or weak_bear:
        parts += [
            "<div style='font-size:11px;color:{};text-transform:uppercase;"
            "letter-spacing:.06em;font-weight:700;margin-bottom:.5rem'>"
            "Weakest argument on each side</div>".format(theme.MUTED),
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,"
            "minmax(15rem,1fr));gap:.9rem;margin-bottom:1.1rem'>",
        ]
        for label, text, side_color in (
                ("🐂 Weakest bull claim", weak_bull, theme.GOOD),
                ("🐻 Weakest bear claim", weak_bear, theme.BAD)):
            parts.append(
                "<div style='background:{};border-radius:10px;padding:.7rem .85rem'>"
                "<div style='color:{};font-weight:700;font-size:.82rem;"
                "margin-bottom:.3rem'>{}</div>"
                "<div style='color:{};font-size:.86rem;line-height:1.5'>{}</div>"
                "</div>".format(theme.PAGE, side_color, label, theme.INK_2,
                                theme.safe(text or "—")))
        parts.append("</div>")

    falsifiers = judge.get("falsifiers") or []
    if falsifiers:
        items = "".join(
            "<li style='margin-bottom:.35rem'>{}</li>".format(theme.safe(f))
            for f in falsifiers)
        parts += [
            "<div style='font-size:11px;color:{};text-transform:uppercase;"
            "letter-spacing:.06em;font-weight:700'>What would change my mind"
            "</div>".format(theme.MUTED),
            "<ol style='color:{};padding-left:1.2rem;margin:.5rem 0 0;"
            "max-width:68ch;line-height:1.55'>{}</ol>".format(theme.INK_2, items),
        ]

    key_uncertainty = judge.get("key_uncertainty")
    if key_uncertainty:
        parts.append(
            "<div style='margin-top:1.1rem;padding:.7rem .85rem;border-radius:10px;"
            "background:{};border:1px solid {}'>"
            "<span style='color:{};font-weight:700;font-size:.82rem'>"
            "Key uncertainty</span>"
            "<div style='color:{};margin-top:.25rem;font-size:.88rem;"
            "line-height:1.55;max-width:68ch'>{}</div></div>".format(
                theme.PAGE, theme.WARN, theme.WARN, theme.INK_2,
                theme.safe(key_uncertainty)))

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _render_debate(result: dict) -> None:
    """Verdict first, then the exchange that produced it.

    The old order was openings -> rebuttals -> judge, which put the ANSWER
    ~4,200px below the fold at the end of a scroll, after a 25-second wait
    during which the page never moved. PRODUCT.md's own principle is "the plain
    answer on the surface, the method one layer down" — so the verdict leads and
    the debate that produced it sits underneath, where a reader who wants the
    method can reach it without a reader who wants the answer having to scroll
    for it.
    """
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

    # ---- The answer -------------------------------------------------------
    _render_judge(judge)

    # ---- The exchange it came from ---------------------------------------
    theme.section("How the two sides argued it")
    st.caption(
        "Both analysts saw the same numbers. Neither could see anything the "
        "other was given. The judge scored the exchange on evidence, not on tone."
    )

    st.markdown("### Opening arguments")
    open_l, open_r = st.columns(2)
    with open_l:
        _side_header("🐂 Bull", theme.GOOD, "bull")
        _render_opening(bull.get("opening"), theme.GOOD, "bull")
    with open_r:
        _side_header("🐻 Bear", theme.BAD, "bear")
        _render_opening(bear.get("opening"), theme.BAD, "bear")

    st.markdown("### Rebuttals")
    reb_l, reb_r = st.columns(2)
    with reb_l:
        _side_header("🐂 Bull rebuts", theme.GOOD, "bull")
        _render_rebuttal(bull.get("rebuttal"), theme.GOOD, "bull")
    with reb_r:
        _side_header("🐻 Bear rebuts", theme.BAD, "bear")
        _render_rebuttal(bear.get("rebuttal"), theme.BAD, "bear")


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
        st.header(f"⚔️ Bull vs Bear — {name}")
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

    # ---- Start / empty state ---------------------------------------------
    if result is None:
        # Say what the work IS before asking for 25 seconds of the user's time.
        # That this is a five-call orchestration is the most impressive fact
        # about the engine, and the interface never used to mention it.
        st.markdown(
            f"Two analysts argue **{theme.safe_md(name)}** from the same data, "
            f"then an impartial judge scores the exchange on evidence."
        )
        st.caption(f"{len(STAGES)} sequential model calls · roughly 20–30 seconds · "
                   f"each turn sees everything said before it")

        if st.button("⚔️ Start the debate", type="primary", use_container_width=True,
                     key=f"start_debate_{ticker}"):
            progress = st.progress(0.0, text="Starting…")
            status_slot = st.empty()

            def _on_stage(i, key, label, done):
                """Real progress, driven by the five actual call boundaries."""
                completed = i + 1 if done else i
                progress.progress(
                    completed / len(STAGES),
                    text=f"Step {i + 1} of {len(STAGES)} · {label}"
                         + ("  ✓" if done else " …"),
                )

            try:
                result = run_debate(context, on_stage=_on_stage)
                store[ticker] = result
            except Exception as e:  # noqa: BLE001 — never crash the tab
                progress.empty()
                status_slot.empty()
                st.error(
                    f"Couldn't run the debate for {ticker}: {e}\n\n"
                    f"The market data above is unaffected. Press the button again "
                    f"to retry — nothing was saved."
                )
                return
            progress.empty()
            status_slot.empty()
            # Rerun rather than falling through. st.button() DRAWS the button in
            # the same script run that reports the click, so falling through
            # leaves a full-width primary "Start the debate" sitting directly
            # above its own completed output — the loudest thing on the screen
            # after a run being an invitation to do the thing just done. On the
            # fresh run `result` is in the store, so this branch is skipped
            # entirely and the result header takes its place.
            st.rerun()
        else:
            return

    # ---- Result header ----------------------------------------------------
    # The primary "Start the debate" button used to still be rendering, full
    # width, directly ABOVE its own output — so the loudest thing on the screen
    # after a completed run was an invitation to do the thing that had just been
    # done. It is replaced by a header that says the run is finished.
    head, rerun_col = st.columns([4, 1])
    with head:
        st.caption(f"Debate complete · {len(STAGES)} model calls · {ticker}")
    with rerun_col:
        if st.button("Run again", key=f"rerun_debate_{ticker}",
                     use_container_width=True,
                     help="Discard this debate and run a fresh one."):
            store.pop(ticker, None)
            st.rerun()

    # ---- Reveal -----------------------------------------------------------
    try:
        _render_debate(result)
    except Exception as e:  # noqa: BLE001 — degrade gracefully, show nothing raw
        st.error(f"Couldn't render the debate: {e}")


if __name__ == "__main__":
    import data_layer

    render(data_layer.get_context("NVDA"))
