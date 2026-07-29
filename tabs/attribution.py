"""
tabs/attribution.py — "What Happened to My Stock Today" (Person 4).
===================================================================
RENDER ONLY. The math lives in factor_model.decompose_move (pure, tested); the
one-sentence news story lives in agents.explainer.explain_idiosyncratic. This
file just draws them.

The whole tab answers one question a beginner actually asks — "my stock moved,
why?" — and answers it honestly: it splits the move into MARKET, SECTOR, and
COMPANY-SPECIFIC parts (the waterfall), then only reaches for the LLM to explain
the company-specific leftover. If that leftover is noise, we say so and stop. If
no headline explains it, we say "no clear cause found" with confidence instead of
inventing a story.

Entry point (fixed signature — do not change):
    def render(context: dict) -> None
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import theme
from factor_model import decompose_move
from agents.explainer import explain_idiosyncratic

# Residual (in percentage points, absolute) below this is ordinary daily noise —
# mirror of agents.explainer.NOISE_THRESHOLD so the tab and agent agree.
NOISE_THRESHOLD = 0.3
_BLUE = theme.CATEGORICAL[0]  # totals bar / neutral accent


def _finite(x) -> bool:
    """True for a real, finite number."""
    try:
        return x is not None and np.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _delta_color_for(v) -> str:
    """A hex colour string for a signed move (green up, red down, muted flat)."""
    if not _finite(v):
        return theme.MUTED
    if float(v) > 0:
        return theme.GOOD
    if float(v) < 0:
        return theme.BAD
    return theme.INK_2


# --------------------------------------------------------------------------
# The one chart that makes the whole idea obvious
# --------------------------------------------------------------------------

def _waterfall(market: float, sector: float, idio: float, total: float,
               ticker: str) -> go.Figure:
    """Market → Sector → Company-specific → Total, as a signed % waterfall."""
    labels = ["Market", "Sector", "Company-specific", "Total move"]
    values = [float(market), float(sector), float(idio), float(total)]
    measure = ["relative", "relative", "relative", "total"]
    text = [theme.fmt_pct(v) for v in values]

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measure,
        x=labels,
        y=values,
        text=text,
        textposition="outside",
        textfont=dict(color=theme.INK, size=12),
        connector=dict(line=dict(color=theme.AXIS, width=1)),
        increasing=dict(marker=dict(color=theme.GOOD)),   # green = added to the move
        decreasing=dict(marker=dict(color=theme.BAD)),    # red = subtracted
        totals=dict(marker=dict(color=_BLUE)),            # blue = the net result
        hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=f"What moved {ticker} today — market vs sector vs the company itself",
        yaxis_title="Contribution to today's move (%)",
        showlegend=False,
    )
    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=theme.AXIS)
    # Headroom so the outside text labels don't clip.
    span = max(abs(v) for v in values) if values else 1.0
    pad = max(span * 0.35, 0.25)
    lo = min(values + [0.0]) - pad
    hi = max(values + [0.0]) + pad
    fig.update_yaxes(range=[lo, hi])
    return theme.style_fig(fig, height=380)


# --------------------------------------------------------------------------
# Explanation rendering (cards / no-cause panel)
# --------------------------------------------------------------------------

def _render_explanation(result: dict) -> None:
    """Render the explainer's output as cards, or a confident no-cause panel.
    Never shows raw JSON."""
    if not isinstance(result, dict):
        st.error("The explainer returned an unexpected result.")
        return

    explanations = result.get("explanations") or []
    no_cause = bool(result.get("no_cause_found")) or not explanations

    if no_cause:
        st.info(
            "**No clear cause found in recent news.** After accounting for the "
            "market and sector, this company-specific move isn't tied to any "
            "headline we can see — it may be flow-driven (positioning, options, "
            "index rebalancing), or the catalyst simply isn't public yet. That's a "
            "legitimate outcome, not an error."
        )
        caveat = (result.get("caveat") or "").strip()
        if caveat:
            st.caption(caveat)
        return

    st.markdown("**Most likely explanations** (ranked):")
    for e in explanations:
        if not isinstance(e, dict):
            continue
        cause = (e.get("cause") or "Company-specific news").strip()
        likelihood = str(e.get("likelihood") or "medium").lower()
        if likelihood not in ("high", "medium", "low"):
            likelihood = "medium"
        headline = (e.get("evidence_headline") or "").strip()
        link = (e.get("source_link") or "").strip()
        reasoning = (e.get("reasoning") or "").strip()

        with st.container(border=True):
            top = st.columns([1, 6])
            with top[0]:
                st.markdown(theme.badge(likelihood.upper(), likelihood),
                            unsafe_allow_html=True)
            with top[1]:
                st.markdown(f"**{cause}**")
            if headline:
                if link:
                    st.markdown(f"📰 [{headline}]({link})")
                else:
                    st.markdown(f"📰 {headline}")
            if reasoning:
                st.markdown(reasoning)

    caveat = (result.get("caveat") or "").strip()
    if caveat:
        st.caption(f"⚠️ {caveat}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(context: dict) -> None:
    # ---- Empty state -------------------------------------------------------
    if context is None:
        st.info("🔎 Pick a stock from the sidebar to see what drove its move today.")
        return

    ticker = (context.get("ticker") or "—").upper()
    company = context.get("company_name") or ticker

    st.subheader(f"What happened to {company} today?")

    # ---- Factor decomposition (the math) -----------------------------------
    try:
        decomposition = decompose_move(context)
    except Exception as e:  # noqa: BLE001 — never take the whole tab down
        st.error(f"Couldn't decompose today's move: {e}")
        return

    total = decomposition.get("total_move_pct")
    market = decomposition.get("market_component_pct")
    sector = decomposition.get("sector_component_pct")
    idio = decomposition.get("idiosyncratic_pct")
    mq = decomposition.get("model_quality") or {}
    betas = decomposition.get("betas") or {}

    # ---- (1) Hero metric: today's total move, coloured ---------------------
    try:
        price = context.get("price") or {}
        current = price.get("current")
        c1, c2 = st.columns([1, 2])
        with c1:
            value = theme.fmt_money(current) if _finite(current) else theme.fmt_pct(total)
            st.metric(
                f"{ticker} — today's move",
                value,
                delta=theme.fmt_pct(total) if _finite(total) else None,
                delta_color="normal",
                help="Today's price change vs the previous close.",
            )
        with c2:
            if _finite(total):
                move_color = _delta_color_for(total)
                direction = "up" if float(total) > 0 else "down" if float(total) < 0 else "flat"
                st.markdown(
                    f"<div style='padding-top:6px'>"
                    f"<span style='color:{theme.INK_2}'>Today {company} moved </span>"
                    f"<span style='color:{move_color};font-weight:700'>"
                    f"{theme.fmt_pct(total)} ({direction})</span>"
                    f"<span style='color:{theme.INK_2}'>. The chart below splits that "
                    f"into what the whole market did, what the sector did, and what's "
                    f"specific to {ticker}.</span></div>",
                    unsafe_allow_html=True,
                )
    except Exception as e:  # noqa: BLE001
        st.error(f"Couldn't render the move summary: {e}")

    st.divider()

    # ---- (2) The waterfall — the one chart that makes it obvious ----------
    have_components = all(_finite(v) for v in (market, sector, idio, total))
    if have_components:
        try:
            st.plotly_chart(_waterfall(market, sector, idio, total, ticker),
                            width="stretch")
        except Exception as e:  # noqa: BLE001
            st.error(f"Attribution chart unavailable: {e}")
    else:
        st.info("📉 Not enough overlapping price history to break this move into "
                "market, sector, and company-specific parts.")

    # ---- (3) Interpretation + model detail --------------------------------
    interpretation = decomposition.get("interpretation")
    if interpretation:
        st.markdown(f"**{interpretation}**")

    try:
        bits = []
        r2 = mq.get("r_squared")
        if _finite(r2):
            bits.append(f"Model fit R² = {float(r2):.0%}")
        bm, bs = betas.get("market"), betas.get("sector")
        if _finite(bm):
            bits.append(f"market β = {float(bm):.2f}")
        if _finite(bs):
            bits.append(f"sector β = {float(bs):.2f}")
        n_obs = mq.get("n_obs")
        if n_obs:
            bits.append(f"{int(n_obs)} days")
        if bits:
            st.caption(" · ".join(bits) + ". Betas are OLS on 1y daily returns; "
                       "the sector is residualized against the market so the two "
                       "don't double-count. Not investment advice.")
    except Exception:  # noqa: BLE001 — caption is a nicety, never break the tab
        pass

    # ---- (4) Reliability warning ------------------------------------------
    if not mq.get("reliable", False):
        r2 = mq.get("r_squared")
        n_obs = mq.get("n_obs")
        reasons = []
        if _finite(r2) and float(r2) < 0.2:
            reasons.append(f"the market/sector model explains little of this stock's "
                           f"variance (R² = {float(r2):.0%})")
        if isinstance(n_obs, (int, float)) and n_obs < 100:
            reasons.append(f"only {int(n_obs)} overlapping days were available")
        why = "; ".join(reasons) if reasons else "the model fit is weak"
        st.warning(
            f"⚠️ **Treat this split as rough** — {why}. The market and sector "
            f"components may be unreliable, so the company-specific residual could "
            f"be over- or under-stated."
        )

    st.divider()

    # ---- (5)-(8) Explain the company-specific move ------------------------
    st.markdown("### The company-specific move")

    if not _finite(idio):
        st.info("There's no reliable company-specific residual to explain — the "
                "decomposition above couldn't be computed.")
        return

    resid = abs(float(idio))

    # (8) Noise → say so plainly and skip the LLM entirely.
    if resid < NOISE_THRESHOLD:
        st.success(
            f"✅ The company-specific part of today's move is just "
            f"**{theme.fmt_pct(idio)}** — within normal daily noise. Nothing to "
            f"explain here: today's move was essentially the market and sector "
            f"carrying {ticker} along."
        )
        return

    st.caption(
        f"After stripping out market and sector, **{theme.fmt_pct(idio)}** of today's "
        f"move is specific to {ticker}. Ask the explainer to check whether recent "
        f"news accounts for it."
    )

    cache_key = f"attribution_explanation::{ticker}"
    clicked = st.button("🔍 Explain the company-specific move",
                        key=f"explain_btn_{ticker}", type="primary")

    if clicked:
        try:
            with st.spinner(f"Reading recent {ticker} headlines…"):
                st.session_state[cache_key] = explain_idiosyncratic(context, decomposition)
        except Exception as e:  # noqa: BLE001
            st.error(f"Couldn't generate an explanation: {e}")
            return

    if cache_key in st.session_state:
        try:
            _render_explanation(st.session_state[cache_key])
        except Exception as e:  # noqa: BLE001
            st.error(f"Couldn't display the explanation: {e}")
