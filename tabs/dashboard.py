"""
tabs/dashboard.py — the Portfolio Dashboard tab (Person 2).
===========================================================
RENDER ONLY. Every number comes from portfolio_metrics.py (pure, tested).
This file is allowed to import Streamlit/Plotly; the math file is not.

Entry point (fixed signature — do not change):
    def render(portfolio: dict) -> None

Colour system: the dataviz reference palette, dark steps. Each chart draws on
its own dark surface (#1a1a19) so it stays legible whether the grader runs
Streamlit in light or dark mode.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import portfolio_metrics as pm
import theme
# Shared design system — one source of truth for colours/formatting across all
# three tabs. (Aliased to the local names this module already uses.)
from theme import (
    AXIS, BAD, CATEGORICAL, CONNECTOR, CURRENCY_SYMBOL, DIVERGING, GOOD, GRID,
    INK, INK_2, MUTED, SURFACE,
    fmt_money as _money, fmt_pct as _pct, style_fig as _style_fig,
)


def _sym(portfolio: dict) -> str:
    return CURRENCY_SYMBOL.get(portfolio.get("currency", "USD"), "$")


# --------------------------------------------------------------------------
# Chart builders
# --------------------------------------------------------------------------

def _donut(sector_df: pd.DataFrame, sym: str = "$", height: int = 340) -> go.Figure:
    n = len(sector_df)
    colors = [CATEGORICAL[i % len(CATEGORICAL)] for i in range(n)]  # cycle, never run out
    invested = float(np.nansum(sector_df["market_value"].to_numpy()))
    fig = go.Figure(go.Pie(
        labels=sector_df["sector"], values=sector_df["market_value"],
        hole=0.62, sort=False, direction="clockwise",
        insidetextorientation="horizontal",           # no rotated labels
        marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
        textinfo="label+percent", textfont=dict(color=INK, size=12),
        hovertemplate="%{label}<br>%{percent}<extra></extra>",
    ))
    # No Plotly title: inside the lede the donut is self-labelling (every
    # wedge is named on it), and a title here rendered ABOVE the "TOTAL
    # VALUE" label — so the first text inside a block whose whole premise is
    # "the left column is primary" belonged to the right column.
    fig.update_layout(showlegend=False)
    fig.add_annotation(text=f"<b>{sym}{invested:,.0f}</b><br><span style='font-size:11px'>invested</span>",
                       showarrow=False, font=dict(color=INK, size=18))
    return _style_fig(fig, height=height)


def _heatmap(corr: pd.DataFrame) -> go.Figure:
    z = corr.to_numpy().astype(float).copy()
    diag = np.eye(z.shape[0], dtype=bool)
    z_color = z.copy()
    z_color[diag] = np.nan                    # trivial 1.0s out of the colour scale
    text = np.where(diag, "", np.round(z, 2).astype(object))
    fig = go.Figure(go.Heatmap(
        z=z_color, x=list(corr.columns), y=list(corr.index),
        zmin=-1, zmax=1, colorscale=DIVERGING, zmid=0,
        xgap=2, ygap=2,                        # 2px surface gap between cells
        text=text, texttemplate="%{text}",
        textfont=dict(size=11, color=INK),
        colorbar=dict(title="ρ", outlinewidth=0, tickcolor=MUTED),
        hovertemplate="%{y} · %{x}<br>ρ = %{z:.2f}<extra></extra>",
    ))
    # No Plotly title — named by theme.section("How concentrated you really
    # are") directly above it.
    fig.update_yaxes(autorange="reversed")
    return _style_fig(fig)


def _contribution_bar(contrib: pd.DataFrame, sym: str = "$") -> go.Figure:
    """Which holdings moved the portfolio today, largest impact first.

    Horizontal bars because the labels are tickers and the comparison is along
    one axis — a reader scans down a ranked list far faster than across a
    rotated-label column chart. Bars diverge from a zero line so "helped" and
    "hurt" are separated by position, not only by colour.
    """
    d = contrib.iloc[::-1]                       # largest at the TOP once drawn
    values = d["contribution_pct"].to_numpy(dtype=float)
    colors = [GOOD if v > 0 else BAD if v < 0 else MUTED for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=d["ticker"], orientation="h",
        marker=dict(color=colors),
        text=[f"{v:+.2f}%" for v in values],
        textposition="outside",
        cliponaxis=False,
        textfont=dict(color=INK, size=12),
        customdata=np.stack([d["day_change_pct"].to_numpy(dtype=float),
                             d["weight_pct"].to_numpy(dtype=float),
                             d["contribution_abs"].to_numpy(dtype=float)], axis=-1),
        hovertemplate=("<b>%{y}</b><br>moved %{customdata[0]:+.2f}% today"
                       "<br>at %{customdata[1]:.1f}% of your book"
                       f"<br>= %{{customdata[2]:+,.2f}} {sym}"
                       "<br><b>%{x:+.2f}%</b> of your portfolio move<extra></extra>"),
    ))
    fig.update_layout(
        xaxis_title="Contribution to your portfolio's move (%)",
        showlegend=False,
    )
    fig.update_xaxes(ticksuffix="%", zeroline=True, zerolinecolor=CONNECTOR,
                     zerolinewidth=1.5)
    span = float(np.nanmax(np.abs(values))) if len(values) else 1.0
    pad = max(span * 0.45, 0.05)
    fig.update_xaxes(range=[values.min() - pad, values.max() + pad])
    fig.update_yaxes(showgrid=False)
    return _style_fig(fig, height=max(220, 46 * len(d) + 90))


def _perf_line(perf: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=perf.index, y=perf["Portfolio"], name="Your portfolio",
        mode="lines", line=dict(color="#3987e5", width=2.5),
        hovertemplate="%{x|%b %d}<br>Portfolio %{y:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=perf.index, y=perf["SPY"], name="S&P 500 (SPY)",
        mode="lines", line=dict(color=MUTED, width=2, dash="dash"),
        hovertemplate="%{x|%b %d}<br>SPY %{y:.1f}<extra></extra>",
    ))
    fig.update_layout(
        legend=dict(orientation="h", y=1.12, x=0),
        xaxis_title="Date", yaxis_title="Index (start = 100)",
    )
    return _style_fig(fig, height=360)


# --------------------------------------------------------------------------
# Positions table (conditional green/red styling)
# --------------------------------------------------------------------------

def _sign_class(v) -> str:
    """Colour class for a signed cell. Colour is redundant here, never sole:
    every formatted value below already carries an explicit +/- or a currency
    symbol, so the meaning survives with colour stripped entirely."""
    if v is None or not np.isfinite(v):
        return "rs-flat"
    return "rs-pos" if v > 0 else "rs-neg" if v < 0 else "rs-flat"


def _render_positions_table(df: pd.DataFrame, sym: str) -> None:
    """Render holdings as a semantic <table>.

    This replaces st.dataframe deliberately. The Streamlit grid paints to a
    <canvas>, and its accessibility fallback exposed the UNFORMATTED floats —
    a screen reader heard "513.8399999999999" where the screen showed "$513.84",
    "150" where it showed "$150.00", and "-1.88" where it showed "-1.88%".
    The pandas Styler.format() only ever styled the paint, never the a11y tree,
    so display and announced content could not be reconciled from inside
    st.dataframe. Here they are the same string by construction.
    """
    def money(v):
        return "N/A" if v is None or not np.isfinite(v) else f"{sym}{v:,.2f}"

    def pct(v):
        return "N/A" if v is None or not np.isfinite(v) else f"{v:+.2f}%"

    def weight(v):
        return "N/A" if v is None or not np.isfinite(v) else f"{v:.1f}%"

    headers = ["Ticker", "Shares", "Cost basis", "Current", "Market value",
               "P&L", "P&L %", "Weight %", "Day %"]

    rows = []
    for r in df.itertuples():
        cells = [
            f"<th scope='row'>{theme.safe(r.ticker)}</th>",
            f"<td>{r.shares:,.0f}</td>",
            f"<td>{money(r.cost_basis)}</td>",
            f"<td>{money(r.current_price)}</td>",
            f"<td>{money(r.market_value)}</td>",
            f"<td class='{_sign_class(r.pnl_abs)}'>{money(r.pnl_abs)}</td>",
            f"<td class='{_sign_class(r.pnl_pct)}'>{pct(r.pnl_pct)}</td>",
            f"<td>{weight(r.weight_pct)}</td>",
            f"<td class='{_sign_class(r.day_change_pct)}'>{pct(r.day_change_pct)}</td>",
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")

    head = "".join(f"<th scope='col'>{h}</th>" for h in headers)
    st.markdown(
        "<div class='rs-table-wrap'>"
        "<table class='rs-table'>"
        "<caption>Your holdings — one row per position. Gains and losses carry "
        "an explicit + or − as well as colour.</caption>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# The lede
# --------------------------------------------------------------------------

def _mover_sentence(contrib) -> str:
    """One sentence naming the holding that actually moved the book today.

    This used to live ~900px down the page under its own section heading. It is
    the most useful sentence on the tab — it converts an abstract "+0.09%" into
    a fact about something the reader owns — so it belongs beside the number it
    explains, not below the fold.
    """
    if contrib is None or getattr(contrib, "empty", True) or len(contrib) < 2:
        return ""
    top = contrib.iloc[0]
    verb = "added" if top["contribution_pct"] > 0 else "cost you"
    return (f"<b>{top['ticker']}</b> {verb} "
            f"<b>{abs(top['contribution_pct']):.2f}%</b> of today's move — it "
            f"changed {top['day_change_pct']:+.2f}% while making up "
            f"{top['weight_pct']:.0f}% of what you hold.")


def _render_lede(summary: dict, sector_df, contrib, sym: str) -> None:
    """The page's primary object.

    Before this the dashboard opened on four equal-weight metric tiles and then
    ran nine analyses down one column at the same visual weight, with a type
    scale spanning about 3x top to bottom. Uniform weight across a narrow scale
    range is precisely what "this looks basic" means, and no amount of
    background treatment fixes it — the page had no primary object to look at.

    So: ONE composed unit, asymmetric 7:5, carrying the four things a returning
    user actually opens the app to learn — what it's worth, what it did today,
    what caused that, and what it's made of. Everything below now reads as
    evidence supporting a headline rather than as nine peers.

    The headline is the user's MONEY, not the product's name. theme.py rule 6
    already argued this when it cut the 44px masthead: on an Operate surface
    the user's money is the headline and the product's name is a label. A hero
    with the product name in it was specified for this pass and cut for exactly
    that reason.

    Rendered with st.html rather than st.markdown(unsafe_allow_html=True): this
    is app-authored markup with no model text in it, and st.html does not run
    the string through the markdown/LaTeX pass that has twice eaten dollar
    signs in this project.
    """
    mover = _mover_sentence(contrib)

    # Built from st.metric, NOT from hand-written HTML. The first version of
    # this block rendered the headline in raw markup to get display-scale type,
    # and the AppTest suite caught it immediately: the metric count dropped
    # from 9 to 5. That count was standing in for something real — st.metric
    # carries the label/value/delta relationship, the delta's direction arrow
    # (the non-colour encoding gain/loss depends on), and the help tooltip.
    # Hand-rolled HTML looked identical and silently threw all three away.
    #
    # Display scale is a CSS problem, so it is solved in CSS (rule 13), scoped
    # by container key. The semantics stay native.
    with st.container(key="rs_lede"):
        left, right = st.columns([7, 5], vertical_alignment="top")
        with left:
            with st.container(key="rs_headline"):
                st.metric(
                    "Total value", _money(summary["total_value"], sym),
                    delta=f"{_money(summary.get('day_change_abs'), sym)} "
                          f"({_pct(summary.get('day_change_pct'))}) today",
                    delta_color="normal",
                    help="Everything you own here: the market value of your "
                         "holdings plus uninvested cash. The change below it is "
                         "today's equity move as a % of yesterday's total.",
                )
            if mover:
                st.html(f"<p class='rs-lede-mover'>{mover}</p>")
        with right:
            try:
                # 215, not the 340 default. The donut is the tallest thing in
                # the row, so IT sets the block's height, and every pixel it
                # exceeds the left column by becomes dead space at the bottom
                # of that column. 340 opened a ~220px gap (split above and
                # below, when the columns were centre-aligned); 250 still left
                # ~65px. Measured against the left column's ~185px of content.
                #
                # Sizing the chart to the text is the fix. Padding the text to
                # the chart would only have moved the emptiness somewhere else.
                st.plotly_chart(_donut(sector_df, sym, height=215),
                                width="stretch", config=theme.CHART_CONFIG)
            except Exception as e:  # noqa: BLE001 — never take the lede down
                st.caption(f"Sector chart unavailable: {e}")

        # The meta strip. P&L, positions and cash were headline tiles of equal
        # weight; they are context, not the headline, and demoting them is what
        # gives the value above the room to be read at display size.
        with st.container(key="rs_lede_meta", horizontal=True):
            st.metric("Total P&L", _money(summary.get("total_pnl_abs"), sym),
                      delta=_pct(summary.get("total_pnl_pct")),
                      delta_color="normal",
                      help="Return on cost basis (invested equity).")
            st.metric("Positions", f"{summary['num_positions']}",
                      help="Number of distinct holdings.")
            st.metric("Cash", _money(summary.get("cash") or 0.0, sym),
                      help="Uninvested cash. Included in total value, but not "
                           "in the holdings table below.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(portfolio: dict) -> None:
    # ---- Empty state -------------------------------------------------------
    if not portfolio or not portfolio.get("positions"):
        st.info("Upload a portfolio CSV or load the demo portfolio from the "
                "sidebar to see your dashboard.")
        return

    sym = _sym(portfolio)
    tickers = [p["ticker"] for p in portfolio["positions"]]

    # ---- Pull market context (built by Person 1's data_layer) --------------
    try:
        from data_layer import active_provider_name, get_context_batch
        contexts = get_context_batch(tickers)
    except Exception as e:  # noqa: BLE001 — never take the whole tab down
        st.error(f"Couldn't load market data: {e}")
        return

    # `get_context_batch` omits tickers it couldn't resolve. Say which, instead
    # of leaving unexplained N/A rows in the holdings table and letting the user
    # wonder whether it's a typo, a delisting, or a broken app.
    unresolved = [t for t in tickers if t.upper().strip() not in contexts]
    if unresolved:
        offline = active_provider_name() == "fixture"
        st.warning(
            f"No market data for **{', '.join(unresolved)}** — shown as N/A below. "
            + ("Not in the offline fixture; run without USE_MOCK to fetch it live."
               if offline else "Check the symbol — it may be mistyped or delisted."),
            icon=":material/warning:",
        )

    # ---- Benchmark history — ONE source (INTEGRATION_CONTRACT §3) ----------
    # Fetch SPY once here from the data layer and inject it into every
    # benchmark-relative metric below. This keeps beta / risk / performance
    # reconciled with the same SPY series, and — crucially — means mock mode
    # never triggers portfolio_metrics' live yfinance fallback.
    try:
        from data_layer import get_benchmark_history
        spy_history = get_benchmark_history("SPY")
    except Exception:  # noqa: BLE001 — degrade to N/A rather than crash the tab
        spy_history = None

    # ---- Metrics + concentration + table (isolated) -----------------------
    try:
        df = pm.position_values(portfolio, contexts)
        summary = pm.portfolio_summary(df, portfolio.get("cash", 0.0))
        sector_df = pm.sector_breakdown(df, portfolio)
        weights = {r.ticker: (r.weight_pct / 100.0)
                   for r in df.itertuples() if np.isfinite(r.weight_pct)}

        # The day's biggest mover, needed by the lede below. Computed here
        # rather than in its old position ~900px down the page, because the
        # sentence it produces is the single most useful thing on the tab and
        # it was previously below the fold.
        try:
            contrib = pm.day_move_contributions(df, portfolio.get("cash", 0.0))
        except Exception:  # noqa: BLE001 — an insight, never a blocker
            contrib = None

        _render_lede(summary, sector_df, contrib, sym)

        # The holdings table sums to invested equity, but "Total value" adds
        # cash on top — so the two numbers visibly disagree by exactly the cash
        # balance, and the reconciliation used to live only inside a (?) tooltip
        # on an unrelated tile. A beginner reading a $5,000 gap concludes the
        # app is broken. State it in the open instead.
        cash = summary.get("cash") or 0.0
        invested = (summary.get("total_value") or 0.0) - cash
        if cash > 0:
            # fmt_money_md, not fmt_money: three bare $ in one markdown string
            # makes Streamlit read the span between the first two as LaTeX and
            # paint it as a code block. This exact sentence did that.
            _md = theme.fmt_money_md
            st.caption(
                f"{_md(summary['total_value'], sym)} total = "
                f"{_md(invested, sym)} invested in the {summary['num_positions']} "
                f"holdings below, plus {_md(cash, sym)} cash you haven’t invested. "
                f"The table below shows the invested part."
            )

        # theme.notice, not st.warning: st.warning is aria-live="assertive" and
        # these re-render on every rerun, interrupting a screen reader each time
        # with a message that has not changed.
        flags = pm.concentration_flags(df, sector_df)
        if flags:
            for f in flags:
                theme.notice(f, "warn")
        else:
            theme.notice("Well diversified — no single position, sector, or top-3 "
                         "cluster exceeds the risk guidelines.", "good")

        # ---- Who moved you today ------------------------------------------
        # The headline said the book moved +0.54% but never which holding did
        # it. These contributions sum to that number exactly (same denominator,
        # see pm.day_move_contributions), so the breakdown cannot disagree with
        # the tile above it.
        # Reuses the `contrib` computed for the lede rather than recomputing it.
        # The lede names the top mover; this section is the full distribution,
        # so it opens on the tally instead of repeating that sentence verbatim
        # 900px further down.
        try:
            if contrib is not None and not contrib.empty and len(contrib) > 1:
                theme.section("Who moved you today")
                helped = contrib[contrib["contribution_pct"] > 0]
                hurt = contrib[contrib["contribution_pct"] < 0]
                st.markdown(
                    f"**{len(helped)} holding{'s' if len(helped) != 1 else ''}** "
                    f"helped, **{len(hurt)}** held you back."
                )
                st.plotly_chart(_contribution_bar(contrib, sym),
                                width="stretch", config=theme.CHART_CONFIG)
                st.caption(
                    "Impact is size × move, not move alone: a small position "
                    "jumping 10% can matter less than your largest holding "
                    "drifting 1%. These add up to the day change shown above."
                )
        except Exception as e:  # noqa: BLE001 — an insight, never a blocker
            st.caption(f"Contribution breakdown unavailable: {e}")

        theme.section("Holdings")
        _render_positions_table(df, sym)
    except Exception as e:  # noqa: BLE001 — keep the tab alive
        st.error(f"Could not compute portfolio summary: {e}")
        return

    # ---- Correlation heatmap ----------------------------------------------
    # The sector donut used to sit here beside the heatmap. It has moved into
    # the lede, where it earns its place by turning the headline number into a
    # picture; drawing it twice on one tab would have been the page telling the
    # reader the same thing in the same way in two places. The heatmap takes
    # the full width it always wanted — it is a matrix, and half a column was
    # never enough for one.
    theme.section("How concentrated you really are")
    try:
        corr = pm.correlation_matrix(contexts)
        if corr is None or corr.shape[0] < 2 or corr.isna().all().all():
            st.info("Correlation needs at least two holdings with price "
                    "history — add another position to see the matrix.",
                    icon=":material/grid_on:")
        else:
            st.plotly_chart(_heatmap(corr), width="stretch",
                            config=theme.CHART_CONFIG)
            avg_rho = pm.average_pairwise_correlation(corr)
            pair = pm.most_correlated_pair(corr)
            bits = []
            if np.isfinite(avg_rho):
                bits.append(f"Average pairwise correlation **{avg_rho:.2f}**.")
            if pair:
                a, b, v = pair
                bits.append(
                    f"Most correlated: **{a}–{b}** at ρ = {v:.2f} — "
                    + ("they move almost as one, so holding both adds little "
                       "diversification." if v > 0.7 else
                       "moderately linked."))
            if bits:
                st.caption(" ".join(bits))
    except Exception as e:  # noqa: BLE001
        st.error(f"Correlation chart unavailable: {e}")

    # ---- Portfolio beta (regressed on SPY, with R²) -----------------------
    theme.section("How much market risk you are carrying")
    bcol, icol = st.columns([1, 2])
    stats = {"beta": np.nan, "r_squared": np.nan, "n_days": 0}
    try:
        stats = pm.market_model(contexts, weights, spy_history)
    except Exception:  # noqa: BLE001 — SPY fetch may fail off-network; degrade
        pass
    beta = stats["beta"]
    with bcol:
        st.metric("Beta vs S&P 500 (invested equity)",
                  "N/A" if not np.isfinite(beta) else f"{beta:.2f}")
    with icol:
        if np.isfinite(beta):
            pctmove = abs(beta - 1) * 100
            direction = "more" if beta > 1 else "less"
            st.markdown(
                f"A beta of **{beta:.2f}** means your invested equity tends to move "
                f"about **{pctmove:.0f}% {direction}** than the market. "
                + ("More aggressive than the index — bigger up days and bigger "
                   "down days." if beta > 1 else "More defensive than the index."))
            if np.isfinite(stats["r_squared"]):
                st.caption(
                    f"OLS on {stats['n_days']} days of 1y daily returns; "
                    f"the market explains R² = {stats['r_squared']:.0%} of your "
                    f"variance. Beta is regime-dependent — a rough sensitivity, "
                    f"not a constant.")
        else:
            st.caption("Beta needs SPY history (network / data layer). Unavailable "
                       "right now.")

    # ---- Risk & diversification snapshot ----------------------------------
    try:
        rm = pm.risk_metrics(contexts, weights, spy_history)
        dv = pm.diversification_score(weights)
        r1, r2, r3, r4 = st.columns(4)
        r1.metric(
            "Annualized volatility",
            "N/A" if not np.isfinite(rm["port_vol"]) else f"{rm['port_vol'] * 100:.1f}%",
            help="Std. dev. of daily returns × √252. "
                 + ("" if not np.isfinite(rm["spy_vol"]) else f"S&P: {rm['spy_vol'] * 100:.1f}%."))
        r2.metric(
            "Max drawdown (1y)",
            "N/A" if not np.isfinite(rm["max_drawdown"]) else f"{rm['max_drawdown'] * 100:.1f}%",
            help="Largest peak-to-trough drop over the year.")
        eff = dv["effective_n"]
        r3.metric(
            "Effective holdings",
            "N/A" if not np.isfinite(eff) else f"{eff:.1f}",
            help=f"1 / HHI — the number of equal-weight positions that would match "
                 f"your concentration. You hold {dv['n_positions']}.")
        if np.isfinite(rm["port_total_return"]) and np.isfinite(rm["spy_total_return"]):
            r4.metric(
                "1y return", f"{rm['port_total_return'] * 100:+.1f}%",
                delta=f"{(rm['port_total_return'] - rm['spy_total_return']) * 100:+.1f}% vs S&P",
                delta_color="normal")
        else:
            r4.metric("1y return", "N/A")

        # Say what those four numbers MEAN. Beta already gets a plain-language
        # sentence directly above; these four got a (?) tooltip each, which is
        # hover-only and gone on touch. The inconsistency taught the beginner
        # that some numbers on this page are for her and some are not.
        # PRODUCT.md principle 5: explain to the beginner, let the evaluator
        # drill down — one surface, two depths.
        bits = []
        if np.isfinite(rm["port_vol"]):
            vol = rm["port_vol"] * 100
            if np.isfinite(rm["spy_vol"]):
                spy_vol = rm["spy_vol"] * 100
                calmer = "calmer than" if vol < spy_vol else "choppier than"
                if abs(vol - spy_vol) < 1.0:
                    calmer = "about as jumpy as"
                bits.append(
                    f"In a typical year your holdings swing about "
                    f"**{vol:.0f}%** up or down — {calmer} the S&P 500's "
                    f"{spy_vol:.0f}%.")
            else:
                bits.append(f"In a typical year your holdings swing about "
                            f"**{vol:.0f}%** up or down.")
        if np.isfinite(rm["max_drawdown"]):
            bits.append(
                f"The worst stretch of the past year took the book "
                f"**{abs(rm['max_drawdown']) * 100:.1f}%** below its own peak "
                f"before recovering — that is the drop you would have had to sit "
                f"through.")
        eff_n, n_pos = dv["effective_n"], dv["n_positions"]
        if np.isfinite(eff_n):
            if eff_n < n_pos - 0.5:
                bits.append(
                    f"And although you hold **{n_pos}** positions, they are "
                    f"uneven enough that the book behaves like roughly "
                    f"**{eff_n:.0f} equal-sized** ones.")
            else:
                bits.append(
                    f"Your **{n_pos}** positions are evenly enough sized that "
                    f"the book behaves like about {eff_n:.0f} equal ones — "
                    f"no single holding dominates.")
        if bits:
            st.markdown(" ".join(bits))
    except Exception:  # noqa: BLE001 — snapshot is a bonus; never break the tab
        pass

    # ---- Performance vs benchmark -----------------------------------------
    try:
        perf = pm.performance_vs_benchmark(contexts, weights, spy_history)
        if perf is not None and not perf.empty:
            theme.section("How this book would have performed")
            st.plotly_chart(_perf_line(perf), width="stretch",
                            config=theme.CHART_CONFIG)
            st.caption("Hypothetical: today's holdings held at constant weights "
                       "(daily-rebalanced) over the past year — a backtest of your "
                       "current book, not a realized track record. Ignores trades, "
                       "costs, and taxes.")
        else:
            st.info("Performance chart needs overlapping price history for your "
                    "holdings and SPY.")
    except Exception as e:  # noqa: BLE001
        st.error(f"Performance chart unavailable: {e}")

    st.caption("Weights are computed on invested equity (cash excluded). "
               "Not investment advice.")
