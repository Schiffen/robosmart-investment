"""The stock / sector / market comparison, and the collapse that guards it.

The defect this file exists to prevent shipped as far as a written design
before it was caught, and it was invisible to a fixture-only reading of the
data: `market_data/live.py` resolves a ticker's sector ETF as
`SECTOR_ETF.get(sector, "SPY")`, so anything yfinance cannot classify falls
back to SPY itself. A naive three-line chart then plots SPY twice — once
labelled "the market" and once labelled "its sector" — which is not a cosmetic
duplicate but a false claim about what a fund's sector is.

It is not a rare edge either. Six of the eighteen recorded tickers hit it, and
they are every fund in the book.
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

import data_layer
import tabs.attribution as attrib
import theme

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every fund in the recorded fixture. All resolve sector -> "Unknown".
UNCLASSIFIED = ["GLD", "TLT", "VTI", "VXUS", "BND", "VNQ"]
CLASSIFIED = [("AAPL", "XLK"), ("XOM", "XLE"), ("JPM", "XLF"),
              ("KO", "XLP"), ("JNJ", "XLV")]


def _frame(ticker):
    ctx = data_layer.get_context(ticker)
    etf = attrib._sector_etf(ctx)
    hist = ctx["history"]
    f = pd.DataFrame(index=hist.index)
    f["stock"] = attrib._rebase(hist["Close"])
    spy = data_layer.get_benchmark_history("SPY")
    f["market"] = attrib._rebase(spy["Close"].reindex(hist.index).ffill())
    if etf:
        sec = data_layer.get_benchmark_history(etf)
        f["sector"] = attrib._rebase(sec["Close"].reindex(hist.index).ffill())
    return ctx, etf, f.dropna(how="all")


# --------------------------------------------------------------------------
# The collapse
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ticker", UNCLASSIFIED)
def test_unclassified_tickers_collapse_to_two_lines(ticker):
    ctx, etf, frame = _frame(ticker)
    assert ctx["sector_etf"] == "SPY", "fixture changed; this ticker was unclassified"
    assert etf is None, f"{ticker} must have no DISTINCT sector ETF"
    fig = attrib._comparison(frame, ticker, etf, theme.RANGE_HOME)
    assert len(fig.data) == 2, f"{ticker} drew {len(fig.data)} lines; expected 2"


@pytest.mark.parametrize("ticker", UNCLASSIFIED)
def test_spy_is_never_drawn_twice(ticker):
    """The actual failure mode, asserted directly rather than via trace count."""
    _, etf, frame = _frame(ticker)
    fig = attrib._comparison(frame, ticker, etf, theme.RANGE_HOME)
    spy_traces = [t for t in fig.data if "SPY" in (t.name or "")]
    assert len(spy_traces) == 1, \
        f"SPY appears {len(spy_traces)} times — one of them claims to be a sector"
    # And no two traces may carry identical y data, whatever they are called.
    ys = [tuple(np.round(np.asarray(t.y, dtype=float), 6)) for t in fig.data]
    assert len(set(ys)) == len(ys), "two lines carry identical data"


@pytest.mark.parametrize("ticker,etf", CLASSIFIED)
def test_classified_tickers_draw_all_three(ticker, etf):
    ctx, resolved, frame = _frame(ticker)
    assert resolved == etf
    fig = attrib._comparison(frame, ticker, resolved, theme.RANGE_HOME)
    assert len(fig.data) == 3
    names = " ".join(t.name for t in fig.data)
    assert etf in names and "SPY" in names and ticker in names


def test_sector_etf_guard_is_case_insensitive_and_null_safe():
    assert attrib._sector_etf({"sector_etf": "spy"}) is None
    assert attrib._sector_etf({"sector_etf": "SPY"}) is None
    assert attrib._sector_etf({"sector_etf": None}) is None
    assert attrib._sector_etf({}) is None
    assert attrib._sector_etf({"sector_etf": "xlk"}) == "XLK"


# --------------------------------------------------------------------------
# Rebasing and windowing
# --------------------------------------------------------------------------

def test_all_series_start_at_100():
    """Rebasing is what makes a $400 stock comparable to a $60 ETF."""
    _, _, frame = _frame("AAPL")
    for col in ("stock", "sector", "market"):
        first = frame[col].dropna().iloc[0]
        assert abs(first - 100.0) < 1e-6, f"{col} starts at {first}, not 100"


def test_rebase_survives_a_degenerate_series():
    assert np.isnan(attrib._rebase(pd.Series([np.nan, np.nan]))).all()
    assert np.isnan(attrib._rebase(pd.Series([0.0, 5.0]))).all()
    assert np.isnan(attrib._rebase(pd.Series([], dtype=float))).all()


def test_comparison_shares_the_dashboards_windowing():
    """Both series charts must mean the same thing by "1Y"."""
    _, etf, frame = _frame("AAPL")
    fig = attrib._comparison(frame, "AAPL", etf, theme.RANGE_HOME)
    assert fig.layout.xaxis.range is not None
    assert fig.layout.yaxis.range is not None
    assert tuple(pd.Timestamp(v) for v in fig.layout.xaxis.range) == \
        theme.range_bounds(frame.index, theme.RANGE_HOME)


def test_comparison_opts_into_pan_not_zoom():
    _, etf, frame = _frame("AAPL")
    assert attrib._comparison(frame, "AAPL", etf,
                              theme.RANGE_HOME).layout.dragmode == "pan"


@pytest.mark.parametrize("preset", list(theme.RANGE_PRESETS))
def test_every_preset_produces_a_drawable_chart(preset):
    _, etf, frame = _frame("AAPL")
    fig = attrib._comparison(frame, "AAPL", etf, preset)
    lo, hi = fig.layout.yaxis.range
    assert hi > lo and np.isfinite(lo) and np.isfinite(hi)


# --------------------------------------------------------------------------
# Against real yfinance — the check that caught this in the first place
# --------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.parametrize("ticker", ["BA", "NEE", "PLD", "BRK-B"])
def test_live_tickers_absent_from_the_fixture_resolve_a_real_sector(ticker):
    """XLI/XLU/XLRE are mapped in SECTOR_ETF but recorded in NO fixture, so
    these paths exist only against live data."""
    ctx, etf, frame = _frame(ticker)
    assert etf is not None and etf != "SPY", \
        f"{ticker} resolved to {etf!r}; expected a real sector ETF"
    fig = attrib._comparison(frame, ticker, etf, theme.RANGE_HOME)
    assert len(fig.data) == 3


@pytest.mark.live
def test_live_unclassified_ticker_still_collapses():
    """GLD is a fund live as well as recorded — the guard must not depend on
    the fixture's particular sector strings."""
    ctx, etf, frame = _frame("GLD")
    assert etf is None
    assert len(attrib._comparison(frame, "GLD", etf, theme.RANGE_HOME).data) == 2
