"""
data_layer.py  — LOCAL MOCK / DEV STAND-IN  (Person 1 owns the REAL version)
============================================================================
This is NOT the file you submit. In the real app, Person 1 (Core) builds
`data_layer.py` on top of yfinance and exposes:

    get_context(ticker: str) -> dict          # Contract B
    get_context_batch(tickers: list) -> dict  # {ticker: context_dict}

This mock produces the SAME schema, but from *synthetic, reproducible*
data (fixed random seed) so that Person 2's dashboard can be built and run
end-to-end WITHOUT the network, an API key, or Person 1's code being ready.

The synthetic returns are built from a market factor + per-sector factors +
idiosyncratic noise, so the correlation matrix and betas are realistic:
tech names move together, defensives (JNJ) don't. That makes the dashboard's
"you're less diversified than you think" story real, not random.

Swap this whole file for Person 1's data_layer.py at integration time.
Nothing in portfolio_metrics.py or tabs/dashboard.py imports the mock
internals — they only rely on the shared contract.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

# Anchored to this file, not to the process working directory. These helpers
# author and reload a fixture, and a CWD-relative default silently writes the
# JSON wherever the caller happened to be standing.
_CONTEXT_JSON = os.path.join(os.path.dirname(__file__), "fixtures", "mock_context.json")

# --------------------------------------------------------------------------
# Universe definition (fixed, deterministic)
# --------------------------------------------------------------------------

SECTOR_ETF = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Communication Services": "XLC",
}

# ticker -> (company_name, sector, market_beta, sector_beta, target_price)
# target_price = the most-recent close we want the series to END on, so the
# demo portfolio has controlled, sensible weights.
_UNIVERSE = {
    "NVDA": ("NVIDIA Corporation",         "Technology",         1.55, 0.85, 175.0),
    "MSFT": ("Microsoft Corporation",      "Technology",         1.15, 0.80, 430.0),
    "AAPL": ("Apple Inc.",                 "Technology",         1.20, 0.75, 210.0),
    "JNJ":  ("Johnson & Johnson",          "Healthcare",         0.62, 0.70, 160.0),
    "JPM":  ("JPMorgan Chase & Co.",       "Financial Services", 1.10, 0.80, 210.0),
    "XOM":  ("Exxon Mobil Corporation",    "Energy",             0.85, 0.90, 112.0),
    # Gold: a genuine DIVERSIFIER. Slightly negative market beta and its own
    # factor -> low/negative correlation with the equity sleeve, so the heatmap
    # actually shows its blue (negative) range instead of an all-red block.
    "GLD":  ("SPDR Gold Shares",           "Commodities",       -0.15, 0.00, 205.0),
}

# Benchmarks / sector ETFs we also synthesize so beta & the factor model work.
_ETF_TARGET = {"SPY": 560.0, "XLK": 245.0, "XLV": 150.0, "XLF": 48.0, "XLE": 95.0}

_N_DAYS = 252
_END_DATE = "2026-07-17"          # fixed "today" for reproducibility
_SEED = 42


# --------------------------------------------------------------------------
# Synthetic factor model  (generation only — not the analysis model)
# --------------------------------------------------------------------------

def _business_index(n: int, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def _build_returns() -> dict:
    """Generate daily returns for every ticker + ETF from shared factors."""
    rng = np.random.default_rng(_SEED)
    n = _N_DAYS

    # One market factor drives everything (this IS ~SPY's return).
    market = rng.normal(0.0004, 0.011, n)

    # Sector factors: correlated with the market but with their own component.
    sectors = ["Technology", "Healthcare", "Financial Services", "Energy"]
    sector_factor = {
        s: 0.5 * market + rng.normal(0.0, 0.006, n) for s in sectors
    }

    out = {}

    # SPY ~ the market factor plus a whisper of tracking noise.
    out["SPY"] = market + rng.normal(0.0, 0.0005, n)

    # Sector ETFs: load on market + own sector factor.
    etf_sector = {"XLK": "Technology", "XLV": "Healthcare",
                  "XLF": "Financial Services", "XLE": "Energy"}
    for etf, sec in etf_sector.items():
        out[etf] = (0.9 * market + 0.9 * sector_factor[sec]
                    + rng.normal(0.0, 0.004, n))

    # Individual stocks: market beta * market + sector beta * sector factor + idio.
    idio_sigma = {"NVDA": 0.014, "MSFT": 0.009, "AAPL": 0.010,
                  "JNJ": 0.007, "JPM": 0.009, "XOM": 0.011, "GLD": 0.009}
    for tkr, (_, sec, b_mkt, b_sec, _) in _UNIVERSE.items():
        sec_f = sector_factor.get(sec, np.zeros(n))   # e.g. Commodities has none
        out[tkr] = (b_mkt * market
                    + b_sec * sec_f
                    + rng.normal(0.0, idio_sigma.get(tkr, 0.010), n))

    return out


def _returns_to_ohlcv(returns: np.ndarray, target_price: float,
                      index: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    """Turn a daily-return series into an OHLCV frame ending exactly on target_price."""
    rel = np.cumprod(1.0 + returns)
    close = target_price * rel / rel[-1]           # force last close == target
    prev = np.concatenate([[close[0] / (1.0 + returns[0])], close[:-1]])
    openp = prev * (1.0 + rng.normal(0.0, 0.002, len(close)))
    high = np.maximum(openp, close) * (1.0 + np.abs(rng.normal(0.0, 0.004, len(close))))
    low = np.minimum(openp, close) * (1.0 - np.abs(rng.normal(0.0, 0.004, len(close))))
    vol = rng.integers(5_000_000, 60_000_000, len(close))
    return pd.DataFrame(
        {"Open": openp, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=index,
    )


# Build everything once, cache in module state.
_HISTORY: dict[str, pd.DataFrame] = {}


def _ensure_built() -> None:
    if _HISTORY:
        return
    index = _business_index(_N_DAYS, _END_DATE)
    returns = _build_returns()
    rng = np.random.default_rng(_SEED + 1)  # separate stream for OHLC noise
    targets = {**{t: _UNIVERSE[t][4] for t in _UNIVERSE}, **_ETF_TARGET}
    for sym, r in returns.items():
        _HISTORY[sym] = _returns_to_ohlcv(np.asarray(r), targets[sym], index, rng)


# --------------------------------------------------------------------------
# Technical helpers (so the mock context is faithful; dashboard doesn't need them)
# --------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _pct(series: pd.Series, lookback: int) -> float:
    if len(series) <= lookback:
        return None
    return round(float(series.iloc[-1] / series.iloc[-1 - lookback] - 1.0) * 100, 2)


# --------------------------------------------------------------------------
# Public API — matches Person 1's real data_layer.py contract (Contract B)
# --------------------------------------------------------------------------

def get_benchmark_history(symbol: str = "SPY") -> pd.DataFrame:
    """1y daily OHLCV for a benchmark/ETF (SPY, XLK, ...). Mock replacement
    for the direct yfinance call the dashboard's beta/benchmark functions make."""
    _ensure_built()
    if symbol not in _HISTORY:
        raise KeyError(f"No mock history for benchmark {symbol!r}")
    return _HISTORY[symbol].copy()


def get_context(ticker: str) -> dict:
    """Return Contract-B context dict for a single ticker (synthetic)."""
    _ensure_built()
    ticker = ticker.upper().strip()
    if ticker not in _UNIVERSE:
        raise KeyError(f"TickerNotFound (mock): {ticker!r}")

    name, sector, b_mkt, _, _ = _UNIVERSE[ticker]
    hist = _HISTORY[ticker]
    close = hist["Close"]
    current = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    day_change_pct = round((current / prev_close - 1.0) * 100, 2)
    etf = SECTOR_ETF.get(sector, "SPY")

    spy_c = _HISTORY["SPY"]["Close"]
    etf_c = _HISTORY[etf]["Close"] if etf in _HISTORY else spy_c

    return {
        "ticker": ticker,
        "company_name": name,
        "sector": sector,
        "sector_etf": etf,
        "price": {
            "current": round(current, 2),
            "prev_close": round(prev_close, 2),
            "day_change_pct": day_change_pct,
        },
        "returns": {
            "1d": day_change_pct,
            "5d": _pct(close, 5),
            "1m": _pct(close, 21),
            "ytd": _pct(close, 138),
        },
        "fundamentals": {
            "pe": round(float(20 + b_mkt * 10), 1),
            "forward_pe": round(float(18 + b_mkt * 8), 1),
            "market_cap": int(current * 1e9 * (5 + b_mkt)),
            "profit_margin": round(float(0.15 + 0.2 * (2 - b_mkt)), 2),
            "revenue_growth": round(float(0.05 + 0.1 * b_mkt), 2),
            "debt_to_equity": round(float(0.3 + 0.2 * b_mkt), 2),
        },
        "technicals": {
            "rsi_14": round(_rsi(close), 1),
            "sma_50": round(float(close.rolling(50).mean().iloc[-1]), 2),
            "sma_200": round(float(close.rolling(200).mean().iloc[-1]), 2),
            "atr": round(_atr(hist), 2),
        },
        "news": [
            {
                "title": f"{name} reported updates ahead of the next earnings cycle",
                "publisher": "Reuters",
                "published": "2026-07-16T13:20:00Z",
                "link": "https://example.com/news/1",
            },
            {
                "title": f"Analysts revisit {ticker} price targets after sector moves",
                "publisher": "Bloomberg",
                "published": "2026-07-17T09:05:00Z",
                "link": "https://example.com/news/2",
            },
        ],
        "benchmarks": {
            "SPY": round((float(spy_c.iloc[-1]) / float(spy_c.iloc[-2]) - 1) * 100, 2),
            etf: round((float(etf_c.iloc[-1]) / float(etf_c.iloc[-2]) - 1) * 100, 2),
            "VIX": 18.2,
        },
        "history": hist.copy(),
    }


def get_context_batch(tickers: list) -> dict:
    """Return {ticker: context_dict} for a list of tickers."""
    result = {}
    for t in tickers:
        try:
            result[t.upper().strip()] = get_context(t)
        except KeyError:
            # Real data_layer would do the same: skip unknown tickers gracefully.
            continue
    return result


# --------------------------------------------------------------------------
# JSON serialization — the faithful stand-in for Person 1's mock_context.json.
# JSON can't hold a DataFrame, so `history` is stored as records and rebuilt on
# load. Teammates 3 & 4 (debate / attribution) can build against this file, and
# it demonstrates the exact serialization Person 1's real mock should use.
# --------------------------------------------------------------------------

def _history_to_records(df: pd.DataFrame) -> dict:
    d = df.copy()
    d.index = pd.DatetimeIndex(d.index).strftime("%Y-%m-%d")
    return {"index": list(d.index), "columns": list(map(str, d.columns)),
            "data": d.to_numpy().tolist()}


def _records_to_history(rec: dict) -> pd.DataFrame:
    return pd.DataFrame(rec["data"], columns=rec["columns"],
                        index=pd.to_datetime(rec["index"]))


def export_mock_context_json(path: str = _CONTEXT_JSON, tickers: list | None = None) -> str:
    """Write a JSON with each ticker's full context (history as records) + SPY."""
    tickers = tickers or list(_UNIVERSE.keys())
    payload = {}
    for t in tickers:
        c = dict(get_context(t))
        c["history"] = _history_to_records(c["history"])
        payload[t] = c
    payload["_benchmarks"] = {"SPY": _history_to_records(get_benchmark_history("SPY"))}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return path


def load_mock_context_json(path: str = _CONTEXT_JSON) -> dict:
    """Rebuild {ticker: context} (history back to a DataFrame) from the JSON."""
    with open(path) as f:
        payload = json.load(f)
    out = {}
    for t, c in payload.items():
        if t == "_benchmarks":
            continue
        c = dict(c)
        c["history"] = _records_to_history(c["history"])
        out[t] = c
    return out


def load_benchmark_json(path: str = _CONTEXT_JSON, symbol: str = "SPY") -> pd.DataFrame:
    with open(path) as f:
        payload = json.load(f)
    return _records_to_history(payload["_benchmarks"][symbol])


if __name__ == "__main__":
    ctxs = get_context_batch(["NVDA", "JNJ", "GLD"])
    for t, c in ctxs.items():
        print(f"{t}: {c['company_name']} | price {c['price']['current']} "
              f"| dchg {c['price']['day_change_pct']}% | hist {c['history'].shape}")
    print("SPY last close:", get_benchmark_history('SPY')['Close'].iloc[-1].round(2))
    p = export_mock_context_json()
    print("wrote", p)
