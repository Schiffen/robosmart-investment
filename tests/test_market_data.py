"""Provider-level tests: the NaN-bar defect, real YTD, mode resolution, and
fixture/live contract parity.

None of these need the network. The live-provider tests feed the exact SHAPES
yfinance returns (the same technique as test_real_data_shapes.py) rather than
fetching, so the regression stays pinned even when Yahoo is healthy.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_layer
import run_mode
from market_data import fixture, live
from market_data.errors import TickerNotFoundError


# --------------------------------------------------------------------------
# The defect: an unsettled trailing bar
# --------------------------------------------------------------------------

def _yf_frame_with_unsettled_last_bar(n: int = 60) -> pd.DataFrame:
    """The exact shape Yahoo served on 2026-07-29 for every symbol at once:
    the newest session has Open/High/Low/Volume but Close AND Adj Close NaN.

        NVDA 2026-07-28  O=194.95 H=198.70 L=192.74 C=NaN AdjC=NaN V=125,138,253

    Prices are a seeded random walk rather than a ramp, because a monotonically
    rising series has no down days and RSI is genuinely undefined there — that
    would test the helper, not the fix.
    """
    idx = pd.bdate_range(end="2026-07-28", periods=n, tz="America/New_York")
    rng = np.random.default_rng(7)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.012, n))
    df = pd.DataFrame({
        "Open": close * 0.998, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Adj Close": close,
        "Volume": np.full(n, 1_000_000, dtype="int64"),
    }, index=idx)
    df.loc[df.index[-1], ["Close", "Adj Close"]] = np.nan
    return df


def test_clean_history_drops_the_unsettled_bar():
    df = _yf_frame_with_unsettled_last_bar()
    assert df["Close"].isna().sum() == 1          # precondition: defect present

    cleaned = live.clean_history(df)

    assert len(cleaned) == len(df) - 1
    assert cleaned["Close"].isna().sum() == 0
    assert np.isfinite(float(cleaned["Close"].iloc[-1]))
    # The dropped bar had real Open/High/Low/Volume — we discard the whole row
    # rather than forward-filling a close we don't have.
    assert cleaned.index[-1] == df.index[-2]


def test_clean_history_is_a_noop_on_healthy_data():
    df = _yf_frame_with_unsettled_last_bar()
    healthy = df.iloc[:-1]
    assert live.clean_history(healthy).equals(healthy)


def test_clean_history_survives_degenerate_input():
    assert live.clean_history(None) is None
    empty = pd.DataFrame()
    assert live.clean_history(empty).empty
    no_close = pd.DataFrame({"Open": [1.0, 2.0]})
    assert live.clean_history(no_close).equals(no_close)


def test_unsettled_bar_would_have_blanked_every_downstream_number():
    """Why this is cleaned at the fetch boundary and not per-consumer.

    Locks in the failure mode: one NaN at the tail takes out price, RSI, SMA and
    every lookback return together, because each of them ends on `.iloc[-1]` of
    the close series.

    ATR is the lone survivor — its true-range terms reference `Close.shift()`, so
    the PRIOR close carries it. That is not a reason to leave the bar in: ATR
    would then be reporting a range for a session whose close never settled,
    while every metric beside it reads N/A. Consistency is the point.
    """
    dirty = _yf_frame_with_unsettled_last_bar()
    close_dirty = dirty["Close"]

    assert live._today_change(close_dirty) is None
    assert live._rsi(close_dirty) is None
    assert live._sma(close_dirty, 50) is None
    assert live._ret(close_dirty, 5) is None
    assert live._atr(dirty) is not None            # survives, via the prior close

    clean = live.clean_history(dirty)
    close_clean = clean["Close"]
    assert live._today_change(close_clean) is not None
    assert live._rsi(close_clean) is not None
    assert live._sma(close_clean, 50) is not None
    assert live._ret(close_clean, 5) is not None
    assert live._atr(clean) is not None


# --------------------------------------------------------------------------
# YTD
# --------------------------------------------------------------------------

def test_ytd_baselines_on_prior_year_final_close():
    idx = pd.bdate_range("2025-11-03", "2026-03-31")
    close = pd.Series(100.0 + np.arange(len(idx), dtype=float), index=idx)

    base = float(close[close.index.year == 2025].iloc[-1])
    expected = round((float(close.iloc[-1]) / base - 1.0) * 100, 2)

    assert live._ytd(close) == expected


def test_ytd_differs_from_the_old_fixed_138_day_lookback():
    """Regression on the actual bug: `_ret(close, 138)` was labelled 'ytd'."""
    idx = pd.bdate_range("2025-01-02", "2026-07-28")
    close = pd.Series(100.0 * np.cumprod(1.0 + np.linspace(0.0005, 0.002, len(idx))),
                      index=idx)
    assert live._ytd(close) != live._ret(close, 138)


def test_ytd_falls_back_when_history_starts_inside_the_year():
    idx = pd.bdate_range("2026-01-02", "2026-07-28")
    close = pd.Series(100.0 + np.arange(len(idx), dtype=float), index=idx)
    expected = round((float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100, 2)
    assert live._ytd(close) == expected


def test_ytd_is_none_when_there_is_nothing_to_measure():
    single = pd.Series([100.0], index=pd.DatetimeIndex(["2026-01-02"]))
    assert live._ytd(single) is None
    assert live._ytd(pd.Series([1.0, 2.0], index=[0, 1])) is None   # not datetime


def test_ytd_handles_tz_aware_index():
    idx = pd.bdate_range("2025-11-03", "2026-03-31", tz="America/New_York")
    close = pd.Series(100.0 + np.arange(len(idx), dtype=float), index=idx)
    assert live._ytd(close) is not None


# --------------------------------------------------------------------------
# Mode resolution
# --------------------------------------------------------------------------

@pytest.mark.parametrize("env,expected", [
    ({}, False),
    ({"USE_MOCK": "1"}, True),
    ({"USE_MOCK": "0"}, False),
    ({"USE_MOCK_DATA": "1"}, True),
    ({"USE_MOCK": "1", "USE_MOCK_DATA": "0"}, False),   # specific beats USE_MOCK
    ({"USE_MOCK": "0", "USE_MOCK_DATA": "1"}, True),
    ({"USE_MOCK": "true"}, True),
    ({"USE_MOCK": "garbage"}, False),                   # unrecognised == unset
])
def test_data_mode_precedence(monkeypatch, env, expected):
    for key in ("USE_MOCK", "USE_MOCK_DATA"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert run_mode.use_fixture_data() is expected


@pytest.mark.parametrize("env,expected", [
    ({"ANTHROPIC_API_KEY": "sk-test"}, False),
    ({}, True),                                          # no key -> no choice
    ({"ANTHROPIC_API_KEY": "sk-test", "USE_MOCK": "1"}, True),
    ({"ANTHROPIC_API_KEY": "sk-test", "USE_MOCK": "1", "USE_MOCK_LLM": "0"}, False),
    ({"USE_MOCK_LLM": "0"}, True),                       # still no key
])
def test_llm_mode_precedence(monkeypatch, env, expected):
    for key in ("USE_MOCK", "USE_MOCK_LLM", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert run_mode.use_recorded_llm() is expected

    from agents import llm
    assert llm.use_mock() is expected      # the agents agree with run_mode


def test_data_layer_dispatches_per_call(monkeypatch):
    """Mode is read at call time, not import time — app.py's load_dotenv() and
    the tests' monkeypatch both land after this module is first imported."""
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.setenv("USE_MOCK_DATA", "1")
    assert data_layer.active_provider_name() == "fixture"
    monkeypatch.setenv("USE_MOCK_DATA", "0")
    assert data_layer.active_provider_name() == "live"


# --------------------------------------------------------------------------
# Fixture provider
# --------------------------------------------------------------------------

DEMO_TICKERS = ["NVDA", "MSFT", "AAPL", "JNJ", "JPM", "XOM", "GLD"]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("USE_MOCK_DATA", "1")
    fixture.reset_cache()
    yield
    fixture.reset_cache()


def test_fixture_exists_and_is_dated():
    assert fixture.snapshot_utc(), "no fixture recorded — run market_data.refresh"
    assert fixture.snapshot_date() and len(fixture.snapshot_date()) == 10
    assert set(DEMO_TICKERS) <= set(fixture.available_tickers())


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_fixture_context_satisfies_contract_b(ticker):
    ctx = data_layer.get_context(ticker)

    assert set(ctx) >= {"ticker", "company_name", "sector", "sector_etf", "price",
                        "returns", "fundamentals", "technicals", "news",
                        "benchmarks", "history"}
    assert set(ctx["price"]) == {"current", "prev_close", "day_change_pct"}
    assert set(ctx["returns"]) == {"1d", "5d", "1m", "ytd"}
    assert set(ctx["fundamentals"]) == {"pe", "forward_pe", "market_cap",
                                        "profit_margin", "revenue_growth",
                                        "debt_to_equity"}
    assert set(ctx["technicals"]) == {"rsi_14", "sma_50", "sma_200", "atr"}

    assert ctx["ticker"] == ticker
    assert np.isfinite(ctx["price"]["current"])
    assert ctx["price"]["current"] > 0


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_fixture_history_matches_live_shape(ticker):
    """The fixture must be indistinguishable from yfinance output, not merely
    usable — otherwise offline runs stop exercising the tz-normalisation and
    dtype paths that only real data triggers."""
    hist = data_layer.get_context(ticker)["history"]

    assert isinstance(hist.index, pd.DatetimeIndex)
    assert hist.index.tz is not None, "live yfinance returns tz-aware; fixture must too"
    assert str(hist.index.tz) == "America/New_York"
    assert hist.index.is_monotonic_increasing
    assert not hist.index.has_duplicates
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(hist.columns)
    assert hist["Close"].isna().sum() == 0
    assert len(hist) >= 200
    assert hist["Volume"].dtype == np.int64          # not silently widened to float


def test_fixture_rejects_unknown_ticker_like_live_does():
    with pytest.raises(TickerNotFoundError):
        data_layer.get_context("ZZZZQQ")


def test_fixture_batch_omits_unknowns_and_keeps_the_rest():
    got = data_layer.get_context_batch(["NVDA", "ZZZZQQ", "JNJ"])
    assert set(got) == {"NVDA", "JNJ"}


def test_fixture_benchmarks_cover_what_consumers_ask_for():
    spy = data_layer.get_benchmark_history("SPY")
    assert len(spy) >= 200 and spy["Close"].isna().sum() == 0

    # factor_model asks for each holding's sector ETF by name.
    for ticker in DEMO_TICKERS:
        etf = data_layer.get_context(ticker)["sector_etf"]
        if etf != "SPY":
            assert len(data_layer.get_benchmark_history(etf)) >= 200


def test_fixture_is_deterministic_and_isolated():
    a = data_layer.get_context("NVDA")
    a["price"]["current"] = -999
    a["history"].iloc[0, 0] = -999
    b = data_layer.get_context("NVDA")
    assert b["price"]["current"] > 0, "mutation leaked into the cached fixture"
    assert b["history"].iloc[0, 0] > 0


@pytest.mark.parametrize("ticker", DEMO_TICKERS)
def test_news_fields_are_always_text(ticker):
    """Regression: `published` arrived as a Unix epoch int from yf.Ticker().news
    (yf.Search gives an ISO string), and `agents.explainer._news_block` called
    .strip() on it — crashing the live "Explain this move" button for any ticker
    whose headlines came from that endpoint. These strings go into prompts, so
    there must be exactly one type to reason about."""
    for item in data_layer.get_context(ticker)["news"]:
        for field in ("title", "publisher", "published", "link"):
            value = item.get(field)
            assert value is None or isinstance(value, str), \
                f"{ticker} news.{field} is {type(value).__name__}: {value!r}"


def test_published_normalises_epoch_ints_to_iso():
    from market_data.live import _published
    assert _published({}, {"providerPublishTime": 1785000000}).startswith("2026-")
    assert _published({"pubDate": "2026-07-28T10:00:00Z"}, {}) == "2026-07-28T10:00:00Z"
    assert _published({}, {}) is None
    assert isinstance(_published({}, {"providerPublishTime": 1.7e18}), str)  # out of range


def test_news_block_survives_a_non_string_published_field():
    """Defence in depth: contexts built outside the data layer (older fixtures,
    hand-made test data) can still carry an int here."""
    from agents.explainer import _news_block
    block = _news_block([{"title": "A headline", "publisher": "Reuters",
                          "published": 1785000000, "link": "https://example.test/1"}])
    assert "A headline" in block


def test_fixture_news_is_real_not_placeholder():
    """The debate and explainer prompts instruct the model to cite headlines.
    Offline, those headlines must be real ones — a placeholder feed would demo
    exactly the fabrication the prompts exist to prevent."""
    total_titled = 0
    for ticker in DEMO_TICKERS:
        for item in data_layer.get_context(ticker)["news"]:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            total_titled += 1
            assert "example.com" not in (item.get("link") or "")
            assert len(title) > 15
    assert total_titled >= 20, f"only {total_titled} usable headlines recorded"
