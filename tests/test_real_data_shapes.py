"""
Real-data shape tests — this sandbox can't reach Yahoo, so instead of a live
fetch we feed the metrics the exact SHAPES yfinance returns in the awkward
cases and prove the pipeline survives them. Complements the reference adapter
in data_layer_reference.py (which runs against the live API on a networked
machine).
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio_metrics as pm
import tabs.dashboard as dash


def _yf_history(returns, tz="America/New_York", start_price=100.0, extra_cols=True):
    """Build a yfinance-like OHLCV frame: tz-AWARE index + Dividends/Splits cols."""
    idx = pd.bdate_range(end="2026-07-17", periods=len(returns) + 1, tz=tz)
    close = start_price * np.cumprod(np.concatenate([[1.0], 1.0 + returns]))
    df = pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": np.full(len(close), 1_000_000),
    }, index=idx)
    if extra_cols:
        df["Dividends"] = 0.0
        df["Stock Splits"] = 0.0
    return df


def _ctx(ticker, sector, current, day_change_pct, history):
    return {"ticker": ticker, "sector": sector,
            "price": {"current": current, "day_change_pct": day_change_pct},
            "history": history}


def test_tz_aware_equity_and_utc_crypto_align():
    # Equity carries NY tz, crypto carries UTC tz. After tz-naive date
    # normalization they must align on the shared calendar dates, not vanish.
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, 200)
    equity = _yf_history(r, tz="America/New_York")
    crypto = _yf_history(r * 0.5 + rng.normal(0, 0.01, 200), tz="UTC")
    ctx = {"AAPL": _ctx("AAPL", "Technology", 1, 0, equity),
           "BTC-USD": _ctx("BTC-USD", "Unknown", 1, 0, crypto)}
    corr = pm.correlation_matrix(ctx)
    assert corr.shape == (2, 2)
    assert np.isfinite(corr.loc["AAPL", "BTC-USD"])   # aligned, not NaN/empty


def test_tz_aware_beta_computes():
    rng = np.random.default_rng(1)
    spy_r = rng.normal(0.0003, 0.01, 250)
    spy = _yf_history(spy_r, tz="America/New_York")
    stock = _yf_history(1.5 * spy_r, tz="America/New_York")
    ctx = {"XYZ": _ctx("XYZ", "Technology", 1, 0, stock)}
    beta = pm.portfolio_beta(ctx, {"XYZ": 1.0}, spy_history=spy)
    assert beta == pytest.approx(1.5, abs=0.05)


def test_recent_ipo_short_history_degrades_not_crash():
    # 25 trading days of history: correlation may compute, but beta must guard
    # (needs >=30 overlap) and return NaN rather than a garbage slope.
    rng = np.random.default_rng(2)
    spy = _yf_history(rng.normal(0, 0.01, 250))
    ipo = _yf_history(rng.normal(0, 0.02, 25))
    ctx = {"IPO": _ctx("IPO", "Technology", 1, 0, ipo)}
    beta = pm.portfolio_beta(ctx, {"IPO": 1.0}, spy_history=spy)
    assert np.isnan(beta)   # too little overlap -> honest N/A


def test_extra_columns_dont_break_returns():
    rng = np.random.default_rng(3)
    hist = _yf_history(rng.normal(0, 0.01, 60), extra_cols=True)
    assert "Dividends" in hist.columns and "Stock Splits" in hist.columns
    r = pm._daily_returns(hist)
    assert r is not None and len(r) > 50


def test_crypto_without_sector_renders():
    # BTC-USD style: no sector. Must group as its own slice and not crash charts.
    port = {"positions": [
        {"ticker": "AAPL", "shares": 10, "cost_basis": 150.0, "sector": "Technology"},
        {"ticker": "BTC-USD", "shares": 0.5, "cost_basis": 40000.0, "sector": "Unknown"},
    ], "cash": 0.0, "currency": "USD"}
    ctx = {"AAPL": _ctx("AAPL", "Technology", 210.0, 1.0, _yf_history(np.zeros(60))),
           "BTC-USD": _ctx("BTC-USD", "Unknown", 65000.0, 3.0, _yf_history(np.zeros(60), tz="UTC"))}
    df = pm.position_values(port, ctx)
    sect = pm.sector_breakdown(df, port)
    assert "Unknown" in set(sect["sector"])
    # chart builder must not raise on the mixed book
    fig = dash._donut(sect, "$")
    assert len(fig.data) == 1


def test_market_closed_day_change_zero_not_nan():
    # Market closed: current == prev_close -> day change 0, a real number.
    port = {"positions": [{"ticker": "AAPL", "shares": 10, "cost_basis": 150.0,
                           "sector": "Technology"}], "cash": 0.0, "currency": "USD"}
    ctx = {"AAPL": _ctx("AAPL", "Technology", current=200.0, day_change_pct=0.0,
                        history=_yf_history(np.zeros(60)))}
    df = pm.position_values(port, ctx)
    s = pm.portfolio_summary(df, 0.0)
    assert s["day_change_abs"] == pytest.approx(0.0)
    assert not np.isnan(s["total_value"])
