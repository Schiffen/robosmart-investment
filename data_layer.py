"""data_layer.py — the market-data facade (Contract B).

Everything in the app imports market data from here — `app.py`, `tabs/dashboard.py`,
`factor_model.py`, the tests. This module owns exactly one decision: WHICH
provider answers.

    market_data/live.py      yfinance (production)
    market_data/fixture.py   recorded snapshot (offline / USE_MOCK)

The choice is made PER CALL, not at import. `app.py` runs `load_dotenv()` after
this module may already be imported, and the tests flip modes with
`monkeypatch.setenv`; resolving once at import would ignore both and give you a
mode that silently depends on import order.

Contract B (frozen — see docs/INTEGRATION_CONTRACT.md §1). Keys are always present,
None when a value is genuinely missing, never omitted:

    ticker, company_name, sector, sector_etf,
    price.{current, prev_close, day_change_pct},
    returns.{1d, 5d, 1m, ytd},
    fundamentals.{pe, forward_pe, market_cap, profit_margin,
                  revenue_growth, debt_to_equity},
    technicals.{rsi_14, sma_50, sma_200, atr},
    news[{title, publisher, published, link}],
    benchmarks.{SPY, <sector_etf>, VIX},
    history   (1y daily OHLCV DataFrame, tz-aware index)
"""

from __future__ import annotations

import pandas as pd

import run_mode
from market_data.errors import TickerNotFoundError

__all__ = [
    "TickerNotFoundError", "get_context", "get_context_batch",
    "get_benchmark_history", "active_provider_name",
]


def _provider():
    """The module answering right now. Imported lazily so that a broken or
    absent fixture can never stop the live path from loading, and vice versa."""
    if run_mode.use_fixture_data():
        from market_data import fixture
        return fixture
    from market_data import live
    return live


def active_provider_name() -> str:
    return "fixture" if run_mode.use_fixture_data() else "live"


def get_context(ticker: str) -> dict:
    """Contract-B context for one ticker. Raises TickerNotFoundError only when
    the ticker has no price history at all — partial data is returned as-is."""
    return _provider().get_context(ticker)


def get_context_batch(tickers: list) -> dict:
    """{TICKER: context} for the ones that resolved.

    Tickers with no history are OMITTED rather than raising, so one bad symbol
    can't blank a whole portfolio. The caller is expected to diff its request
    against the returned keys and tell the user which ones failed — see
    `tabs/dashboard.py`, which does exactly that instead of leaving unexplained
    N/A rows in the holdings table.
    """
    return _provider().get_context_batch(tickers)


def get_benchmark_history(symbol: str = "SPY") -> pd.DataFrame:
    """1y OHLCV for a benchmark or sector ETF.

    THE single source for benchmark data (docs/INTEGRATION_CONTRACT.md §3): the
    dashboard's beta/risk/performance and the factor model both come through
    here, so their numbers are guaranteed to reconcile against the same series.
    """
    return _provider().get_benchmark_history(symbol)
