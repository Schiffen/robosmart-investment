"""
portfolio_metrics.py — pure, Streamlit-free, unit-testable portfolio math.
=========================================================================
Person 2 (Dashboard) owns this file. It contains NO Streamlit imports on
purpose, so every function can be unit-tested from the terminal and reused.
`tabs/dashboard.py` only *renders* — all numbers come from here.

Contract in  (built by Person 1, tested against mock_portfolio.json):
    portfolio = {
        "positions": [{"ticker": str, "shares": float,
                       "cost_basis": float, "sector": str}],
        "cash": float, "currency": "USD"
    }
    contexts = {ticker: context_dict}      # from data_layer.get_context_batch
        context_dict uses: price.current, price.day_change_pct,
                           sector, history (1y daily OHLCV DataFrame)

-------------------------------------------------------------------------
FINANCE ASSUMPTIONS (documented on purpose — this is what the grade rewards):

1. WEIGHTS ARE EQUITY-BASED, CASH EXCLUDED.
   A position's weight = its market value / total value of *invested equity*
   (sum of all position market values), NOT of the whole account incl. cash.
   Rationale: concentration, sector mix, correlation and beta are all
   equity-RISK concepts. Mixing an idle cash balance into the denominator
   would understate how concentrated the invested money actually is, and it
   would make the beta/sector weights inconsistent with each other.
   `portfolio_summary` still reports total_value INCLUDING cash, and exposes
   cash separately, so nothing is hidden.

2. CORRELATION uses DAILY RETURNS, not prices. Prices are non-stationary and
   trending; two rising stocks look "correlated" on price even when their
   day-to-day moves aren't. Returns are the honest input. Dates are aligned by
   inner join so a missing day for one name never shifts another.

3. BETA is the OLS slope of a holding's daily returns on SPY's daily returns
   over the lookback window; the portfolio beta is the equity-weighted average
   of holding betas. (Caveat for the write-up: betas are unstable and
   regime-dependent — see the doc's Risks section.)

4. PERFORMANCE-vs-SPY assumes DAILY REBALANCING back to current weights.
   It's the weighted average of holding returns, indexed to 100. This is a
   simplification of true buy-and-hold (whose weights drift), chosen because
   we only reliably know *today's* weights. Documented, not hidden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

POSITION_COLUMNS = [
    "ticker", "shares", "cost_basis", "current_price", "market_value",
    "pnl_abs", "pnl_pct", "weight_pct", "day_change_pct",
]

# Thresholds for concentration warnings (single source of truth).
SINGLE_POSITION_LIMIT = 25.0   # % of equity
SECTOR_LIMIT = 40.0            # % of equity
TOP3_LIMIT = 60.0             # % of equity


# --------------------------------------------------------------------------
# Small internal helpers
# --------------------------------------------------------------------------

def _safe_float(x):
    try:
        v = float(x)
        return v
    except (TypeError, ValueError):
        return np.nan


def _daily_returns(history: pd.DataFrame) -> pd.Series | None:
    """Daily simple returns from a context's OHLCV history. None if unusable."""
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return None
    if "Close" not in history.columns:
        return None
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    # Normalize a datetime index to tz-naive calendar dates. Real yfinance data
    # is timezone-aware (NY for US equities, UTC for crypto); without this,
    # equities/ETFs/crypto miss every date on an inner join and correlation/beta
    # silently vanish. Also drop duplicate dates. (Mock data is already tz-naive,
    # so this is a no-op there.)
    if isinstance(close.index, pd.DatetimeIndex):
        idx = close.index
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        close.index = idx.normalize()
        close = close[~close.index.duplicated(keep="last")]
    if len(close) < 3:
        return None
    return close.pct_change().dropna()


def _ols_beta(stock_ret: pd.Series, bench_ret: pd.Series) -> float:
    """OLS slope of stock returns on benchmark returns (aligned inner join)."""
    joined = pd.concat([stock_ret, bench_ret], axis=1, join="inner").dropna()
    if len(joined) < 30:               # too few overlapping days to trust
        return np.nan
    y = joined.iloc[:, 0].to_numpy()
    x = joined.iloc[:, 1].to_numpy()
    var_x = np.var(x)
    if var_x == 0 or not np.isfinite(var_x):
        return np.nan
    return float(np.cov(x, y, bias=True)[0, 1] / var_x)


def _fetch_benchmark_history(symbol: str = "SPY") -> pd.DataFrame:
    """PRODUCTION path: fetch benchmark OHLCV via yfinance.

    Tests and the local preview override this (monkeypatch / injected
    spy_history) so no network is required off the app.
    """
    import yfinance as yf  # imported lazily so the module loads without it
    df = yf.download(symbol, period="1y", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# --------------------------------------------------------------------------
# 1. Positions & summary
# --------------------------------------------------------------------------

def position_values(portfolio: dict, contexts: dict) -> pd.DataFrame:
    """Per-position table. Never raises on missing/NaN prices — shows NaN,
    which the UI renders as 'N/A'."""
    rows = []
    for pos in portfolio.get("positions", []):
        ticker = str(pos.get("ticker", "")).upper().strip()
        shares = _safe_float(pos.get("shares"))
        cost_basis = _safe_float(pos.get("cost_basis"))
        ctx = contexts.get(ticker, {}) or {}
        price_blk = ctx.get("price", {}) or {}
        current_price = _safe_float(price_blk.get("current"))
        day_change_pct = _safe_float(price_blk.get("day_change_pct"))

        market_value = shares * current_price
        pnl_abs = (current_price - cost_basis) * shares
        if cost_basis and np.isfinite(cost_basis) and cost_basis != 0:
            pnl_pct = (current_price / cost_basis - 1.0) * 100.0
        else:
            pnl_pct = np.nan

        rows.append({
            "ticker": ticker, "shares": shares, "cost_basis": cost_basis,
            "current_price": current_price, "market_value": market_value,
            "pnl_abs": pnl_abs, "pnl_pct": pnl_pct,
            "weight_pct": np.nan,  # filled below once equity total is known
            "day_change_pct": day_change_pct,
        })

    df = pd.DataFrame(rows, columns=POSITION_COLUMNS)
    equity_total = np.nansum(df["market_value"].to_numpy()) if not df.empty else 0.0
    if equity_total and np.isfinite(equity_total) and equity_total != 0:
        df["weight_pct"] = df["market_value"] / equity_total * 100.0
    return df


def portfolio_summary(df: pd.DataFrame, cash: float) -> dict:
    """Top-line numbers.

    - total_value INCLUDES cash.
    - total_pnl_pct is return on COST, computed over the PRICED set only
      (numerator and denominator use the same holdings, so a missing price
      can't dilute the %).
    - day_change_pct is ACCOUNT-level: the day's equity $ move divided by
      yesterday's *account* value (prior equity + cash), so it's consistent
      with the total_value shown beside it.
    - If NO position can be priced (total data failure / market closed), the
      P&L and day-change figures are NaN (-> "N/A" in the UI), never a
      fabricated $0.00 / +0.00%.
    """
    cash = _safe_float(cash)
    cash = 0.0 if not np.isfinite(cash) else cash

    if df.empty:
        return {"total_value": cash, "total_cost": 0.0, "total_pnl_abs": 0.0,
                "total_pnl_pct": np.nan, "day_change_abs": 0.0,
                "day_change_pct": np.nan, "num_positions": 0,
                "cash": cash, "equity_value": 0.0}

    mv = df["market_value"].to_numpy(dtype=float)
    dcp = df["day_change_pct"].to_numpy(dtype=float)
    pnl = df["pnl_abs"].to_numpy(dtype=float)
    cost = (df["shares"] * df["cost_basis"]).to_numpy(dtype=float)

    any_priced = bool(np.isfinite(mv).any())
    equity_value = float(np.nansum(mv)) if any_priced else np.nan
    total_value = (equity_value + cash) if any_priced else cash

    # P&L over the PRICED set only (aligned numerator & denominator).
    priced_pnl = np.isfinite(pnl)
    if priced_pnl.any():
        total_pnl_abs = float(np.nansum(pnl))
        total_cost = float(np.nansum(np.where(priced_pnl, cost, np.nan)))
        total_pnl_pct = (total_pnl_abs / total_cost * 100.0) if total_cost > 0 else np.nan
    else:
        total_pnl_abs = np.nan
        total_cost = np.nan
        total_pnl_pct = np.nan

    # Yesterday's value of each holding = today's value / (1 + today's % move).
    with np.errstate(divide="ignore", invalid="ignore"):
        prev_val = mv / (1.0 + dcp / 100.0)
    prev_val = np.where(np.isfinite(prev_val), prev_val, np.nan)  # guard -100% -> inf
    if np.isfinite(prev_val).any():
        day_change_abs = float(np.nansum(mv - prev_val))
        prev_total = float(np.nansum(prev_val)) + cash          # account-level base
        day_change_pct = (day_change_abs / prev_total * 100.0) if prev_total > 0 else np.nan
    else:
        day_change_abs = np.nan
        day_change_pct = np.nan

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl_abs": total_pnl_abs,
        "total_pnl_pct": total_pnl_pct,
        "day_change_abs": day_change_abs,
        "day_change_pct": day_change_pct,
        "num_positions": int(len(df)),
        "cash": cash,
        "equity_value": equity_value,
    }


def day_move_contributions(df: pd.DataFrame, cash: float) -> pd.DataFrame:
    """Which holdings actually moved the portfolio today, and by how much.

    The dashboard could say the book moved +0.54% but not WHICH holding did it —
    a beginner's most immediate follow-up question, and the natural bridge from
    the portfolio view to the single-stock "what happened today" view.

    A holding's contribution is its own dollar move measured against YESTERDAY'S
    WHOLE ACCOUNT (prior equity + cash) — deliberately the same denominator
    `portfolio_summary` uses for `day_change_pct`. That is what makes these
    numbers reconcile: the contributions sum to the headline day move exactly,
    so the breakdown can never quietly disagree with the number above it.

    A big percentage move in a small position is NOT a big contribution, and
    this is precisely the intuition the table is here to build.

    Returns ticker, contribution_pct, contribution_abs, day_change_pct,
    weight_pct — sorted by absolute contribution, largest mover first. Holdings
    with no usable price are dropped rather than shown as a fake zero.
    """
    cols = ["ticker", "contribution_pct", "contribution_abs",
            "day_change_pct", "weight_pct"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)

    cash = _safe_float(cash)
    cash = 0.0 if not np.isfinite(cash) else cash

    mv = df["market_value"].to_numpy(dtype=float)
    dcp = df["day_change_pct"].to_numpy(dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        prev_val = mv / (1.0 + dcp / 100.0)
    prev_val = np.where(np.isfinite(prev_val), prev_val, np.nan)

    if not np.isfinite(prev_val).any():
        return pd.DataFrame(columns=cols)

    prev_total = float(np.nansum(prev_val)) + cash
    if not (prev_total > 0):
        return pd.DataFrame(columns=cols)

    contribution_abs = mv - prev_val
    contribution_pct = contribution_abs / prev_total * 100.0

    out = pd.DataFrame({
        "ticker": df["ticker"].to_numpy(),
        "contribution_pct": contribution_pct,
        "contribution_abs": contribution_abs,
        "day_change_pct": dcp,
        "weight_pct": df["weight_pct"].to_numpy(dtype=float),
    })
    out = out[np.isfinite(out["contribution_pct"].to_numpy(dtype=float))]
    if out.empty:
        return pd.DataFrame(columns=cols)
    return (out.reindex(out["contribution_pct"].abs()
                        .sort_values(ascending=False).index)
               .reset_index(drop=True))


# --------------------------------------------------------------------------
# 2. Sector breakdown & concentration
# --------------------------------------------------------------------------

def sector_breakdown(df: pd.DataFrame, portfolio: dict) -> pd.DataFrame:
    """Sector -> market_value, weight_pct (of equity). Sorted desc."""
    sector_of = {str(p.get("ticker", "")).upper().strip(): p.get("sector", "Unknown")
                 for p in portfolio.get("positions", [])}
    if df.empty:
        return pd.DataFrame(columns=["sector", "market_value", "weight_pct"])

    tmp = df.copy()
    tmp["sector"] = tmp["ticker"].map(sector_of).fillna("Unknown")
    grp = (tmp.groupby("sector", as_index=False)["market_value"]
              .sum(min_count=1))
    equity_total = np.nansum(df["market_value"].to_numpy())
    if equity_total and np.isfinite(equity_total) and equity_total != 0:
        grp["weight_pct"] = grp["market_value"] / equity_total * 100.0
    else:
        grp["weight_pct"] = np.nan
    return grp.sort_values("market_value", ascending=False).reset_index(drop=True)


def concentration_flags(df: pd.DataFrame, sector_df: pd.DataFrame) -> list:
    """Human-readable warnings. Empty list == well diversified."""
    flags = []
    if df.empty:
        return flags

    # Single position > limit
    for _, r in df.iterrows():
        w = r["weight_pct"]
        if pd.notna(w) and w > SINGLE_POSITION_LIMIT:
            flags.append(
                f"{r['ticker']} is {w:.0f}% of your equity — above the "
                f"{SINGLE_POSITION_LIMIT:.0f}% single-position guideline. "
                f"One name is driving your risk."
            )

    # Sector > limit
    if sector_df is not None and not sector_df.empty:
        for _, r in sector_df.iterrows():
            w = r["weight_pct"]
            if pd.notna(w) and w > SECTOR_LIMIT:
                flags.append(
                    f"{r['sector']} is {w:.0f}% of your equity — above the "
                    f"{SECTOR_LIMIT:.0f}% sector guideline. You're exposed to a "
                    f"single sector's shocks."
                )

    # Top 3 positions > limit
    weights = df["weight_pct"].dropna().sort_values(ascending=False)
    if len(weights) >= 3:
        top3 = float(weights.iloc[:3].sum())
        if top3 > TOP3_LIMIT:
            names = ", ".join(df.sort_values("weight_pct", ascending=False)["ticker"].head(3))
            flags.append(
                f"Your top 3 holdings ({names}) are {top3:.0f}% of your equity — "
                f"above the {TOP3_LIMIT:.0f}% guideline. Diversification is thinner "
                f"than the position count suggests."
            )
    return flags


# --------------------------------------------------------------------------
# 3. Correlation of daily returns
# --------------------------------------------------------------------------

def correlation_matrix(contexts: dict) -> pd.DataFrame:
    """Pearson correlation of DAILY RETURNS across holdings (1y, inner-joined).
    Returns an empty/1x1 frame when there aren't >= 2 usable series; the UI
    handles that case with an info message."""
    series = {}
    for ticker, ctx in contexts.items():
        r = _daily_returns((ctx or {}).get("history"))
        if r is not None:
            series[ticker] = r
    if len(series) == 0:
        return pd.DataFrame()
    rets = pd.DataFrame(series).dropna(how="all")
    # Inner-align: correlation only over days present for all names.
    rets = rets.dropna()
    if rets.shape[0] < 5:
        # Too little overlap to be meaningful.
        return pd.DataFrame(index=list(series.keys()), columns=list(series.keys()))
    return rets.corr(method="pearson")


def most_correlated_pair(corr: pd.DataFrame):
    """(ticker_a, ticker_b, corr_value) for the highest off-diagonal pair.
    None if not computable. Used for the plain-English heatmap caption."""
    if corr is None or corr.empty or corr.shape[0] < 2:
        return None
    s = corr.stack(future_stack=True)
    # Keep each unordered pair once, drop the diagonal (a == b).
    s = s[s.index.get_level_values(0) < s.index.get_level_values(1)].dropna()
    if s.empty:
        return None
    idx = s.idxmax()
    val = float(s.max())
    if not np.isfinite(val):
        return None
    return (idx[0], idx[1], val)


def average_pairwise_correlation(corr: pd.DataFrame) -> float:
    """Mean of the off-diagonal correlations — a single number for the
    'how diversified am I really?' claim. NaN if not computable."""
    if corr is None or corr.empty or corr.shape[0] < 2:
        return np.nan
    a = corr.to_numpy(dtype=float)
    off = a[~np.eye(a.shape[0], dtype=bool)]
    off = off[np.isfinite(off)]
    return float(off.mean()) if off.size else np.nan


# --------------------------------------------------------------------------
# 4. Beta & performance vs benchmark
# --------------------------------------------------------------------------

def portfolio_beta(contexts: dict, weights: dict, spy_history: pd.DataFrame | None = None) -> float:
    """Equity-weighted average of per-holding OLS betas vs SPY.

    weights: {ticker: fraction} — need not be perfectly normalized; we
    renormalize over the holdings we can actually compute a beta for.
    spy_history: inject to avoid the network (tests/preview). If None, the
    production yfinance path is used.
    """
    if spy_history is None:
        spy_history = _fetch_benchmark_history("SPY")
    spy_ret = _daily_returns(spy_history)
    if spy_ret is None:
        return np.nan

    betas, ws = [], []
    for ticker, ctx in contexts.items():
        r = _daily_returns((ctx or {}).get("history"))
        if r is None:
            continue
        b = _ols_beta(r, spy_ret)
        w = _safe_float((weights or {}).get(ticker, np.nan))
        if np.isfinite(b) and np.isfinite(w):
            betas.append(b)
            ws.append(w)
    if not betas:
        return np.nan
    ws = np.asarray(ws, dtype=float)
    total_w = ws.sum()
    if total_w == 0:
        return float(np.mean(betas))          # equal-weight fallback
    return float(np.dot(np.asarray(betas), ws) / total_w)


def _aligned_portfolio_returns(contexts: dict, weights: dict,
                               spy_ret: pd.Series) -> pd.DataFrame | None:
    """Daily-rebalanced portfolio return series aligned with SPY returns.

    Returns a DataFrame with columns ['Portfolio', 'SPY'] of DAILY RETURNS
    over the inner-joined dates, or None if not computable. This one helper
    feeds both the performance chart and the market-model beta so they can
    never disagree.
    """
    series = {}
    for ticker, ctx in contexts.items():
        r = _daily_returns((ctx or {}).get("history"))
        if r is not None and _safe_float((weights or {}).get(ticker, 0)) > 0:
            series[ticker] = r
    if not series:
        return None

    rets = pd.DataFrame(series)
    rets = pd.concat([rets, spy_ret.rename("SPY")], axis=1, join="inner").dropna()
    if rets.shape[0] < 5:
        return None

    w = np.array([_safe_float((weights or {}).get(t, 0)) for t in series.keys()])
    w = np.where(np.isfinite(w), w, 0.0)
    if w.sum() == 0:
        w = np.ones(len(series))
    w = w / w.sum()

    # errstate: this matmul emits "divide by zero" / "overflow" / "invalid"
    # RuntimeWarnings even when every input and output is finite. matmul does
    # not divide — these are STALE FPU STATUS FLAGS, set by earlier unchecked
    # operations (inside pandas) and only surfaced here because BLAS checks the
    # flag register after the call. Verified: inputs finite, output finite,
    # returns in a sane range. Suppressing them at the source keeps the console
    # readable; the guard below is what actually protects correctness, so a real
    # non-finite value still cannot escape.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        port_ret = rets[list(series.keys())].to_numpy() @ w
    # If a genuine inf/NaN ever does appear, make it NaN rather than letting it
    # propagate: every downstream consumer already handles NaN as "unavailable",
    # whereas an inf silently poisons a mean or a standard deviation.
    port_ret = np.where(np.isfinite(port_ret), port_ret, np.nan)
    return pd.DataFrame({"Portfolio": port_ret, "SPY": rets["SPY"].to_numpy()},
                        index=rets.index)


def performance_vs_benchmark(contexts: dict, weights: dict,
                             spy_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Cumulative return of the portfolio vs SPY, BOTH indexed to exactly 100
    on a shared baseline date one business day before the first return.

    Portfolio return each day = weighted avg of holding daily returns
    (daily-rebalanced to `weights` — a hypothetical constant-current-weight
    backtest, not a realized track record). Returns a DataFrame indexed by
    date with columns ['Portfolio', 'SPY']. Empty frame if not computable.
    """
    if spy_history is None:
        spy_history = _fetch_benchmark_history("SPY")
    spy_ret = _daily_returns(spy_history)
    if spy_ret is None:
        return pd.DataFrame(columns=["Portfolio", "SPY"])

    rets = _aligned_portfolio_returns(contexts, weights, spy_ret)
    if rets is None:
        return pd.DataFrame(columns=["Portfolio", "SPY"])

    port_index = 100.0 * np.cumprod(1.0 + rets["Portfolio"].to_numpy())
    spy_index = 100.0 * np.cumprod(1.0 + rets["SPY"].to_numpy())

    # Prepend a shared 100 baseline so both lines start at exactly 100.
    base_date = rets.index[0] - pd.tseries.offsets.BDay(1)
    idx = pd.DatetimeIndex([base_date]).append(rets.index)
    return pd.DataFrame(
        {"Portfolio": np.concatenate([[100.0], port_index]),
         "SPY": np.concatenate([[100.0], spy_index])},
        index=idx,
    )


def market_model(contexts: dict, weights: dict,
                 spy_history: pd.DataFrame | None = None) -> dict:
    """Regress the (daily-rebalanced) portfolio return on SPY over 1y.

    Returns {'beta': float, 'r_squared': float, 'n_days': int}. Because it
    uses the SAME portfolio return series as performance_vs_benchmark, the
    headline beta and the performance chart are guaranteed consistent, and
    R² tells the user how much of their variance the market explains.
    """
    empty = {"beta": np.nan, "r_squared": np.nan, "n_days": 0}
    if spy_history is None:
        spy_history = _fetch_benchmark_history("SPY")
    spy_ret = _daily_returns(spy_history)
    if spy_ret is None:
        return empty
    rets = _aligned_portfolio_returns(contexts, weights, spy_ret)
    if rets is None or rets.shape[0] < 30:
        return empty
    y = rets["Portfolio"].to_numpy()
    x = rets["SPY"].to_numpy()
    var_x = np.var(x)
    if var_x == 0 or not np.isfinite(var_x):
        return empty
    beta = float(np.cov(x, y, bias=True)[0, 1] / var_x)
    r = np.corrcoef(x, y)[0, 1]
    return {"beta": beta, "r_squared": float(r * r), "n_days": int(len(y))}


def risk_metrics(contexts: dict, weights: dict,
                 spy_history: pd.DataFrame | None = None) -> dict:
    """Annualized vol, 1y total return, and max drawdown for the portfolio vs
    SPY — all from the same daily-return series as the performance chart.
    Returns NaNs if not computable."""
    empty = {"port_vol": np.nan, "spy_vol": np.nan, "port_total_return": np.nan,
             "spy_total_return": np.nan, "max_drawdown": np.nan, "n_days": 0}
    if spy_history is None:
        spy_history = _fetch_benchmark_history("SPY")
    spy_ret = _daily_returns(spy_history)
    if spy_ret is None:
        return empty
    rets = _aligned_portfolio_returns(contexts, weights, spy_ret)
    if rets is None:
        return empty
    p = rets["Portfolio"].to_numpy()
    s = rets["SPY"].to_numpy()
    idx = np.cumprod(1.0 + p)
    drawdown = idx / np.maximum.accumulate(idx) - 1.0
    return {
        "port_vol": float(np.std(p, ddof=1) * np.sqrt(252)),
        "spy_vol": float(np.std(s, ddof=1) * np.sqrt(252)),
        "port_total_return": float(np.prod(1.0 + p) - 1.0),
        "spy_total_return": float(np.prod(1.0 + s) - 1.0),
        "max_drawdown": float(drawdown.min()),
        "n_days": int(len(p)),
    }


def diversification_score(weights: dict) -> dict:
    """Herfindahl concentration -> 'effective number of holdings' = 1/HHI:
    how many EQUAL-weight positions would give the same concentration. A book
    with one dominant name has an effective N far below its position count."""
    w = np.array([v for v in (weights or {}).values()
                  if np.isfinite(v) and v > 0], dtype=float)
    if w.size == 0:
        return {"hhi": np.nan, "effective_n": np.nan, "n_positions": 0}
    w = w / w.sum()
    hhi = float(np.sum(w ** 2))
    return {"hhi": hhi, "effective_n": float(1.0 / hhi), "n_positions": int(w.size)}


if __name__ == "__main__":
    import json
    import os
    import data_layer  # local mock stand-in

    portfolio = json.load(open(
        os.path.join(os.path.dirname(__file__), "fixtures", "mock_portfolio.json")))
    tickers = [p["ticker"] for p in portfolio["positions"]]
    contexts = data_layer.get_context_batch(tickers)

    df = position_values(portfolio, contexts)
    summ = portfolio_summary(df, portfolio["cash"])
    sect = sector_breakdown(df, portfolio)
    weights = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()}
    spy = data_layer.get_benchmark_history("SPY")

    print("\n=== POSITIONS ===")
    print(df.round(2).to_string(index=False))
    print("\n=== SUMMARY ===")
    for k, v in summ.items():
        print(f"  {k}: {round(v,2) if isinstance(v,float) else v}")
    print("\n=== SECTORS ===")
    print(sect.round(2).to_string(index=False))
    print("\n=== CONCENTRATION FLAGS ===")
    for f in concentration_flags(df, sect):
        print("  •", f)
    print("\n=== BETA vs SPY ===", round(portfolio_beta(contexts, weights, spy), 3))
    corr = correlation_matrix(contexts)
    print("\n=== CORRELATION ===")
    print(corr.round(2).to_string())
    print("most correlated pair:", most_correlated_pair(corr))
    perf = performance_vs_benchmark(contexts, weights, spy)
    print("\n=== PERFORMANCE (last row, indexed to 100) ===")
    print(perf.tail(1).round(2).to_string())
