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
# Shared design system — one source of truth for colours/formatting across all
# three tabs. (Aliased to the local names this module already uses.)
from theme import (
    AXIS, BAD, CATEGORICAL, CURRENCY_SYMBOL, DIVERGING, GOOD, GRID, INK, INK_2,
    MUTED, SURFACE,
    fmt_money as _money, fmt_pct as _pct, style_fig as _style_fig,
)


def _sym(portfolio: dict) -> str:
    return CURRENCY_SYMBOL.get(portfolio.get("currency", "USD"), "$")


# --------------------------------------------------------------------------
# Chart builders
# --------------------------------------------------------------------------

def _donut(sector_df: pd.DataFrame, sym: str = "$") -> go.Figure:
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
    fig.update_layout(title="Sector allocation", showlegend=False)
    fig.add_annotation(text=f"<b>{sym}{invested:,.0f}</b><br><span style='font-size:11px'>invested</span>",
                       showarrow=False, font=dict(color=INK, size=18))
    return _style_fig(fig)


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
    fig.update_layout(title="Correlation of daily returns (1y)")
    fig.update_yaxes(autorange="reversed")
    return _style_fig(fig)


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
        title="Growth of 100 — portfolio vs S&P 500 (1y)",
        legend=dict(orientation="h", y=1.12, x=0),
        xaxis_title="Date", yaxis_title="Index (start = 100)",
    )
    return _style_fig(fig, height=360)


# --------------------------------------------------------------------------
# Positions table (conditional green/red styling)
# --------------------------------------------------------------------------

def _render_positions_table(df: pd.DataFrame, sym: str) -> None:
    show = df.rename(columns={
        "ticker": "Ticker", "shares": "Shares", "cost_basis": "Cost basis",
        "current_price": "Current", "market_value": "Market value",
        "pnl_abs": "P&L", "pnl_pct": "P&L %", "weight_pct": "Weight %",
        "day_change_pct": "Day %",
    })

    from theme import signed_color as color_signed   # shared green/red logic

    styler = (
        show.style
        .format({
            "Shares": "{:,.0f}", "Cost basis": f"{sym}{{:,.2f}}".format,
            "Current": lambda v: _money(v, sym), "Market value": lambda v: _money(v, sym),
            "P&L": lambda v: _money(v, sym), "P&L %": _pct,
            "Weight %": lambda v: "N/A" if not np.isfinite(v) else f"{v:.1f}%",
            "Day %": _pct,
        }, na_rep="N/A")
        .map(color_signed, subset=["P&L", "P&L %", "Day %"])
    )
    st.dataframe(styler, width="stretch", hide_index=True)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def render(portfolio: dict) -> None:
    # ---- Empty state -------------------------------------------------------
    if not portfolio or not portfolio.get("positions"):
        st.info("📭 Upload a portfolio CSV or load the demo portfolio from the "
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
            f"⚠️ No market data for **{', '.join(unresolved)}** — shown as N/A below. "
            + ("Not in the offline fixture; run without USE_MOCK to fetch it live."
               if offline else "Check the symbol — it may be mistyped or delisted.")
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

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total value", _money(summary["total_value"], sym),
                  help="Equity holdings + cash.")
        c2.metric(
            "Total P&L", _money(summary["total_pnl_abs"], sym),
            delta=_pct(summary["total_pnl_pct"]), delta_color="normal",
            help="Return on cost basis (invested equity).",
        )
        c3.metric(
            "Today's change", _money(summary["day_change_abs"], sym),
            delta=_pct(summary["day_change_pct"]), delta_color="normal",
            help="Day's equity move as a % of yesterday's total account value.",
        )
        c4.metric("Positions", f"{summary['num_positions']}",
                  help=f"Cash: {_money(summary['cash'], sym)}")

        st.divider()

        flags = pm.concentration_flags(df, sector_df)
        if flags:
            for f in flags:
                st.warning("⚠️ " + f)
        else:
            st.success("✅ Well diversified — no single position, sector, or top-3 "
                       "cluster exceeds the risk guidelines.")

        st.subheader("Holdings")
        _render_positions_table(df, sym)
    except Exception as e:  # noqa: BLE001 — keep the tab alive
        st.error(f"Could not compute portfolio summary: {e}")
        return

    st.divider()

    # ---- Sector donut + correlation heatmap (each isolated) ---------------
    left, right = st.columns(2)
    with left:
        try:
            st.plotly_chart(_donut(sector_df, sym), width="stretch")
        except Exception as e:  # noqa: BLE001
            st.error(f"Sector chart unavailable: {e}")
    with right:
        try:
            corr = pm.correlation_matrix(contexts)
            if corr is None or corr.shape[0] < 2 or corr.isna().all().all():
                st.info("📈 Correlation needs at least two holdings with price "
                        "history — add another position to see the matrix.")
            else:
                st.plotly_chart(_heatmap(corr), width="stretch")
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

    st.divider()

    # ---- Portfolio beta (regressed on SPY, with R²) -----------------------
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
    except Exception:  # noqa: BLE001 — snapshot is a bonus; never break the tab
        pass

    # ---- Performance vs benchmark -----------------------------------------
    try:
        perf = pm.performance_vs_benchmark(contexts, weights, spy_history)
        if perf is not None and not perf.empty:
            st.plotly_chart(_perf_line(perf), width="stretch")
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
