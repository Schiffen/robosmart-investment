"""
factor_model.py — Person 4: decompose a stock's daily move into market,
sector, and idiosyncratic components. PURE Python, no Streamlit, unit-testable.
=============================================================================
r_stock = alpha + beta_mkt * r_SPY + beta_sector * r_SECTOR_RESID + epsilon

Betas are OLS on DAILY RETURNS over a lookback window (default 252 days). The
sector ETF's returns are RESIDUALIZED against SPY first, so the market and
sector components don't double-count the part of the sector that is just "the
market". Today's actual factor returns are then applied to those betas.

This is real finance, not a wrapper around an LLM — the LLM (agents/explainer)
only interprets the leftover idiosyncratic residual.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from data_layer import get_benchmark_history
except Exception:  # pragma: no cover - allows import if data_layer absent
    get_benchmark_history = None


def _returns(history: pd.DataFrame) -> pd.Series | None:
    """Daily simple returns with tz-naive date normalization (so SPY/ETF/stock
    align on an inner join even when yfinance returns tz-aware indices)."""
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return None
    if "Close" not in history.columns:
        return None
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if isinstance(close.index, pd.DatetimeIndex):
        idx = close.index
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        close.index = idx.normalize()
        close = close[~close.index.duplicated(keep="last")]
    if len(close) < 3:
        return None
    return close.pct_change().dropna()


def _ols(y: np.ndarray, X: np.ndarray):
    """OLS with intercept. Returns (coeffs incl. intercept as [0], r_squared)."""
    A = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return coef, r2


def decompose_move(context: dict, lookback_days: int = 252,
                   benchmark_fetcher=None) -> dict:
    """Decompose context['price']['day_change_pct'] into market / sector /
    idiosyncratic. `benchmark_fetcher(symbol)->OHLCV` defaults to
    data_layer.get_benchmark_history (inject in tests to avoid the network)."""
    fetch = benchmark_fetcher or get_benchmark_history
    total_move = float(context.get("price", {}).get("day_change_pct") or 0.0)
    sector_etf = context.get("sector_etf") or "SPY"

    stock_ret = _returns(context.get("history"))
    spy_ret = _returns(fetch("SPY")) if fetch else None

    def _fail(note):
        return {
            "total_move_pct": total_move, "market_component_pct": np.nan,
            "sector_component_pct": np.nan, "idiosyncratic_pct": np.nan,
            "betas": {"market": np.nan, "sector": np.nan, "alpha": np.nan},
            "model_quality": {"r_squared": np.nan, "n_obs": 0,
                              "lookback_days": lookback_days, "reliable": False},
            "interpretation": note,
        }

    if stock_ret is None or spy_ret is None:
        return _fail("Not enough price history to decompose this move.")

    # Optional sector ETF (skip if it maps to SPY or can't be fetched).
    sector_ret = None
    if sector_etf and sector_etf != "SPY" and fetch:
        try:
            sector_ret = _returns(fetch(sector_etf))
        except Exception:  # noqa: BLE001
            sector_ret = None

    # Align on common dates, take the most recent `lookback_days`.
    cols = {"stock": stock_ret, "spy": spy_ret}
    if sector_ret is not None:
        cols["sector"] = sector_ret
    df = pd.concat(cols, axis=1, join="inner").dropna()
    if len(df) > lookback_days:
        df = df.iloc[-lookback_days:]
    n = len(df)
    if n < 60:
        out = _fail("Too few overlapping observations for a reliable decomposition.")
        out["model_quality"]["n_obs"] = n
        return out

    y = df["stock"].to_numpy()
    spy = df["spy"].to_numpy()
    spy_today = float(spy[-1])

    if "sector" in df.columns:
        sec = df["sector"].to_numpy()
        # Residualize sector vs SPY: sector = a + g*spy + resid  -> use resid.
        (a_s, g_s), _ = _ols(sec, spy.reshape(-1, 1))
        sec_resid = sec - (a_s + g_s * spy)
        (coef, r2) = _ols(y, np.column_stack([spy, sec_resid]))
        alpha, beta_mkt, beta_sector = coef
        sec_today = float(sec[-1])
        sec_resid_today = sec_today - (a_s + g_s * spy_today)
        sector_component = beta_sector * sec_resid_today * 100.0
    else:
        (coef, r2) = _ols(y, spy.reshape(-1, 1))
        alpha, beta_mkt = coef
        beta_sector = 0.0
        sector_component = 0.0

    market_component = beta_mkt * spy_today * 100.0
    idiosyncratic = total_move - market_component - sector_component

    explained = 0.0
    if abs(total_move) > 1e-9:
        explained = max(0.0, min(1.0, 1.0 - abs(idiosyncratic) / abs(total_move)))
    reliable = (r2 >= 0.2) and (n >= 100)

    return {
        "total_move_pct": round(total_move, 3),
        "market_component_pct": round(market_component, 3),
        "sector_component_pct": round(sector_component, 3),
        "idiosyncratic_pct": round(idiosyncratic, 3),
        "betas": {"market": round(float(beta_mkt), 3),
                  "sector": round(float(beta_sector), 3),
                  "alpha": round(float(alpha), 5)},
        "model_quality": {"r_squared": round(float(r2), 3), "n_obs": int(n),
                          "lookback_days": lookback_days, "reliable": bool(reliable)},
        "interpretation": (
            f"{explained * 100:.0f}% of today's move is explained by market and "
            f"sector; the rest is company-specific."),
    }


if __name__ == "__main__":
    import data_layer
    ctx = data_layer.get_context("NVDA")
    from pprint import pprint
    pprint(decompose_move(ctx))
