"""Cross-checks that the numbers the app shows are internally consistent.

These are not "does it run" tests. Each one asserts an identity that must hold
between two figures the UI displays side by side, computed down different code
paths. If one drifts, the dashboard starts contradicting itself — which is worse
than an error, because it looks fine.

Runs on the recorded fixture (suite default), so the arithmetic is exact and
reproducible rather than dependent on what the market did this morning.
"""

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_layer
import portfolio_metrics as pm
from factor_model import decompose_move

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="function")
def book():
    with open(os.path.join(BASE, "fixtures", "mock_portfolio.json")) as fh:
        portfolio = json.load(fh)
    contexts = data_layer.get_context_batch([p["ticker"] for p in portfolio["positions"]])
    spy = data_layer.get_benchmark_history("SPY")
    df = pm.position_values(portfolio, contexts)
    weights = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()}
    return portfolio, contexts, spy, df, weights


# --------------------------------------------------------------------------
# Portfolio accounting
# --------------------------------------------------------------------------

def test_total_value_is_exactly_equity_plus_cash(book):
    portfolio, _, _, df, _ = book
    s = pm.portfolio_summary(df, portfolio["cash"])
    assert s["total_value"] == pytest.approx(s["equity_value"] + s["cash"], abs=1e-9)


def test_position_weights_sum_to_one(book):
    _, _, _, df, weights = book
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert df["weight_pct"].sum() == pytest.approx(100.0, abs=1e-9)


def test_sector_weights_reconcile_with_position_weights(book):
    portfolio, _, _, df, _ = book
    sectors = pm.sector_breakdown(df, portfolio)
    assert sectors["weight_pct"].sum() == pytest.approx(100.0, abs=1e-9)
    assert sectors["market_value"].sum() == pytest.approx(df["market_value"].sum(), abs=1e-6)


def test_pnl_reconciles_with_cost_basis(book):
    portfolio, _, _, df, _ = book
    s = pm.portfolio_summary(df, portfolio["cash"])
    cost = float((df["shares"] * df["cost_basis"]).sum())
    assert s["total_pnl_abs"] == pytest.approx(s["equity_value"] - cost, abs=1e-6)
    assert s["total_pnl_pct"] == pytest.approx(s["total_pnl_abs"] / cost * 100.0, abs=1e-9)


def test_effective_holdings_never_exceeds_position_count(book):
    _, _, _, _, weights = book
    d = pm.diversification_score(weights)
    assert 1.0 <= d["effective_n"] <= d["n_positions"]


# --------------------------------------------------------------------------
# Benchmark-relative figures — all three come off ONE return series, so they
# must agree. This is the guarantee docs/INTEGRATION_CONTRACT.md §3 is written for.
# --------------------------------------------------------------------------

def test_performance_chart_and_risk_metrics_agree_exactly(book):
    _, contexts, spy, _, weights = book
    perf = pm.performance_vs_benchmark(contexts, weights, spy)
    risk = pm.risk_metrics(contexts, weights, spy)

    assert perf.iloc[0]["Portfolio"] == 100.0
    assert perf.iloc[0]["SPY"] == 100.0

    # The chart's final index IS the total return, restated. If these diverge,
    # the "1y return" tile is contradicting the chart directly above it.
    assert perf.iloc[-1]["Portfolio"] == pytest.approx(
        100.0 * (1.0 + risk["port_total_return"]), rel=1e-12)
    assert perf.iloc[-1]["SPY"] == pytest.approx(
        100.0 * (1.0 + risk["spy_total_return"]), rel=1e-12)


def test_beta_satisfies_the_correlation_volatility_identity(book):
    """beta == rho * (sigma_portfolio / sigma_market), derived independently.

    market_model computes beta from cov/var and R2 from corrcoef; risk_metrics
    computes the two volatilities. Different expressions, same underlying data —
    so this identity is a genuine cross-check, not a restatement.
    """
    _, contexts, spy, _, weights = book
    mm = pm.market_model(contexts, weights, spy)
    risk = pm.risk_metrics(contexts, weights, spy)

    rho = np.sqrt(mm["r_squared"]) * np.sign(mm["beta"])
    implied = rho * (risk["port_vol"] / risk["spy_vol"])
    assert mm["beta"] == pytest.approx(implied, rel=1e-9)


def test_portfolio_beta_is_plausible_for_this_book(book):
    """The demo book is 48% tech but also holds gold, healthcare and energy, so
    a sub-1 beta is the CORRECT answer — an earlier version of this test
    asserted 'tech-heavy book -> beta > 1', which the composition doesn't
    support."""
    _, contexts, spy, _, weights = book
    mm = pm.market_model(contexts, weights, spy)
    assert 0.3 < mm["beta"] < 1.2
    assert 0.0 <= mm["r_squared"] <= 1.0
    assert mm["n_days"] > 200


def test_max_drawdown_is_negative_and_bounded(book):
    _, contexts, spy, _, weights = book
    risk = pm.risk_metrics(contexts, weights, spy)
    assert -1.0 < risk["max_drawdown"] <= 0.0
    assert risk["port_vol"] > 0 and risk["spy_vol"] > 0


# --------------------------------------------------------------------------
# Factor model — the waterfall must actually add up
# --------------------------------------------------------------------------

DEMO_TICKERS = ["NVDA", "MSFT", "AAPL", "JNJ", "JPM", "XOM", "GLD"]


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_waterfall_components_sum_to_the_total_move(ticker):
    """market + sector + company-specific == today's move.

    The chart draws these as a waterfall landing on 'Total move'. If they don't
    sum, the bars visibly fail to reach the total.
    """
    ctx = data_layer.get_context(ticker)
    d = decompose_move(ctx, benchmark_fetcher=data_layer.get_benchmark_history)

    parts = (d["market_component_pct"] + d["sector_component_pct"]
             + d["idiosyncratic_pct"])
    # Each component is rounded to 3dp independently, so allow that much slack.
    assert parts == pytest.approx(d["total_move_pct"], abs=0.0025)


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_decomposition_total_matches_the_context_it_was_given(ticker):
    ctx = data_layer.get_context(ticker)
    d = decompose_move(ctx, benchmark_fetcher=data_layer.get_benchmark_history)
    assert d["total_move_pct"] == pytest.approx(ctx["price"]["day_change_pct"], abs=1e-9)


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_model_quality_flag_matches_its_own_criteria(ticker):
    """`reliable` drives a user-facing warning banner; it must mean what the
    docstring says it means (R2 >= 0.2 and n >= 100)."""
    ctx = data_layer.get_context(ticker)
    mq = decompose_move(ctx, benchmark_fetcher=data_layer.get_benchmark_history)["model_quality"]
    assert mq["reliable"] is bool(mq["r_squared"] >= 0.2 and mq["n_obs"] >= 100)
    assert 0.0 <= mq["r_squared"] <= 1.0
    assert mq["n_obs"] > 200


def test_sector_etf_is_residualised_not_double_counted():
    """XOM sits in Energy, so XLE should carry most of its move. The point of
    residualising the ETF against SPY is that the market leg doesn't also claim
    that same move — if it did, the two components would be double-counting."""
    ctx = data_layer.get_context("XOM")
    d = decompose_move(ctx, benchmark_fetcher=data_layer.get_benchmark_history)
    assert abs(d["sector_component_pct"]) > abs(d["market_component_pct"])
    assert d["model_quality"]["r_squared"] > 0.5


# --------------------------------------------------------------------------
# Concentration
# --------------------------------------------------------------------------

def test_demo_book_trips_exactly_the_sector_concentration_flag(book):
    """Technology is 47.8% of equity, above the 40% guideline. No single
    position clears 25% and the top 3 come to 58%, under the 60% guideline — so
    this book must produce exactly one warning, about the sector."""
    portfolio, _, _, df, _ = book
    sectors = pm.sector_breakdown(df, portfolio)
    flags = pm.concentration_flags(df, sectors)

    assert len(flags) == 1
    assert "Technology" in flags[0]
    assert df["weight_pct"].max() < pm.SINGLE_POSITION_LIMIT
    assert df["weight_pct"].nlargest(3).sum() < pm.TOP3_LIMIT
    assert sectors["weight_pct"].max() > pm.SECTOR_LIMIT
