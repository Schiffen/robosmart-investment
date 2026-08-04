"""
agents/tools.py — the analyst agent's tool surface.
===================================================
Every tool here is a thin, JSON-returning wrapper over code that already exists
and is already tested: portfolio_metrics, factor_model, data_layer. Nothing in
this file computes finance. That is the whole point.

WHY THIS SHAPE. The product's credibility rests on "the math runs first and the
model only interprets it" (docs/PRODUCT.md principle 1). A chat agent is the easiest
possible place to lose that: a model asked "why am I down?" will happily invent
a number. Here it cannot — every figure it can say comes back from a tool call
that ran the same tested code the dashboard runs. The model chooses WHICH
question to ask; it never chooses the answer.

Two design rules follow from that:

  1. Tools return numbers plus the units and labels needed to say them out loud,
     so the model never has to reformat a raw ratio (the `revenue_growth: 0.852`
     failure, in a new place).
  2. Simulation is explicitly hypothetical and NEVER mutates session state. The
     agent can model a trade; only the user can apply one. See simulate_trade.
"""

from __future__ import annotations

import numpy as np

import data_layer
import portfolio_metrics as pm
from factor_model import decompose_move


# --------------------------------------------------------------------------
# Formatting helpers — the model speaks in these, so they carry units
# --------------------------------------------------------------------------

def _num(x, digits: int = 2):
    """A finite float rounded, or None. None means 'not available' and the
    prompt tells the agent to say so rather than guess."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, digits) if np.isfinite(v) else None


def _pct(x, digits: int = 2):
    return _num(x, digits)


# --------------------------------------------------------------------------
# Context loading (shared by several tools)
# --------------------------------------------------------------------------

def _contexts(portfolio: dict) -> dict:
    tickers = [p["ticker"] for p in portfolio.get("positions", [])]
    return data_layer.get_context_batch(tickers)


def _spy():
    try:
        return data_layer.get_benchmark_history("SPY")
    except Exception:  # noqa: BLE001 — degrade to None; tools report unavailable
        return None


def _weights(df) -> dict:
    return {r.ticker: (r.weight_pct / 100.0)
            for r in df.itertuples() if np.isfinite(r.weight_pct)}


# --------------------------------------------------------------------------
# Read-only tools
# --------------------------------------------------------------------------

def get_portfolio_summary(portfolio: dict) -> dict:
    """What the user owns, what it is worth, and how it is weighted."""
    contexts = _contexts(portfolio)
    df = pm.position_values(portfolio, contexts)
    summary = pm.portfolio_summary(df, portfolio.get("cash", 0.0))
    sectors = pm.sector_breakdown(df, portfolio)

    return {
        "currency": portfolio.get("currency", "USD"),
        "total_value": _num(summary["total_value"]),
        "cash": _num(summary["cash"]),
        "invested_equity": _num(summary["equity_value"]),
        "total_pnl": _num(summary["total_pnl_abs"]),
        "total_pnl_pct": _pct(summary["total_pnl_pct"]),
        "day_change": _num(summary["day_change_abs"]),
        "day_change_pct": _pct(summary["day_change_pct"]),
        "positions": [
            {
                "ticker": r.ticker,
                "shares": _num(r.shares, 4),
                "cost_basis_per_share": _num(r.cost_basis),
                "current_price": _num(r.current_price),
                "market_value": _num(r.market_value),
                "pnl": _num(r.pnl_abs),
                "pnl_pct": _pct(r.pnl_pct),
                "weight_pct_of_equity": _pct(r.weight_pct, 1),
                "day_change_pct": _pct(r.day_change_pct),
            }
            for r in df.itertuples()
        ],
        "sector_weights_pct": {
            row.sector: _pct(row.weight_pct, 1) for row in sectors.itertuples()
        },
        "concentration_warnings": pm.concentration_flags(df, sectors),
    }


def get_day_contributions(portfolio: dict) -> dict:
    """Which holdings actually moved the portfolio today, largest impact first.

    Contributions sum to the portfolio's day change exactly — same denominator
    as get_portfolio_summary's day_change_pct.
    """
    contexts = _contexts(portfolio)
    df = pm.position_values(portfolio, contexts)
    contrib = pm.day_move_contributions(df, portfolio.get("cash", 0.0))
    if contrib.empty:
        return {"available": False,
                "reason": "No holding could be priced, so today's move cannot "
                          "be attributed."}
    return {
        "available": True,
        "note": "contribution_pct figures sum to the portfolio's total day move.",
        "contributions": [
            {
                "ticker": r.ticker,
                "contribution_pct": _pct(r.contribution_pct),
                "contribution_amount": _num(r.contribution_abs),
                "own_move_pct": _pct(r.day_change_pct),
                "weight_pct_of_equity": _pct(r.weight_pct, 1),
            }
            for r in contrib.itertuples()
        ],
    }


def get_risk_metrics(portfolio: dict) -> dict:
    """Volatility, drawdown, beta vs the S&P 500, and effective diversification."""
    contexts = _contexts(portfolio)
    df = pm.position_values(portfolio, contexts)
    weights = _weights(df)
    spy = _spy()

    rm = pm.risk_metrics(contexts, weights, spy)
    dv = pm.diversification_score(weights)
    mm = pm.market_model(contexts, weights, spy)

    return {
        "annualized_volatility_pct": _pct(
            rm["port_vol"] * 100 if np.isfinite(rm["port_vol"]) else np.nan, 1),
        "benchmark_volatility_pct": _pct(
            rm["spy_vol"] * 100 if np.isfinite(rm["spy_vol"]) else np.nan, 1),
        "max_drawdown_pct": _pct(
            rm["max_drawdown"] * 100 if np.isfinite(rm["max_drawdown"]) else np.nan, 1),
        "one_year_return_pct": _pct(
            rm["port_total_return"] * 100
            if np.isfinite(rm["port_total_return"]) else np.nan, 1),
        "benchmark_one_year_return_pct": _pct(
            rm["spy_total_return"] * 100
            if np.isfinite(rm["spy_total_return"]) else np.nan, 1),
        "beta_vs_sp500": _num(mm["beta"]),
        "beta_r_squared": _num(mm["r_squared"]),
        "beta_observation_days": int(mm["n_obs"]) if mm.get("n_obs") else None,
        "holdings_count": dv["n_positions"],
        "effective_holdings": _num(dv["effective_n"], 1),
        "note": ("effective_holdings is 1/HHI — the number of EQUAL-sized "
                 "positions that would carry the same concentration. Lower than "
                 "holdings_count means the book is lopsided."),
    }


def get_correlations(portfolio: dict) -> dict:
    """How much the holdings move together — the diversification reality check."""
    contexts = _contexts(portfolio)
    corr = pm.correlation_matrix(contexts)
    if corr is None or corr.shape[0] < 2:
        return {"available": False,
                "reason": "Correlation needs at least two holdings with "
                          "overlapping price history."}
    pair = pm.most_correlated_pair(corr)
    return {
        "available": True,
        "average_pairwise_correlation": _num(pm.average_pairwise_correlation(corr)),
        "most_correlated_pair": (
            {"a": pair[0], "b": pair[1], "correlation": _num(pair[2])}
            if pair else None),
        "matrix": {a: {b: _num(corr.loc[a, b]) for b in corr.columns}
                   for a in corr.index},
        "note": ("1.0 means two holdings move identically; 0 means unrelated. "
                 "High correlation means holding both adds little "
                 "diversification."),
    }


def decompose_stock_move(ticker: str) -> dict:
    """Split ONE stock's move today into market, sector, and company-specific
    parts. This is the statistical decomposition, not an opinion."""
    context = data_layer.get_context(ticker)
    d = decompose_move(context)
    mq = d.get("model_quality") or {}
    betas = d.get("betas") or {}
    return {
        "ticker": (context.get("ticker") or ticker).upper(),
        "company_name": context.get("company_name"),
        "total_move_pct": _pct(d.get("total_move_pct")),
        "market_component_pct": _pct(d.get("market_component_pct")),
        "sector_component_pct": _pct(d.get("sector_component_pct")),
        "company_specific_pct": _pct(d.get("idiosyncratic_pct")),
        "interpretation": d.get("interpretation"),
        "model_r_squared": _num(mq.get("r_squared")),
        "model_is_reliable": bool(mq.get("reliable", False)),
        "observation_days": mq.get("n_obs"),
        "market_beta": _num(betas.get("market")),
        "sector_beta": _num(betas.get("sector")),
        "note": ("company_specific_pct is what the market and sector do NOT "
                 "explain. If model_is_reliable is false, treat the split as "
                 "rough and say so."),
    }


def get_stock_details(ticker: str) -> dict:
    """Price, fundamentals, technicals and recent headlines for ONE holding.

    Numbers arrive here already humanised — the agent must not be handed a raw
    ratio like 0.852 and asked to say "85.2%" itself.
    """
    c = data_layer.get_context(ticker)
    price = c.get("price") or {}
    f = c.get("fundamentals") or {}
    t = c.get("technicals") or {}
    news = c.get("news") or []

    def _ratio_pct(v):
        n = _num(v, 4)
        return None if n is None else round(n * 100, 1)

    return {
        "ticker": (c.get("ticker") or ticker).upper(),
        "company_name": c.get("company_name"),
        "sector": c.get("sector"),
        "current_price": _num(price.get("current")),
        "previous_close": _num(price.get("prev_close")),
        "day_change_pct": _pct(price.get("day_change_pct")),
        "returns_pct": {k: _pct(v) for k, v in (c.get("returns") or {}).items()},
        "fundamentals": {
            "pe_ratio": _num(f.get("pe")),
            "forward_pe_ratio": _num(f.get("forward_pe")),
            "market_cap": _num(f.get("market_cap"), 0),
            "profit_margin_pct": _ratio_pct(f.get("profit_margin")),
            "revenue_growth_pct": _ratio_pct(f.get("revenue_growth")),
            "debt_to_equity": _num(f.get("debt_to_equity")),
        },
        "technicals": {
            "rsi_14": _num(t.get("rsi_14")),
            "moving_average_50_day": _num(t.get("sma_50")),
            "moving_average_200_day": _num(t.get("sma_200")),
        },
        "recent_headlines": [
            {"title": n.get("title"), "publisher": n.get("publisher"),
             "published": n.get("published"), "link": n.get("link")}
            for n in news[:6] if isinstance(n, dict)
        ],
    }


# --------------------------------------------------------------------------
# Simulation — hypothetical only, never mutates anything
# --------------------------------------------------------------------------

def simulate_trade(portfolio: dict, trades: list) -> dict:
    """Recompute the book's metrics under a HYPOTHETICAL set of trades.

    Returns before/after for the numbers that actually change a risk picture.
    This function is pure: it builds a copy of the portfolio and never touches
    session state. Applying a change is a button the USER presses — deliberately
    not something the model can do, so a simulation can never quietly become an
    executed decision.

    `trades` is [{"ticker": str, "action": "buy"|"sell", "shares": float}].
    Selling more than held is clamped to the position and reported.
    """
    positions = {p["ticker"].upper(): dict(p)
                 for p in portfolio.get("positions", [])}
    cash = float(portfolio.get("cash", 0.0) or 0.0)

    contexts = _contexts(portfolio)
    notes, applied = [], []

    # Price any ticker being bought that isn't held yet.
    for t in trades:
        tk = str(t.get("ticker", "")).upper().strip()
        if tk and tk not in contexts:
            try:
                contexts[tk] = data_layer.get_context(tk)
            except Exception:  # noqa: BLE001
                notes.append(f"No market data for {tk} — that trade was skipped.")

    for t in trades:
        tk = str(t.get("ticker", "")).upper().strip()
        action = str(t.get("action", "")).lower().strip()
        try:
            shares = float(t.get("shares"))
        except (TypeError, ValueError):
            notes.append(f"Skipped a {tk or 'trade'} with an unreadable share count.")
            continue
        if shares <= 0 or action not in ("buy", "sell") or tk not in contexts:
            if tk not in contexts:
                continue
            notes.append(f"Skipped an invalid trade for {tk}.")
            continue

        price = (contexts[tk].get("price") or {}).get("current")
        price = _num(price)
        if price is None:
            notes.append(f"No usable price for {tk} — that trade was skipped.")
            continue

        if action == "sell":
            held = float(positions.get(tk, {}).get("shares", 0.0) or 0.0)
            if held <= 0:
                notes.append(f"You don't hold {tk}, so it can't be sold.")
                continue
            if shares > held:
                notes.append(
                    f"You hold {held:g} shares of {tk}, not {shares:g} — "
                    f"simulated selling all {held:g}.")
                shares = held
            positions[tk]["shares"] = held - shares
            cash += shares * price
            if positions[tk]["shares"] <= 1e-9:
                positions.pop(tk)
            applied.append({"ticker": tk, "action": "sell", "shares": shares,
                            "price": price, "proceeds": round(shares * price, 2)})
        else:
            cost = shares * price
            if cost > cash + 1e-9:
                affordable = cash / price if price > 0 else 0.0
                notes.append(
                    f"Buying {shares:g} {tk} costs {cost:,.2f} but only "
                    f"{cash:,.2f} cash is available — simulated buying "
                    f"{affordable:.2f} shares instead.")
                shares = affordable
                cost = shares * price
            if shares <= 0:
                continue
            if tk in positions:
                held = float(positions[tk].get("shares", 0.0) or 0.0)
                old_basis = float(positions[tk].get("cost_basis", price) or price)
                positions[tk]["shares"] = held + shares
                positions[tk]["cost_basis"] = (
                    (old_basis * held + price * shares) / (held + shares))
            else:
                positions[tk] = {
                    "ticker": tk, "shares": shares, "cost_basis": price,
                    "sector": contexts[tk].get("sector") or "Unknown",
                }
            cash -= cost
            applied.append({"ticker": tk, "action": "buy", "shares": round(shares, 4),
                            "price": price, "cost": round(cost, 2)})

    if not applied:
        return {"simulated": False,
                "reason": "None of the requested trades could be simulated.",
                "notes": notes}

    hypothetical = {"positions": list(positions.values()), "cash": cash,
                    "currency": portfolio.get("currency", "USD")}

    def _snapshot(book: dict) -> dict:
        df = pm.position_values(book, contexts)
        summary = pm.portfolio_summary(df, book.get("cash", 0.0))
        sectors = pm.sector_breakdown(df, book)
        weights = _weights(df)
        spy = _spy()
        rm = pm.risk_metrics(contexts, weights, spy)
        dv = pm.diversification_score(weights)
        mm = pm.market_model(contexts, weights, spy)
        return {
            "total_value": _num(summary["total_value"]),
            "cash": _num(summary["cash"]),
            "holdings_count": dv["n_positions"],
            "effective_holdings": _num(dv["effective_n"], 1),
            "beta_vs_sp500": _num(mm["beta"]),
            "annualized_volatility_pct": _pct(
                rm["port_vol"] * 100 if np.isfinite(rm["port_vol"]) else np.nan, 1),
            "largest_position_pct": _pct(
                max((r.weight_pct for r in df.itertuples()
                     if np.isfinite(r.weight_pct)), default=np.nan), 1),
            "sector_weights_pct": {row.sector: _pct(row.weight_pct, 1)
                                   for row in sectors.itertuples()},
            "concentration_warnings": pm.concentration_flags(df, sectors),
        }

    return {
        "simulated": True,
        "hypothetical": True,
        "disclaimer": ("This is a what-if calculation on current prices. It is "
                       "NOT a recommendation and NOT an executed trade."),
        "trades_applied": applied,
        "notes": notes,
        "before": _snapshot(portfolio),
        "after": _snapshot(hypothetical),
    }


# --------------------------------------------------------------------------
# Tool schemas
# --------------------------------------------------------------------------
# Descriptions are PRESCRIPTIVE about when to call, not just what the tool does.
# On current models that measurably raises should-call rate; a description that
# only says what a tool returns leaves the trigger condition to be guessed.

_PORTFOLIO_TOOLS = {
    "get_portfolio_summary": get_portfolio_summary,
    "get_day_contributions": get_day_contributions,
    "get_risk_metrics": get_risk_metrics,
    "get_correlations": get_correlations,
}
_TICKER_TOOLS = {
    "decompose_stock_move": decompose_stock_move,
    "get_stock_details": get_stock_details,
}

TOOLS = [
    {
        "name": "get_portfolio_summary",
        "description": (
            "Everything the user owns: each position's shares, price, value, "
            "profit or loss, and weight, plus cash, totals, sector weights and "
            "any concentration warnings. Call this FIRST for any question about "
            "'my portfolio', what they hold, how much they have, or how they are "
            "doing overall."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_day_contributions",
        "description": (
            "Which holdings moved the portfolio today and by how much, ranked by "
            "impact. Call this whenever the user asks why the portfolio is up or "
            "down today, what moved them, or which holding is responsible. "
            "Impact is size times move, so this is the ONLY correct way to answer "
            "'what moved me' — the biggest percentage mover is often not the "
            "biggest contributor."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_risk_metrics",
        "description": (
            "Volatility, worst drawdown, one-year return, beta against the S&P "
            "500, and effective (concentration-adjusted) holding count. Call this "
            "for any question about risk, how safe or aggressive the book is, how "
            "it compares to the market, or how diversified it really is."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_correlations",
        "description": (
            "How much the holdings move together, including the average pairwise "
            "correlation and the most-correlated pair. Call this when the user "
            "asks about diversification, whether their holdings are too similar, "
            "or whether they are really spread out."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "decompose_stock_move",
        "description": (
            "Split ONE stock's move today into market, sector and "
            "company-specific components using the OLS factor model. Call this "
            "when the user asks why a specific stock moved, or whether a move was "
            "the company itself versus the whole market drifting."),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string",
                           "description": "Ticker symbol, e.g. NVDA."},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_stock_details",
        "description": (
            "Price, returns, fundamentals, technicals and recent headlines for "
            "ONE stock. Call this when the user asks about a specific company's "
            "valuation, growth, momentum, or news. Headlines here are the ONLY "
            "news you may cite."),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string",
                           "description": "Ticker symbol, e.g. AAPL."},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "simulate_trade",
        "description": (
            "Recompute the portfolio's risk profile under a HYPOTHETICAL set of "
            "buys and sells, returning before/after for value, cash, beta, "
            "volatility, largest position, sector weights, effective holdings and "
            "concentration warnings. Call this whenever the user asks 'what if I "
            "sold/bought X', or how a change would affect their risk or "
            "concentration. This only calculates — it never executes anything, "
            "and you must always say the result is hypothetical."),
        "input_schema": {
            "type": "object",
            "properties": {
                "trades": {
                    "type": "array",
                    "description": "One or more hypothetical trades.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "action": {"type": "string",
                                       "enum": ["buy", "sell"]},
                            "shares": {"type": "number",
                                       "description": "Positive share count."},
                        },
                        "required": ["ticker", "action", "shares"],
                    },
                },
            },
            "required": ["trades"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]


def run_tool(name: str, tool_input: dict, portfolio: dict) -> dict:
    """Dispatch one tool call. Raises KeyError for an unknown tool name so the
    caller can return it to the model as an error result rather than crashing."""
    tool_input = tool_input or {}
    if name in _PORTFOLIO_TOOLS:
        return _PORTFOLIO_TOOLS[name](portfolio)
    if name in _TICKER_TOOLS:
        ticker = str(tool_input.get("ticker", "")).strip()
        if not ticker:
            raise ValueError("This tool needs a `ticker`.")
        return _TICKER_TOOLS[name](ticker)
    if name == "simulate_trade":
        trades = tool_input.get("trades")
        if not isinstance(trades, list) or not trades:
            raise ValueError("`trades` must be a non-empty list.")
        return simulate_trade(portfolio, trades)
    raise KeyError(name)
