"""market_data/refresh.py — record a live snapshot into the offline fixture.

    .venv/bin/python -m market_data.refresh              # the demo book
    .venv/bin/python -m market_data.refresh TSLA PLTR    # plus extras

Always hits LIVE yfinance regardless of USE_MOCK — recording from the fixture
would be a no-op that silently froze the data forever.

Everything written here has already been through `live.clean_history`, so the
fixture can never carry the unsettled-Close defect. The snapshot is validated
before it is written: a fixture that quietly recorded garbage would push the
failure all the way out to the demo, which is the one place it must not happen.
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from market_data import live  # noqa: E402
from market_data.errors import TickerNotFoundError  # noqa: E402

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "market_data.json")
PORTFOLIO_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_portfolio.json")

# Contract B, exactly as docs/INTEGRATION_CONTRACT.md freezes it.
REQUIRED_TOP = {"ticker", "company_name", "sector", "sector_etf", "price",
                "returns", "fundamentals", "technicals", "news", "benchmarks",
                "history"}
REQUIRED_PRICE = {"current", "prev_close", "day_change_pct"}
REQUIRED_RETURNS = {"1d", "5d", "1m", "ytd"}
REQUIRED_FUNDAMENTALS = {"pe", "forward_pe", "market_cap", "profit_margin",
                         "revenue_growth", "debt_to_equity"}
REQUIRED_TECHNICALS = {"rsi_14", "sma_50", "sma_200", "atr"}

MIN_HISTORY_ROWS = 200


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------

def _serialize_frame(df: pd.DataFrame) -> dict:
    """OHLCV frame -> JSON-safe payload that round-trips tz and dtypes exactly."""
    idx = df.index
    tz = str(idx.tz) if getattr(idx, "tz", None) is not None else None
    utc_idx = idx.tz_convert("UTC") if tz else idx
    return {
        "tz": tz,
        "index_name": idx.name,
        "index": [ts.isoformat() for ts in utc_idx],
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
        "data": [[None if pd.isna(v) else float(v) for v in row]
                 for row in df.to_numpy()],
    }


def _json_safe(obj):
    """numpy scalars and NaN/inf are not JSON — normalise before writing."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if not np.isfinite(f) else f
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


# --------------------------------------------------------------------------
# Validation — run BEFORE writing
# --------------------------------------------------------------------------

def validate(contexts: dict, histories: dict) -> tuple[list, list]:
    """Return (errors, warnings). Errors block the write; warnings are printed.

    The split matters: a missing P/E is normal for an ETF and must not stop a
    snapshot, but a NaN close or a broken contract would poison every consumer.
    """
    errors, warns = [], []

    for ticker, ctx in contexts.items():
        missing = REQUIRED_TOP - set(ctx) - {"history"}
        if missing:
            errors.append(f"{ticker}: context missing keys {sorted(missing)}")
        for name, required in (("price", REQUIRED_PRICE),
                               ("returns", REQUIRED_RETURNS),
                               ("fundamentals", REQUIRED_FUNDAMENTALS),
                               ("technicals", REQUIRED_TECHNICALS)):
            block = ctx.get(name) or {}
            gap = required - set(block)
            if gap:
                errors.append(f"{ticker}: {name} missing {sorted(gap)}")

        price = ctx.get("price") or {}
        if not isinstance(price.get("current"), (int, float)) or \
                not np.isfinite(float(price.get("current") or np.nan)):
            errors.append(f"{ticker}: price.current is not a finite number "
                          f"({price.get('current')!r})")
        if price.get("day_change_pct") is None:
            warns.append(f"{ticker}: no day_change_pct")

        # Fundamentals are genuinely absent for ETFs/commodities — warn only.
        fundamentals = ctx.get("fundamentals") or {}
        empty = [k for k, v in fundamentals.items() if v is None]
        if len(empty) == len(REQUIRED_FUNDAMENTALS):
            warns.append(f"{ticker}: no fundamentals at all (normal for an ETF)")

        technicals = ctx.get("technicals") or {}
        blank = [k for k, v in technicals.items() if v is None]
        if blank:
            warns.append(f"{ticker}: technicals unavailable: {blank}")

        news = ctx.get("news") or []
        # Every news field must be text. These are interpolated straight into
        # LLM prompts; `published` used to arrive as a Unix epoch int from one of
        # yfinance's two news schemas and crashed the explainer on `.strip()`.
        for i, item in enumerate(news):
            for field in ("title", "publisher", "published", "link"):
                value = (item or {}).get(field)
                if value is not None and not isinstance(value, str):
                    errors.append(
                        f"{ticker}: news[{i}].{field} is {type(value).__name__}, "
                        f"expected str or None ({value!r})")

        titled = [n for n in news if (n or {}).get("title")]
        if not titled:
            warns.append(f"{ticker}: NO usable headlines — the explainer tab "
                         f"will correctly answer 'no clear cause found' offline")
        else:
            linkless = [n for n in titled if not n.get("link")]
            if linkless:
                warns.append(f"{ticker}: {len(linkless)}/{len(titled)} headlines have no link")

    for symbol, df in histories.items():
        if df is None or df.empty:
            errors.append(f"{symbol}: empty history")
            continue
        if "Close" not in df.columns:
            errors.append(f"{symbol}: history has no Close column")
            continue
        n_nan = int(df["Close"].isna().sum())
        if n_nan:
            errors.append(f"{symbol}: {n_nan} NaN Close rows survived cleaning")
        if len(df) < MIN_HISTORY_ROWS:
            warns.append(f"{symbol}: only {len(df)} rows (< {MIN_HISTORY_ROWS})")
        if getattr(df.index, "tz", None) is None:
            warns.append(f"{symbol}: tz-naive index (live yfinance returns tz-aware)")

    return errors, warns


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def demo_book_tickers() -> list:
    """The UNION of the curated shelf and every sample profile's holdings.

    Both are sourced rather than hardcoded, so adding a holding to a profile or
    a name to `shelf.py` brings it into the offline fixture on the next refresh.

    Union, not replacement, and that ordering matters: the shelf is what the
    builder and the generator may draw on, while the profiles are what the app
    ships and what tests/test_profiles.py asserts against. If this returned the
    shelf alone, editing shelf.py could quietly drop a profile's ticker out of
    the fixture and break five sample books at once. Shelf first so the recorded
    order reads like the picker.

    Falls back to the original demo book if neither module is importable.
    """
    tickers: list = []
    try:
        import shelf
        tickers = list(shelf.tickers())
    except Exception as e:  # noqa: BLE001 — never block a refresh on this
        print(f"  (shelf unavailable: {e})")
    try:
        import profiles
        for t in profiles.all_tickers():
            if t not in tickers:
                tickers.append(t)
    except Exception as e:  # noqa: BLE001
        print(f"  (profiles unavailable: {e})")

    if tickers:
        return tickers

    print("  (falling back to mock_portfolio.json)")
    with open(PORTFOLIO_PATH, encoding="utf-8") as fh:
        portfolio = json.load(fh)
    return [p["ticker"] for p in portfolio.get("positions", [])]


def refresh(extra_tickers: list | None = None, path: str = FIXTURE_PATH) -> dict:
    tickers = demo_book_tickers()
    for t in (extra_tickers or []):
        t = str(t).upper().strip()
        if t and t not in tickers:
            tickers.append(t)

    print(f"Recording {len(tickers)} tickers: {', '.join(tickers)}\n")

    contexts, histories, failed = {}, {}, []
    for ticker in tickers:
        try:
            ctx = live.get_context(ticker)
        except TickerNotFoundError as e:
            failed.append(ticker)
            print(f"  ✗ {ticker:6s} {e}")
            continue
        history = ctx.pop("history")
        contexts[ticker] = ctx
        histories[ticker] = history
        news_n = len([n for n in ctx.get("news") or [] if (n or {}).get("title")])
        print(f"  ✓ {ticker:6s} {ctx['company_name'][:34]:34s} "
              f"${ctx['price']['current']:>9,.2f}  "
              f"{len(history):>3d} bars  {news_n:>2d} headlines")

    # Benchmarks the factor model and the dashboard will ask for.
    benchmarks = {"SPY", "^VIX"} | {c.get("sector_etf") for c in contexts.values()
                                    if c.get("sector_etf")}
    print()
    for symbol in sorted(benchmarks):
        if symbol in histories:
            continue
        try:
            histories[symbol] = live.get_benchmark_history(symbol)
            print(f"  ✓ {symbol:6s} benchmark  {len(histories[symbol]):>3d} bars")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {symbol:6s} benchmark unavailable: {e}")

    if not contexts:
        raise SystemExit("\nNothing recorded — refusing to write an empty fixture.")

    errors, warns = validate(contexts, histories)
    print()
    for w in warns:
        print(f"  ! {w}")
    if errors:
        print()
        for e in errors:
            print(f"  ✗ ERROR {e}")
        raise SystemExit(f"\n{len(errors)} validation error(s) — fixture NOT written.")

    import yfinance as yf
    payload = {
        "snapshot_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "yfinance_version": getattr(yf, "__version__", "unknown"),
        "generated_by": "market_data.refresh",
        "tickers": sorted(contexts),
        "failed": failed,
        "contexts": _json_safe(contexts),
        "histories": {s: _serialize_frame(df) for s, df in histories.items()},
    }

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)

    size_kb = os.path.getsize(path) / 1024
    print(f"\nWrote {path}")
    print(f"  {len(contexts)} contexts · {len(histories)} histories · "
          f"{size_kb:,.0f} KB · snapshot {payload['snapshot_utc']}")
    if warns:
        print(f"  {len(warns)} warning(s) above — none blocking.")
    return payload


if __name__ == "__main__":
    refresh(sys.argv[1:])
