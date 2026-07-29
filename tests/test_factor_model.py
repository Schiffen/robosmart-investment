"""Unit tests for factor_model.decompose_move — assert the finance, with an
injected benchmark fetcher so no network is needed."""

import numpy as np
import pandas as pd
import pytest

import factor_model as fm


def _hist(returns, start=100.0):
    idx = pd.bdate_range(end="2026-07-17", periods=len(returns) + 1)
    close = start * np.cumprod(np.concatenate([[1.0], 1.0 + returns]))
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.full(len(close), 1_000_000)}, index=idx)


def _day_change(hist):
    c = hist["Close"]
    return float((c.iloc[-1] / c.iloc[-2] - 1) * 100)


def test_market_only_recovers_beta_and_sums():
    rng = np.random.default_rng(0)
    spy_r = rng.normal(0.0003, 0.01, 250)
    spy, stock = _hist(spy_r), _hist(2.0 * spy_r)      # beta_mkt should be ~2
    ctx = {"ticker": "X", "sector_etf": "SPY",
           "price": {"day_change_pct": _day_change(stock)}, "history": stock}
    d = fm.decompose_move(ctx, benchmark_fetcher=lambda s: spy)
    assert d["betas"]["market"] == pytest.approx(2.0, abs=0.05)
    assert d["betas"]["sector"] == 0.0
    total = (d["market_component_pct"] + d["sector_component_pct"]
             + d["idiosyncratic_pct"])
    assert total == pytest.approx(d["total_move_pct"], abs=1e-6)


def test_components_sum_to_total_with_sector():
    rng = np.random.default_rng(1)
    spy_r = rng.normal(0.0003, 0.01, 250)
    sec_r = 0.6 * spy_r + rng.normal(0, 0.006, 250)
    stock_r = 1.2 * spy_r + 0.8 * (sec_r - 0.6 * spy_r) + rng.normal(0, 0.008, 250)
    spy, sec, stock = _hist(spy_r), _hist(sec_r), _hist(stock_r)
    fetch = lambda s: {"SPY": spy, "XLK": sec}[s]  # noqa: E731
    ctx = {"ticker": "X", "sector_etf": "XLK",
           "price": {"day_change_pct": _day_change(stock)}, "history": stock}
    d = fm.decompose_move(ctx, benchmark_fetcher=fetch)
    total = (d["market_component_pct"] + d["sector_component_pct"]
             + d["idiosyncratic_pct"])
    assert total == pytest.approx(d["total_move_pct"], abs=1e-6)
    assert d["model_quality"]["n_obs"] >= 100


def test_short_history_flagged_unreliable():
    rng = np.random.default_rng(2)
    spy = _hist(rng.normal(0, 0.01, 250))
    stock = _hist(rng.normal(0, 0.02, 40))          # only ~40 obs
    ctx = {"ticker": "X", "sector_etf": "SPY",
           "price": {"day_change_pct": 1.0}, "history": stock}
    d = fm.decompose_move(ctx, benchmark_fetcher=lambda s: spy)
    assert d["model_quality"]["reliable"] is False
