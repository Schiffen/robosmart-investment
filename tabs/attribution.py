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
        cliponaxis=False,                 # labels were clipping against the axis
        textfont=dict(color=theme.INK, size=12),
        # The connectors ARE the argument of this chart: they are what says
        # "these three parts sum to that total". At the old AXIS colour they
        # measured 1.24:1 against the chart surface and were invisible, so the
        # chart read as four disconnected floating bars and lost its point.
        connector=dict(line=dict(color=theme.CONNECTOR, width=1.5)),
        increasing=dict(marker=dict(color=theme.GOOD)),   # green = added to the move
        decreasing=dict(marker=dict(color=theme.BAD)),    # red = subtracted
        totals=dict(marker=dict(color=_BLUE)),            # blue = the net result
        hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
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

def _rebase(series) -> "np.ndarray":
    """Index a price series to 100 at its first finite value."""
    values = series.to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0 or finite[0] == 0:
        return np.full(values.shape, np.nan)
    return values / finite[0] * 100.0


def _comparison(frame, ticker: str, etf: str | None, preset: str) -> go.Figure:
    """The stock against its sector and against the market, all rebased to 100.

    Same three components as the waterfall directly above it — market, sector,
    the stock itself — but over a year rather than a day, which is what turns
    "today was mostly sector" from an assertion into something a reader can see
    the shape of. It uses data_layer.get_benchmark_history for both benchmarks,
    the same single source the Dashboard and the factor model use, so the two
    views cannot disagree about what SPY did (INTEGRATION_CONTRACT §3).

    `etf` is None when there is no distinct sector to draw — see _sector_etf.
    """
    fig = go.Figure()
    cols = ["stock"]
    fig.add_trace(go.Scatter(
        x=frame.index, y=frame["stock"], name=ticker, mode="lines",
        line=dict(color=_BLUE, width=2.5),
        hovertemplate="%{x|%b %d}<br>" + ticker + " %{y:.1f}<extra></extra>"))
    if etf:
        cols.append("sector")
        fig.add_trace(go.Scatter(
            x=frame.index, y=frame["sector"], name=f"{etf} (its sector)",
            mode="lines", line=dict(color=theme.CATEGORICAL[2], width=2),
            hovertemplate="%{x|%b %d}<br>" + etf + " %{y:.1f}<extra></extra>"))
    cols.append("market")
    fig.add_trace(go.Scatter(
        x=frame.index, y=frame["market"], name="SPY (the market)", mode="lines",
        line=dict(color=theme.MUTED, width=2, dash="dash"),
        hovertemplate="%{x|%b %d}<br>SPY %{y:.1f}<extra></extra>"))
    fig.update_layout(legend=dict(orientation="h", y=1.12, x=0),
                      xaxis_title="Date", yaxis_title="Index (start = 100)")
    _apply_window(fig, frame, preset, cols=cols)
    return theme.style_fig(fig, height=360, zoom=True)


def _apply_window(fig: go.Figure, frame, preset: str, *, cols) -> None:
    """Declared x/y ranges for `preset`. Mirrors tabs.dashboard._apply_window —
    both call theme.range_bounds, so the two series charts in the app window
    identically and "1Y" means the same thing on each."""
    bounds = theme.range_bounds(frame.index, preset)
    if bounds is None:
        return
    lo, hi = bounds
    # ISO strings, not Timestamps — see tabs/dashboard.py::_apply_window. A
    # Timestamp here makes the figure unserialisable and it drops silently out
    # of the PDF export while rendering perfectly in the browser.
    fig.update_xaxes(range=[lo.isoformat(), hi.isoformat()])
    visible = frame.loc[(frame.index >= lo) & (frame.index <= hi), list(cols)]
    values = visible.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return
    top, bottom = float(values.max()), float(values.min())
    pad = max((top - bottom) * 0.06, 0.5)
    fig.update_yaxes(range=[bottom - pad, top + pad])


def _sector_etf(context: dict) -> str | None:
    """The ticker's sector ETF, or None when there is no DISTINCT one.

    THIS FUNCTION IS THE WHOLE POINT OF THE DEGENERATE CASE, so it is worth
    saying plainly what it guards. market_data/live.py resolves the sector ETF
    as `SECTOR_ETF.get(sector, "SPY")` — every ticker yfinance cannot classify
    falls back to SPY itself. That is not a rare edge: measured against the
    recorded fixture, SIX of eighteen tickers hit it (BND, GLD, TLT, VNQ, VTI,
    VXUS — i.e. every fund), and the diversified_global book is mostly funds.

    Drawing "stock vs sector vs market" for those would plot SPY twice: two
    identical lines, one labelled "its sector", silently asserting that GLD's
    sector is the S&P 500. Returning None instead collapses the chart to two
    honest lines, and the caller says why in the caption.

    Verified live as well as offline: GLD and SPY both come back with
    benchmarks == {SPY, VIX} and no separate sector key, so the collapse is
    already visible in Contract B rather than being inferred from the symbol.
    """
    etf = context.get("sector_etf")
    if not etf or str(etf).upper() == "SPY":
        return None
    return str(etf).upper()


def _safe_link(url: str) -> str | None:
    """Return the URL only if it is a plain http(s) link.

    `source_link` is model-authored and lands in a markdown link, so a
    `javascript:` or `data:` scheme would be live in the page. Anything that is
    not http/https is dropped and the headline renders as plain text.
    """
    url = (url or "").strip()
    if not url:
        return None
    lowered = url.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        # Parens would terminate the markdown link target early.
        return url.replace("(", "%28").replace(")", "%29")
    return None


def _render_explanation(result: dict) -> None:
    """Render the explainer's output as cards, or a confident no-cause panel.
    Never shows raw JSON. Every field here is model-authored."""
    if not isinstance(result, dict):
        st.error("The explainer returned an unexpected result.")
        return

    explanations = result.get("explanations") or []
    no_cause = bool(result.get("no_cause_found")) or not explanations
    caveat = (result.get("caveat") or "").strip()

    if no_cause:
        # Principle 2 is "say I don't know out loud", and this is the panel that
        # does it — but it used to render as st.info(), the same blue hint box
        # used for "Press Start the Debate". A deliberate, epistemically load-
        # bearing answer wore the same clothes as a tooltip. It is now the most
        # confidently designed panel on the tab, because that is what it is.
        st.markdown(
            f"<div style='background:{theme.SURFACE};border:1px solid {theme.AXIS};"
            f"border-radius:{theme.RADIUS_HERO};padding:1.35rem 1.5rem'>"
            f"<div style='font-size:11px;color:{theme.MUTED};text-transform:uppercase;"
            f"letter-spacing:.09em;font-weight:700'>The honest answer</div>"
            f"<div style='font-size:1.5rem;font-weight:700;color:{theme.INK};"
            f"letter-spacing:-.015em;margin:.45rem 0 .6rem'>"
            f"No clear cause found</div>"
            f"<div style='color:{theme.INK_2};line-height:1.6;max-width:68ch'>"
            f"After accounting for the market and the sector, this "
            f"company-specific move isn’t tied to any headline we can see. It may "
            f"be flow-driven — positioning, options, index rebalancing — or the "
            f"catalyst simply isn’t public yet."
            f"</div>"
            f"<div style='color:{theme.MUTED};margin-top:.8rem;font-size:.88rem;"
            f"max-width:68ch'>This is a designed outcome, not an error. The model "
            f"is only allowed to cite evidence it was actually given, so when the "
            f"evidence isn’t there it says so instead of inventing a story."
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if caveat:
            st.caption(theme.safe_md(caveat))
        return

    st.markdown("**Most likely explanations**, ranked by how confident the model "
                "is that the evidence supports them:")
    for e in explanations:
        if not isinstance(e, dict):
            continue
        cause = (e.get("cause") or "Company-specific news").strip()
        likelihood = str(e.get("likelihood") or "medium").lower()
        if likelihood not in ("high", "medium", "low"):
            likelihood = "medium"
        headline = (e.get("evidence_headline") or "").strip()
        link = _safe_link(e.get("source_link"))
        reasoning = (e.get("reasoning") or "").strip()

        with st.container(border=True):
            top = st.columns([1, 6])
            with top[0]:
                # "HIGH" here means high CONFIDENCE, not good news — the badge
                # palette otherwise reads as the app's gain/loss green.
                st.markdown(theme.badge(likelihood.upper(), likelihood),
                            unsafe_allow_html=True)
            with top[1]:
                st.markdown(f"**{theme.safe_md(cause)}**")
            if headline:
                if link:
                    st.markdown(f"📰 [{theme.safe_md(headline)}]({link})")
                else:
                    st.markdown(f"📰 {theme.safe_md(headline)}")
            if reasoning:
                st.markdown(theme.safe_md(reasoning))

    if caveat:
        st.caption(f":material/warning: {theme.safe_md(caveat)}")


def _render_comparison(context: dict, ticker: str) -> None:
    """Draw the year-wide stock / sector / market comparison."""
    import pandas as pd

    import data_layer

    history = context.get("history")
    if history is None or len(history) == 0:
        return
    etf = _sector_etf(context)

    frame = pd.DataFrame(index=history.index)
    frame["stock"] = _rebase(history["Close"])
    spy = data_layer.get_benchmark_history("SPY")
    frame["market"] = _rebase(spy["Close"].reindex(history.index).ffill())
    if etf:
        sector = data_layer.get_benchmark_history(etf)
        frame["sector"] = _rebase(sector["Close"].reindex(history.index).ffill())
    frame = frame.dropna(how="all")
    if frame.empty:
        return

    theme.section("How it compares to its sector and the market")
    preset = theme.range_control(f"cmp_{ticker}")
    st.plotly_chart(_comparison(frame, ticker, etf, preset), width="stretch",
                    config=theme.CHART_CONFIG,
                    key=theme.chart_key(f"cmp_{ticker}", preset))

    if etf:
        st.caption(f"All three rebased to 100 one year ago, so the lines are "
                   f"comparable regardless of share price. **{etf}** is the "
                   f"sector ETF for {theme.safe_md(str(context.get('sector')))}; "
                   f"**SPY** is the market.")
    else:
        # Never draw SPY twice. See _sector_etf — this is a third of the
        # recorded book, not a rare edge.
        st.caption(f"**{ticker}** has no sector classification, so it is shown "
                   f"against the market alone rather than against a sector ETF "
                   f"that would just be SPY a second time. Both rebased to 100 "
                   f"one year ago.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(context: dict) -> None:
    # ---- Empty state -------------------------------------------------------
    if context is None:
        st.info("Pick a stock from the sidebar to see what drove its move today.",
                icon=":material/search:")
        return

    ticker = (context.get("ticker") or "—").upper()
    company = context.get("company_name") or ticker

    st.header(f"What happened to {company} today?")

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
                            width="stretch", config=theme.CHART_CONFIG)
        except Exception as e:  # noqa: BLE001
            st.error(f"Attribution chart unavailable: {e}")
    else:
        st.info("📉 Not enough overlapping price history to break this move into "
                "market, sector, and company-specific parts.")

    # ---- (2b) The same three parts, over a year ---------------------------
    # Placed immediately under the waterfall on purpose: the waterfall splits
    # ONE DAY into market / sector / company, and a reader's next question is
    # whether that day was typical. Same three things, same order, same
    # benchmark source — just a year wide instead of a day.
    try:
        _render_comparison(context, ticker)
    except Exception as e:  # noqa: BLE001 — a bonus chart never breaks the tab
        st.caption(f"Sector comparison unavailable: {e}")

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
            f":material/warning: **Treat this split as rough** — {why}. The market and sector "
            f"components may be unreliable, so the company-specific residual could "
            f"be over- or under-stated."
        )

    st.divider()

    # ---- (5)-(8) Explain the company-specific move ------------------------
    theme.section("The company-specific move")

    if not _finite(idio):
        st.info("There's no reliable company-specific residual to explain — the "
                "decomposition above couldn't be computed.")
        return

    resid = abs(float(idio))

    # (8) Noise → say so plainly and skip the LLM entirely.
    if resid < NOISE_THRESHOLD:
        st.success(
            f":material/check_circle: The company-specific part of today's move is just "
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
    clicked = st.button(":material/troubleshoot: Explain the company-specific move",
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
