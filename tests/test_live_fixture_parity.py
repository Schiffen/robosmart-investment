"""Does the fixture behave like live yfinance, or merely well enough to pass?

The offline provider is only worth having if code that works against it also
works against the real thing. These tests fetch BOTH and compare structure —
keys, types, index timezone, column dtypes — while ignoring values, which are
expected to differ (the fixture is a snapshot).

Network-gated: `pytest --live`. Everything else in the suite runs offline.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_data import fixture, live
from market_data.errors import TickerNotFoundError

PARITY_TICKERS = ["NVDA", "JNJ", "GLD"]   # a stock, a defensive, an ETF with no fundamentals


def _shape(obj):
    """Structural signature: nested key names and types, values discarded."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_shape(obj[0])] if obj else []
    if isinstance(obj, pd.DataFrame):
        return "DataFrame"
    if obj is None:
        return "None"
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, (int, np.integer)):
        return "number"
    if isinstance(obj, (float, np.floating)):
        return "number"
    return "str"


def _relaxed(shape):
    """Treat None and a present value as interchangeable.

    A missing P/E offline and a present one live is a data difference, not a
    contract difference — Contract B guarantees the KEY exists, not the value.
    """
    if isinstance(shape, dict):
        return {k: _relaxed(v) for k, v in shape.items()}
    if isinstance(shape, list):
        return [_relaxed(s) for s in shape]
    return "value" if shape in ("number", "str", "None") else shape


@pytest.mark.live
@pytest.mark.parametrize("ticker", PARITY_TICKERS)
def test_context_structure_matches_live(ticker):
    live_ctx = live.get_context(ticker)
    fix_ctx = fixture.get_context(ticker)

    assert set(live_ctx) == set(fix_ctx)
    assert _relaxed(_shape({k: v for k, v in fix_ctx.items() if k != "history"})) == \
           _relaxed(_shape({k: v for k, v in live_ctx.items() if k != "history"}))

    # Identity fields are snapshot-stable and must match exactly.
    for key in ("ticker", "company_name", "sector", "sector_etf"):
        assert fix_ctx[key] == live_ctx[key], f"{key} drifted since the snapshot"


@pytest.mark.live
@pytest.mark.parametrize("ticker", PARITY_TICKERS)
def test_history_frame_matches_live(ticker):
    live_hist = live.get_context(ticker)["history"]
    fix_hist = fixture.get_context(ticker)["history"]

    assert list(fix_hist.columns) == list(live_hist.columns)
    assert fix_hist.dtypes.to_dict() == live_hist.dtypes.to_dict()
    assert str(fix_hist.index.tz) == str(live_hist.index.tz)
    assert fix_hist.index.name == live_hist.index.name
    assert type(fix_hist.index) is type(live_hist.index)

    # Both must already be free of the unsettled-bar defect.
    assert fix_hist["Close"].isna().sum() == 0
    assert live_hist["Close"].isna().sum() == 0


@pytest.mark.live
def test_overlapping_closes_are_identical_where_dates_coincide():
    """Where both cover the same session, the recorded close must equal the live
    one. A mismatch means the fixture was written from adjusted or repaired data
    and is no longer a faithful replay."""
    live_hist = live.get_context("NVDA")["history"]["Close"]
    fix_hist = fixture.get_context("NVDA")["history"]["Close"]

    joined = pd.concat([fix_hist.rename("fix"), live_hist.rename("live")],
                       axis=1, join="inner").dropna()
    assert len(joined) > 100, "fixture and live share too few sessions to compare"
    # yfinance re-adjusts historical closes after dividends/splits, so allow a
    # small relative drift rather than demanding bit equality.
    rel = (joined["fix"] - joined["live"]).abs() / joined["live"]
    assert rel.max() < 0.01, f"recorded closes drifted {rel.max():.2%} from live"


@pytest.mark.live
def test_benchmark_history_matches_live():
    for symbol in ("SPY", "XLK"):
        live_df = live.get_benchmark_history(symbol)
        fix_df = fixture.get_benchmark_history(symbol)
        assert list(fix_df.columns) == list(live_df.columns)
        assert str(fix_df.index.tz) == str(live_df.index.tz)
        assert fix_df["Close"].isna().sum() == 0


@pytest.mark.live
def test_both_providers_reject_an_unknown_ticker_the_same_way():
    with pytest.raises(TickerNotFoundError):
        live.get_context("ZZZZQQ")
    with pytest.raises(TickerNotFoundError):
        fixture.get_context("ZZZZQQ")


@pytest.mark.live
def test_live_still_serves_unsettled_bars_that_cleaning_removes():
    """Documents the defect against the real API rather than a synthetic frame.

    Informational: it passes whether or not Yahoo is currently serving an
    unsettled bar, and reports which. What it enforces is that whatever comes
    back is clean AFTER `clean_history`.
    """
    import yfinance as yf
    raw = yf.Ticker("NVDA").history(period="1y", auto_adjust=True)
    n_bad = int(raw["Close"].isna().sum())
    cleaned = live.clean_history(raw)

    assert cleaned["Close"].isna().sum() == 0
    assert len(cleaned) == len(raw) - n_bad
    print(f"\nYahoo currently serves {n_bad} unsettled bar(s) for NVDA "
          f"(last raw date {raw.index[-1].date()}, last clean {cleaned.index[-1].date()})")
