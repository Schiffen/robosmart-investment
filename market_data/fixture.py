"""market_data/fixture.py — replay recorded market data, no network.

Serves the same Contract B as `market_data.live`, from a snapshot written by
`market_data.refresh`. Used when USE_MOCK=1 / USE_MOCK_DATA=1.

Fidelity is the whole point. Two things are preserved deliberately even though
a simpler fixture would "work":

1. **A tz-aware DatetimeIndex** (America/New_York), because that is what
   `yf.Ticker().history()` really returns. `portfolio_metrics._daily_returns`
   and `factor_model._returns` both carry tz-normalisation code specifically to
   survive it. A tz-naive fixture would leave that path untested offline and let
   a tz regression hide until it reached live data.
2. **The real recorded values** — real prices, real company names, real
   fundamentals, real headlines with working links. The debate and explainer
   prompts instruct the model to cite figures and headlines; feeding them
   invented ones offline would train the demo on exactly the fabrication the
   prompts exist to prevent.
"""

from __future__ import annotations

import copy
import json
import os

import pandas as pd

from market_data.errors import TickerNotFoundError

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "market_data.json")

_CACHE: dict | None = None


class FixtureMissingError(Exception):
    """The fixture file is absent or unreadable."""


def _load() -> dict:
    """Read and memoise the fixture. Raises a directly actionable error."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.exists(FIXTURE_PATH):
        raise FixtureMissingError(
            f"No market-data fixture at {FIXTURE_PATH}. Record one with:\n"
            f"    .venv/bin/python -m market_data.refresh"
        )
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        _CACHE = json.load(fh)
    return _CACHE


def reset_cache() -> None:
    """Drop the memoised fixture. For tests that write their own."""
    global _CACHE
    _CACHE = None


def _frame(payload: dict) -> pd.DataFrame:
    """Rebuild an OHLCV DataFrame, restoring the recorded timezone and dtypes.

    Dtypes are restored rather than left as float64 so the frame is
    indistinguishable from what yfinance hands back — Volume is int64 live, and
    a fixture that quietly widened it would let a dtype-sensitive bug pass
    offline and fail in production.
    """
    idx = pd.to_datetime(payload["index"], utc=True)
    tz = payload.get("tz")
    idx = idx.tz_convert(tz) if tz else idx.tz_localize(None)
    df = pd.DataFrame(payload["data"], columns=payload["columns"], index=idx)
    df.index.name = payload.get("index_name") or "Date"
    for col, dtype in (payload.get("dtypes") or {}).items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except (TypeError, ValueError):
                pass  # e.g. a NaN in an int column — the float form is fine
    return df


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------

def snapshot_utc() -> str | None:
    """Full ISO timestamp of when the fixture was recorded."""
    try:
        return _load().get("snapshot_utc")
    except FixtureMissingError:
        return None


def snapshot_date() -> str | None:
    """Just the date, for the sidebar banner."""
    stamp = snapshot_utc()
    return stamp.split("T")[0] if stamp else None


def available_tickers() -> list:
    try:
        return sorted(_load().get("contexts", {}).keys())
    except FixtureMissingError:
        return []


# --------------------------------------------------------------------------
# Public API — mirrors market_data.live
# --------------------------------------------------------------------------

def get_benchmark_history(symbol: str = "SPY") -> pd.DataFrame:
    data = _load()
    payload = data.get("histories", {}).get(str(symbol).upper().strip())
    if payload is None:
        raise TickerNotFoundError(
            f"No recorded history for benchmark {symbol!r}. "
            f"Recorded: {sorted(data.get('histories', {}))}"
        )
    return _frame(payload)


def get_context(ticker: str) -> dict:
    ticker = str(ticker).upper().strip()
    data = _load()
    ctx = data.get("contexts", {}).get(ticker)
    if ctx is None:
        raise TickerNotFoundError(
            f"{ticker!r} is not in the offline fixture "
            f"(recorded: {', '.join(available_tickers()) or 'nothing'}). "
            f"Run without USE_MOCK to fetch it live, or re-record with "
            f"`python -m market_data.refresh {ticker}`."
        )
    history = data.get("histories", {}).get(ticker)
    if history is None:
        raise TickerNotFoundError(f"Fixture has a context but no history for {ticker!r}")

    # Deep copy so a consumer mutating the context can't poison the cache for
    # the next caller — the live provider hands back fresh objects every time.
    out = copy.deepcopy(ctx)
    out["history"] = _frame(history)
    return out


def get_context_batch(tickers: list) -> dict:
    """{ticker: context}, omitting anything not recorded — same contract, and
    same caller responsibility to diff the keys, as the live provider."""
    out = {}
    for t in tickers:
        try:
            out[str(t).upper().strip()] = get_context(t)
        except TickerNotFoundError:
            continue
    return out
