"""market_data/live.py — the yfinance-backed provider (Contract B).

Design rules honored:
- Every context key is ALWAYS present; missing values are None (never omitted).
- NEVER raise on partial data (missing fundamentals/news). Only raise
  TickerNotFoundError if the ticker itself has no price history.
- RSI(14)/ATR(14)/SMA computed with pandas (no TA-Lib).
- @st.cache_data(ttl=900) on the network fetches for demo reliability.
- Robust to real-data quirks: tz-aware indices, MultiIndex columns from
  yf.download, absent .info fields, crypto with no sector, thin/empty news,
  and unsettled trailing bars (see `_clean`).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from market_data.errors import TickerNotFoundError

try:
    import streamlit as st
    _cache = st.cache_data(ttl=900)
except Exception:  # allow import without a Streamlit runtime (e.g. terminal tests)
    def _cache(fn):
        return fn


SECTOR_ETF = {
    "Technology": "XLK", "Healthcare": "XLV", "Financial Services": "XLF",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Utilities": "XLU", "Real Estate": "XLRE",
    "Basic Materials": "XLB", "Communication Services": "XLC",
}


# --------------------------------------------------------------------------
# Raw fetches (cached)
# --------------------------------------------------------------------------

def clean_history(df: pd.DataFrame) -> pd.DataFrame:
    """Drop bars that have no settled Close.

    Yahoo publishes the most recent session with Open/High/Low/Volume filled in
    but Close AND Adj Close still NaN until the close settles. Observed on every
    symbol simultaneously, benchmarks included:

        NVDA 2026-07-28  O=194.95 H=198.70 L=192.74 C=NaN AdjC=NaN V=125,138,253

    This is cleaned at the FETCH boundary rather than in each consumer on
    purpose. `price.current`, all four technicals, all four returns, the
    portfolio weights, beta, the risk tiles, the performance chart and the
    factor-model waterfall every one of them terminates in a `.iloc[-1]`, so a
    single unguarded NaN blanks the entire application. One guard here is the
    difference between an app and a wall of "N/A".

    Consequence, accepted deliberately: `current` is the last SETTLED close, so
    during a live session the app shows the prior close rather than an intraday
    price. That keeps every number close-to-close and therefore keeps the
    portfolio beta and the attribution waterfall reconciled with SPY.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return df
    return df[df["Close"].notna()]


@_cache
def _fetch_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):        # defensive
        df.columns = df.columns.get_level_values(0)
    return clean_history(df)


@_cache
def _fetch_info(symbol: str) -> dict:
    import yfinance as yf
    try:
        return dict(yf.Ticker(symbol).get_info() or {})
    except Exception:
        return {}


# Corporate boilerplate that carries no signal when matching a headline to a company.
_CORP_STOPWORDS = {
    "corporation", "corp", "inc", "incorporated", "ltd", "limited", "co", "company",
    "plc", "group", "holdings", "holding", "shares", "trust", "the", "and", "class",
}


def _name_keywords(symbol: str, company_name: str | None) -> set:
    """Tokens that mark a headline as being about this company.

    "NVIDIA Corporation" -> {"nvda", "nvidia"};  "SPDR Gold Shares" -> {"gld", "spdr", "gold"}.
    """
    kws = {symbol.lower()}
    for tok in re.split(r"[^a-z0-9]+", (company_name or "").lower()):
        if len(tok) >= 3 and tok not in _CORP_STOPWORDS:
            kws.add(tok)
    return kws


def _news_title(item) -> str:
    """Title from either news schema: yf.Search is flat, yf.Ticker().news nests under `content`."""
    if not isinstance(item, dict):
        return ""
    content = item.get("content", item)
    return (content.get("title") if isinstance(content, dict) else None) or item.get("title") or ""


def _published(content: dict, raw: dict):
    """Publication time as a STRING, whichever schema it arrived in.

    yf.Search gives `pubDate`, an ISO string. yf.Ticker().news gives
    `providerPublishTime`, a Unix epoch int. Both land in the same
    `news[].published` field, so consumers that treat it as text — and they all
    do; it goes into prompts — would break on whichever one they didn't expect.
    `agents.explainer._news_block` did exactly that: `.strip()` on an int,
    crashing the live explainer for any ticker whose headlines came from the
    Ticker endpoint. Normalised here so there is one type to reason about.
    """
    value = content.get("pubDate") or raw.get("providerPublishTime")
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(value)
    return str(value)


@_cache
def _fetch_news(symbol: str, company_name: str | None = None) -> list:
    """Recent news for `symbol`, filtered down to headlines actually about the company.

    Yahoo exposes two news endpoints and neither is clean on its own. `yf.Ticker().news`
    is a generic "related finance stories" panel — measured across the demo book only 41%
    of its headlines mention the company they are attached to (NVDA's top story was about
    Teva). `yf.Search()` is better on some names and worse on others (NVDA 8/10, XOM 3/10),
    and its `relatedTickers` field is not trustworthy either — Yahoo tags "Dividend ETFs vs.
    Bond ETFs" with NVDA.

    This matters because these headlines are injected into the debate agents' system prompt
    and the explainer's evidence list, and both prompts instruct the model to cite a headline
    as evidence. Feeding them stories about other companies invites exactly the fabrication
    the prompts are written to prevent.

    So: pool both sources, de-duplicate, and keep the headlines that name the company. That
    trades volume for precision — about 5.7 relevant headlines per ticker instead of 10 of
    which ~4 are relevant. If the filter would empty the list, the unfiltered pool is returned
    rather than starving the tab.
    """
    import yfinance as yf

    pool = []
    for fetch in (lambda: yf.Search(symbol, news_count=10).news,
                  lambda: yf.Ticker(symbol).news):
        try:
            pool.extend(fetch() or [])
        except Exception:  # noqa: BLE001 - one source failing must not lose the other
            pass

    seen, unique = set(), []
    for item in pool:
        key = _news_title(item).lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    kws = _name_keywords(symbol, company_name)
    relevant = [i for i in unique if any(k in _news_title(i).lower() for k in kws)]
    return relevant or unique


# --------------------------------------------------------------------------
# Indicators (pandas only)
# --------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int = 14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    val = (100 - 100 / (1 + rs)).iloc[-1]
    return round(float(val), 1) if np.isfinite(val) else None


def _atr(df: pd.DataFrame, period: int = 14):
    if len(df) < period + 1 or not {"High", "Low", "Close"} <= set(df.columns):
        return None
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return round(float(val), 2) if np.isfinite(val) else None


def _sma(close: pd.Series, window: int):
    if len(close) < window:
        return None
    val = close.rolling(window).mean().iloc[-1]
    return round(float(val), 2) if np.isfinite(val) else None


def _ret(close: pd.Series, lookback: int):
    if len(close) <= lookback:
        return None
    val = close.iloc[-1] / close.iloc[-1 - lookback] - 1.0
    return round(float(val) * 100, 2) if np.isfinite(val) else None


def _today_change(close: pd.Series):
    if len(close) < 2:
        return None
    val = close.iloc[-1] / close.iloc[-2] - 1.0
    return round(float(val) * 100, 2) if np.isfinite(val) else None


def _ytd(close: pd.Series):
    """Actual year-to-date return, baselined on the PRIOR year's final close.

    The previous implementation hardcoded a 138-trading-day lookback and called
    the result "ytd". That is only correct on one arbitrary day of the year and
    drifts further from the truth every session after it.

    Baselining on last December's close (rather than this January's first close)
    matches how YTD is quoted everywhere else. When the window doesn't reach
    back that far we fall back to the first bar of the current year, and when
    there isn't even that we return None — the honest answer in early January.
    """
    if not isinstance(close.index, pd.DatetimeIndex) or len(close) < 2:
        return None

    current_year = close.index[-1].year
    in_year = np.asarray(close.index.year == current_year)
    if not in_year.any():
        return None

    first_pos = int(np.argmax(in_year))          # first bar of the current year
    if first_pos > 0:
        base_pos = first_pos - 1                 # prior year's final close
    elif in_year.sum() >= 2:
        base_pos = first_pos                     # history starts inside this year
    else:
        return None                              # nothing meaningful to measure

    base = float(close.iloc[base_pos])
    last = float(close.iloc[-1])
    if not np.isfinite(base) or not np.isfinite(last) or base == 0:
        return None
    return round((last / base - 1.0) * 100, 2)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get_benchmark_history(symbol: str = "SPY") -> pd.DataFrame:
    """1y OHLCV for a benchmark/ETF. Used by beta/performance for SPY."""
    df = _fetch_history(symbol)
    if df is None or df.empty:
        raise TickerNotFoundError(f"No history for benchmark {symbol!r}")
    return df


def get_context(ticker: str) -> dict:
    ticker = str(ticker).upper().strip()
    hist = _fetch_history(ticker)
    if hist is None or hist.empty:
        raise TickerNotFoundError(f"Ticker not found or no history: {ticker!r}")

    info = _fetch_info(ticker)
    close = hist["Close"]
    current = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else None
    sector = info.get("sector") or "Unknown"
    etf = SECTOR_ETF.get(sector, "SPY")

    def _bench_change(sym):
        try:
            c = _fetch_history(sym)["Close"]
            return round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2)
        except Exception:
            return None

    # Search matches on the company's name far better than on its ticker symbol.
    company_name = info.get("shortName") or info.get("longName") or ticker

    news_out = []
    for n in (_fetch_news(ticker, company_name) or [])[:10]:
        # yfinance news schema has shifted over versions; probe both shapes.
        content = n.get("content", n) if isinstance(n, dict) else {}
        publisher = ((content.get("provider", {}) or {}).get("displayName")
                     if isinstance(content.get("provider"), dict) else n.get("publisher"))
        link = ((content.get("canonicalUrl", {}) or {}).get("url")
                if isinstance(content.get("canonicalUrl"), dict) else n.get("link"))
        title = content.get("title") or n.get("title")
        news_out.append({
            # Every field is text or None. These strings are interpolated into
            # LLM prompts, so a stray int here surfaces as a crash in an agent.
            "title": str(title) if title is not None else None,
            "publisher": str(publisher) if publisher is not None else None,
            "published": _published(content, n),
            "link": str(link) if link is not None else None,
        })

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "sector_etf": etf,
        "price": {
            "current": round(current, 2),
            "prev_close": round(prev_close, 2) if prev_close is not None else None,
            "day_change_pct": _today_change(close),
        },
        "returns": {
            "1d": _today_change(close), "5d": _ret(close, 5),
            "1m": _ret(close, 21), "ytd": _ytd(close),
        },
        "fundamentals": {
            "pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap": info.get("marketCap"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
        },
        "technicals": {
            "rsi_14": _rsi(close), "sma_50": _sma(close, 50),
            "sma_200": _sma(close, 200), "atr": _atr(hist),
        },
        "news": news_out,
        "benchmarks": {
            "SPY": _bench_change("SPY"),
            etf: _bench_change(etf),
            "VIX": _bench_change("^VIX"),
        },
        "history": hist,
    }


def get_context_batch(tickers: list) -> dict:
    """{ticker: context}. Tickers with no history are omitted — the caller is
    expected to diff its request against the returned keys and tell the user
    which ones failed, rather than letting them show up as unexplained N/A."""
    out = {}
    for t in tickers:
        try:
            out[str(t).upper().strip()] = get_context(t)
        except TickerNotFoundError:
            continue
    return out
