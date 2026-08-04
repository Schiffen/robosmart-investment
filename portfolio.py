"""
portfolio.py — Contract A: the one place a portfolio is validated.
==================================================================
def validate_rows(rows, *, universe=None) -> list[dict]   # issues, not exceptions
def build_portfolio(rows, cash=0.0, ...) -> dict           # rows  -> Contract A
def from_weights(allocation, prices, investable, ...)      # weights -> Contract A
def parse_portfolio(uploaded_file) -> dict                 # CSV   -> Contract A
def sample_portfolio() -> dict                             # the legacy demo book
Raises PortfolioError(message) with a human-readable message on bad input.

WHY THE RULES LIVE HERE AND NOT IN A VALIDATOR MODULE
-----------------------------------------------------
Contract A now has three producers — an uploaded CSV, a book typed into the
in-app builder, and a book drafted from an investor questionnaire. They must not
each carry their own idea of what a valid position is. This module already owned
`PortfolioError` and the definition of the contract, so the rules were lifted out
of `parse_portfolio`'s row loop into `build_portfolio` and every producer routes
through it. `parse_portfolio` is now just the CSV adapter.

It imports pandas but NOT streamlit, so `agents/` and the builder can both use it.

TWO SHAPES, BECAUSE THE CALLERS NEED DIFFERENT THINGS
-----------------------------------------------------
`validate_rows` returns a LIST of issues and raises nothing: the builder shows
per-row feedback while you type and cannot use an exception for that.
`build_portfolio` raises on the first issue, which is what a file upload wants.
One implementation, so the two can never disagree about what is valid.

CASH READS FROM THE `shares` COLUMN
-----------------------------------
`CASH,5000,0` is five thousand dollars; `CASH,1,5000` is one dollar. This is
unobvious enough that the example the sidebar printed got it wrong while the
template it offered for download got it right — a user who copied the on-screen
example silently lost their cash balance. tests/test_portfolio.py pins both.
"""

from __future__ import annotations

import json
import math
import os

import pandas as pd

CASH_TICKERS = ("CASH", "$CASH")

REQUIRED_COLUMNS = ("ticker", "shares", "cost_basis")

# Fallback sector map used when yfinance sector lookup isn't available
# (offline / rate-limited). A 'sector' column in the CSV always wins.
_SECTOR_FALLBACK = {
    "NVDA": "Technology", "MSFT": "Technology", "AAPL": "Technology",
    "GOOGL": "Communication Services", "META": "Communication Services",
    "JNJ": "Healthcare", "PFE": "Healthcare", "UNH": "Healthcare",
    "JPM": "Financial Services", "BAC": "Financial Services",
    "XOM": "Energy", "CVX": "Energy", "GLD": "Commodities", "TLT": "Fixed Income",
}


class PortfolioError(Exception):
    """Human-readable error for bad portfolio input."""


def _lookup_sector(ticker: str) -> str:
    """Resolve a sector over the network. NOT offline-safe — see below.

    This calls yfinance directly rather than going through `data_layer`, so it
    ignores USE_MOCK_DATA entirely: a test or a builder keystroke would reach
    Yahoo. That is why `build_portfolio` takes `sector_for` as an argument — the
    builder passes `shelf.sector_of` and never touches the network, and tests
    stub it. The CSV path keeps this as its default because an uploaded file may
    name any ticker at all.
    """
    try:
        import yfinance as yf
        s = (yf.Ticker(ticker).get_info() or {}).get("sector")
        if s:
            return s
    except Exception:  # noqa: BLE001 — offline / bad ticker -> fallback
        pass
    return _SECTOR_FALLBACK.get(ticker.upper(), "Unknown")


# --------------------------------------------------------------------------
# Row classification
# --------------------------------------------------------------------------

def _ticker_of(row) -> str:
    tk = row.get("ticker", "")
    if tk is None or (isinstance(tk, float) and math.isnan(tk)):
        return ""
    tk = str(tk).strip().upper()
    return "" if tk == "NAN" else tk


def _is_cash(ticker: str) -> bool:
    return ticker in CASH_TICKERS


def _cash_amount(row) -> float:
    """A CASH row's amount, read from the SHARES column. Never raises.

    Deliberately unlike every other numeric failure in this module: a cash row
    that cannot be read leaves cash at zero rather than rejecting the whole
    file. That is the behaviour the CSV path has always had and changing it
    would reject files that load today.
    """
    try:
        v = row.get("shares")
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return 0.0
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_rows(rows, *, universe=None) -> list[dict]:
    """Contract-A row rules, as a list of issues rather than an exception.

    Each issue: {"row": int, "ticker": str, "field": str, "message": str}.
    An empty list means every row is usable.

    Blank rows and CASH rows are NOT issues — they are simply not positions.
    `universe`, when given, restricts which tickers are allowed: the in-app
    builder passes the shelf so a generated or typed book can always be priced,
    while the CSV path passes None because a user's own file may hold anything
    and live mode can go and fetch it.
    """
    issues: list[dict] = []
    allowed = None if universe is None else {str(t).strip().upper() for t in universe}

    for i, row in enumerate(rows):
        tk = _ticker_of(row)
        if not tk or _is_cash(tk):
            continue

        if allowed is not None and tk not in allowed:
            issues.append({"row": i, "ticker": tk, "field": "ticker",
                           "message": f"{tk} is not one of the tickers this app "
                                      f"has market data for."})
            continue

        try:
            shares = float(row["shares"])
            cost = float(row["cost_basis"])
        except (KeyError, TypeError, ValueError):
            issues.append({"row": i, "ticker": tk, "field": "shares",
                           "message": f"Non-numeric shares/cost_basis for ticker {tk}."})
            continue

        # `nan <= 0` is False, so a blank cell used to sail past the range check
        # below and enter Contract A as `shares: NaN`. Every weight in this app
        # is a share of a total, and one NaN silently redistributes all the
        # others rather than failing. Checked BEFORE the range test, on purpose.
        if not (math.isfinite(shares) and math.isfinite(cost)):
            issues.append({"row": i, "ticker": tk, "field": "shares",
                           "message": f"Non-numeric shares/cost_basis for ticker {tk}."})
            continue

        if shares <= 0 or cost < 0:
            issues.append({"row": i, "ticker": tk, "field": "shares",
                           "message": f"Shares must be > 0 and cost_basis >= 0 "
                                      f"(ticker {tk})."})
    return issues


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------

def build_portfolio(rows, cash: float = 0.0, *, currency: str = "USD",
                    sector_for=None, universe=None,
                    empty_message: str = "No valid positions found in the file.",
                    ) -> dict:
    """rows -> Contract A. Raises PortfolioError on the first issue.

    `rows` is any iterable of mappings with `ticker`, `shares`, `cost_basis` and
    an optional `sector`. CASH rows in `rows` ADD to the `cash` argument, so the
    CSV path can hand the frame over untouched while the builder passes cash
    separately.

    Duplicate tickers merge to a weighted-average cost basis — the same rule
    `agents.tools.simulate_trade` applies when the analyst models a buy, so a
    book assembled here and a book the agent reasons about agree.
    """
    rows = list(rows)
    issues = validate_rows(rows, universe=universe)
    if issues:
        raise PortfolioError(issues[0]["message"])

    sector_for = sector_for or _lookup_sector
    total_cash = float(cash or 0.0)
    positions: dict[str, dict] = {}

    for row in rows:
        tk = _ticker_of(row)
        if not tk:
            continue
        if _is_cash(tk):
            total_cash += _cash_amount(row)
            continue

        shares = float(row["shares"])
        cost = float(row["cost_basis"])

        sector = row.get("sector")
        if sector is None or (isinstance(sector, float) and math.isnan(sector)):
            sector = None
        else:
            sector = str(sector).strip() or None
        sector = sector or sector_for(tk)

        if tk in positions:  # merge duplicates -> weighted-average cost basis
            p = positions[tk]
            total = p["shares"] + shares
            p["cost_basis"] = ((p["cost_basis"] * p["shares"] + cost * shares) / total
                               if total else cost)
            p["shares"] = total
        else:
            positions[tk] = {"ticker": tk, "shares": shares,
                             "cost_basis": cost, "sector": sector}

    if not positions:
        raise PortfolioError(empty_message)
    return {"positions": list(positions.values()), "cash": float(total_cash),
            "currency": currency}


def from_weights(allocation, prices: dict, investable: float, *,
                 cash: float = 0.0, currency: str = "USD",
                 sector_for=None) -> dict:
    """[{ticker, weight_pct}] + {ticker: price} -> Contract A.

    The generator returns WEIGHTS and nothing else. Shares are derived here from
    a real price, so "invested" on screen is arithmetic the app performed rather
    than a number a model wrote. A model-authored share count would imply a
    model-authored price, and the book's stated value would then be fiction.

    `cost_basis` is today's close — exactly what `agents.tools.simulate_trade`
    sets when it opens a new position. A synthetic book has no purchase history,
    and inventing one would print a fabricated P&L on the dashboard's first
    screen.
    """
    rows = []
    for a in allocation or []:
        tk = str(a.get("ticker", "") or "").strip().upper()
        if not tk:
            continue
        try:
            weight = float(a.get("weight_pct") or 0.0)
            price = float(prices.get(tk) or 0.0)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(weight) and math.isfinite(price)) or weight <= 0 or price <= 0:
            continue
        shares = round(weight / 100.0 * float(investable) / price, 2)
        if shares <= 0:
            continue
        rows.append({"ticker": tk, "shares": shares, "cost_basis": price})

    return build_portfolio(
        rows, cash=cash, currency=currency, sector_for=sector_for,
        empty_message="None of the drafted holdings could be priced.")


# --------------------------------------------------------------------------
# The CSV adapter
# --------------------------------------------------------------------------

def parse_portfolio(uploaded_file) -> dict:
    """Accepts a path, file-like, or Streamlit UploadedFile of a CSV with
    columns ticker, shares, cost_basis (case-insensitive; optional 'sector'
    and a 'CASH' row)."""
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:  # noqa: BLE001
        raise PortfolioError(f"Couldn't read the CSV file: {e}")

    if df is None or df.empty:
        raise PortfolioError("The uploaded file is empty.")

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise PortfolioError(
            "Missing column(s): " + ", ".join(sorted(missing))
            + ". The CSV needs: ticker, shares, cost_basis.")

    # universe=None: an uploaded file may name any ticker, and live mode can go
    # and price it. Only the in-app builder is confined to the shelf.
    return build_portfolio(df.to_dict("records"), universe=None)


def sample_portfolio() -> dict:
    """The demo book (loads fixtures/mock_portfolio.json; falls back to an inline copy)."""
    p = os.path.join(os.path.dirname(__file__), "fixtures", "mock_portfolio.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {
        "positions": [
            {"ticker": "NVDA", "shares": 12, "cost_basis": 150.0, "sector": "Technology"},
            {"ticker": "MSFT", "shares": 20, "cost_basis": 460.0, "sector": "Technology"},
            {"ticker": "AAPL", "shares": 30, "cost_basis": 175.0, "sector": "Technology"},
            {"ticker": "JNJ", "shares": 25, "cost_basis": 170.0, "sector": "Healthcare"},
            {"ticker": "JPM", "shares": 18, "cost_basis": 180.0, "sector": "Financial Services"},
            {"ticker": "XOM", "shares": 22, "cost_basis": 118.0, "sector": "Energy"},
            {"ticker": "GLD", "shares": 15, "cost_basis": 195.0, "sector": "Commodities"},
        ],
        "cash": 5000.0, "currency": "USD",
    }


if __name__ == "__main__":
    print(json.dumps(sample_portfolio(), indent=2))
