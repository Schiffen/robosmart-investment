"""
portfolio.py — Person 1: turn an uploaded CSV into Contract A.
==============================================================
def parse_portfolio(uploaded_file) -> dict   # validated, enriched
def sample_portfolio() -> dict                # demo book for the "Try demo" button
Raises PortfolioError(message) with a human-readable message on bad input.
"""

from __future__ import annotations

import json
import os

import pandas as pd

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
    try:
        import yfinance as yf
        s = (yf.Ticker(ticker).get_info() or {}).get("sector")
        if s:
            return s
    except Exception:  # noqa: BLE001 — offline / bad ticker -> fallback
        pass
    return _SECTOR_FALLBACK.get(ticker.upper(), "Unknown")


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
    missing = {"ticker", "shares", "cost_basis"} - set(df.columns)
    if missing:
        raise PortfolioError(
            "Missing column(s): " + ", ".join(sorted(missing))
            + ". The CSV needs: ticker, shares, cost_basis.")

    cash = 0.0
    positions: dict[str, dict] = {}
    for _, row in df.iterrows():
        tk = str(row.get("ticker", "")).strip().upper()
        if not tk or tk == "NAN":
            continue
        if tk in ("CASH", "$CASH"):
            try:
                cash += float(row["shares"]) if pd.notna(row["shares"]) else 0.0
            except Exception:  # noqa: BLE001
                pass
            continue
        try:
            shares = float(row["shares"])
            cost = float(row["cost_basis"])
        except Exception:
            raise PortfolioError(f"Non-numeric shares/cost_basis for ticker {tk}.")
        if shares <= 0 or cost < 0:
            raise PortfolioError(f"Shares must be > 0 and cost_basis >= 0 (ticker {tk}).")

        sector = None
        if "sector" in df.columns and pd.notna(row.get("sector")):
            sector = str(row["sector"]).strip()
        sector = sector or _lookup_sector(tk)

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
        raise PortfolioError("No valid positions found in the file.")
    return {"positions": list(positions.values()), "cash": float(cash),
            "currency": "USD"}


def sample_portfolio() -> dict:
    """The demo book (loads mock_portfolio.json; falls back to an inline copy)."""
    p = os.path.join(os.path.dirname(__file__), "mock_portfolio.json")
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
