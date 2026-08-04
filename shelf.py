"""shelf.py — the curated universe a book can be built or drafted from.

WHY A SHELF EXISTS AT ALL
-------------------------
The in-app builder and the questionnaire-driven generator both need a fixed set
of tickers, for three reasons that happen to point the same way:

  * Every name here is in the recorded fixture, so a book assembled from the
    shelf can be priced with no network at all — the mode the deployed app and
    the whole test suite run in.
  * The generator is confined to it. That is what keeps "draft me a book" a
    demonstration rather than a stock recommendation: the shelf is fixed and the
    model only arranges it.
  * `category` gives the questionnaire something to offer that yfinance cannot.

WHY `category` AND `sector` ARE DIFFERENT FIELDS
------------------------------------------------
`live.py` resolves a sector ETF with `SECTOR_ETF.get(sector, "SPY")`, and
yfinance returns `sector == "Unknown"` for EVERY fund — measured: BND, GLD, TLT,
VNQ, VTI, VXUS, and equally SHY, LQD, HYG, SCHD, IWM, VWO. A picker built on
yfinance's sector would therefore offer beginners a bucket called "Unknown"
holding a third of the shelf. `category` is hand-authored and covers all 41.

`sector` here is NOT a second opinion. Every value for a ticker that appears in
`profiles/*.json` is the string that file already stores, and
`tests/test_shelf.py` pins that equality — so the shelf promotes knowledge the
repo already had rather than introducing a rival source that can drift from the
dashboard's own sector donut.

`kind` is separate from both, because the questionnaire's experience item caps
the SINGLE-STOCK share of a book, which is a stock-vs-fund question rather than
a sector one. `role` is what the equity band and the defensive floor check.

CHANGING THIS FILE CHANGES THE FIXTURE
--------------------------------------
`market_data.refresh.demo_book_tickers()` reads `tickers()`, so adding a name
here means re-recording:  .venv/bin/python -m market_data.refresh
`tests/test_shelf.py` fails until you do, rather than letting a shelf entry with
no market data reach the generator.
"""

from __future__ import annotations

# Display order for the questionnaire's picker, deliberately: the things a
# beginner names first, then the building blocks, then the ballast.
CATEGORIES = (
    "Technology",
    "Communication",
    "Healthcare",
    "Financials",
    "Consumer",
    "Industrials",
    "Utilities",
    "Materials",
    "Energy",
    "Real estate",
    "US broad index",
    "International",
    "Small cap",
    "Dividend income",
    "Bonds",
    "Gold",
)

# ticker -> {name, kind, role, category, sector, note}
#   kind      stock | fund
#   role      equity | bond | alternative      — what the bands check against
#   sector    the Contract A string; matches profiles/*.json where they overlap
#   note      one clause the generator may quote. Factual, never promotional.
SHELF: dict[str, dict] = {
    # ---- Technology ------------------------------------------------------
    "NVDA": {"name": "NVIDIA", "kind": "stock", "role": "equity",
             "category": "Technology", "sector": "Technology",
             "note": "designs the GPUs most AI training runs on"},
    "MSFT": {"name": "Microsoft", "kind": "stock", "role": "equity",
             "category": "Technology", "sector": "Technology",
             "note": "enterprise software and cloud, with a large dividend"},
    "AAPL": {"name": "Apple", "kind": "stock", "role": "equity",
             "category": "Technology", "sector": "Technology",
             "note": "consumer hardware with a growing services business"},
    "AVGO": {"name": "Broadcom", "kind": "stock", "role": "equity",
             "category": "Technology", "sector": "Technology",
             "note": "semiconductors and infrastructure software"},
    "AMD": {"name": "AMD", "kind": "stock", "role": "equity",
            "category": "Technology", "sector": "Technology",
            "note": "processors and accelerators; more volatile than its peers"},
    "PLTR": {"name": "Palantir", "kind": "stock", "role": "equity",
             "category": "Technology", "sector": "Technology",
             "note": "data platforms; a high-multiple, high-volatility name"},

    # ---- Communication ---------------------------------------------------
    "GOOGL": {"name": "Alphabet", "kind": "stock", "role": "equity",
              "category": "Communication", "sector": "Communication Services",
              "note": "search advertising, YouTube and cloud"},
    "META": {"name": "Meta Platforms", "kind": "stock", "role": "equity",
             "category": "Communication", "sector": "Communication Services",
             "note": "social advertising; earnings swing on ad pricing"},
    "VZ": {"name": "Verizon", "kind": "stock", "role": "equity",
           "category": "Communication", "sector": "Communication Services",
           "note": "telecoms; low growth, high dividend yield"},

    # ---- Healthcare ------------------------------------------------------
    "JNJ": {"name": "Johnson & Johnson", "kind": "stock", "role": "equity",
            "category": "Healthcare", "sector": "Healthcare",
            "note": "pharmaceuticals and medical devices; a defensive staple"},
    "UNH": {"name": "UnitedHealth", "kind": "stock", "role": "equity",
            "category": "Healthcare", "sector": "Healthcare",
            "note": "health insurance and care delivery"},
    "PFE": {"name": "Pfizer", "kind": "stock", "role": "equity",
            "category": "Healthcare", "sector": "Healthcare",
            "note": "pharmaceuticals; revenue tied to the patent cycle"},

    # ---- Financials ------------------------------------------------------
    "JPM": {"name": "JPMorgan Chase", "kind": "stock", "role": "equity",
            "category": "Financials", "sector": "Financial Services",
            "note": "the largest US bank; sensitive to interest rates"},
    "BRK-B": {"name": "Berkshire Hathaway", "kind": "stock", "role": "equity",
              "category": "Financials", "sector": "Financial Services",
              "note": "a diversified holding company, not a single business"},
    "V": {"name": "Visa", "kind": "stock", "role": "equity",
          "category": "Financials", "sector": "Financial Services",
          "note": "payment network; earns a fee on card volume"},

    # ---- Consumer --------------------------------------------------------
    "AMZN": {"name": "Amazon", "kind": "stock", "role": "equity",
             "category": "Consumer", "sector": "Consumer Cyclical",
             "note": "online retail plus AWS cloud"},
    "TSLA": {"name": "Tesla", "kind": "stock", "role": "equity",
             "category": "Consumer", "sector": "Consumer Cyclical",
             "note": "electric vehicles; among the most volatile large caps"},
    "MCD": {"name": "McDonald's", "kind": "stock", "role": "equity",
            "category": "Consumer", "sector": "Consumer Cyclical",
            "note": "franchised restaurants; steady cash generation"},
    "COST": {"name": "Costco", "kind": "stock", "role": "equity",
             "category": "Consumer", "sector": "Consumer Defensive",
             "note": "membership retail; defensive with a high multiple"},
    "PG": {"name": "Procter & Gamble", "kind": "stock", "role": "equity",
           "category": "Consumer", "sector": "Consumer Defensive",
           "note": "household brands; classic low-beta defensive"},
    "KO": {"name": "Coca-Cola", "kind": "stock", "role": "equity",
           "category": "Consumer", "sector": "Consumer Defensive",
           "note": "beverages; long dividend record, low growth"},

    # ---- Industrials -----------------------------------------------------
    "CAT": {"name": "Caterpillar", "kind": "stock", "role": "equity",
            "category": "Industrials", "sector": "Industrials",
            "note": "construction and mining equipment; cyclical"},
    "HON": {"name": "Honeywell", "kind": "stock", "role": "equity",
            "category": "Industrials", "sector": "Industrials",
            "note": "diversified industrial and aerospace"},

    # ---- Utilities -------------------------------------------------------
    "NEE": {"name": "NextEra Energy", "kind": "stock", "role": "equity",
            "category": "Utilities", "sector": "Utilities",
            "note": "regulated utility with a large renewables arm"},
    "DUK": {"name": "Duke Energy", "kind": "stock", "role": "equity",
            "category": "Utilities", "sector": "Utilities",
            "note": "regulated electricity; low beta, high yield"},

    # ---- Materials -------------------------------------------------------
    "LIN": {"name": "Linde", "kind": "stock", "role": "equity",
            "category": "Materials", "sector": "Basic Materials",
            "note": "industrial gases; steadier than most materials names"},

    # ---- Energy ----------------------------------------------------------
    "XOM": {"name": "Exxon Mobil", "kind": "stock", "role": "equity",
            "category": "Energy", "sector": "Energy",
            "note": "integrated oil and gas; moves with the crude price"},
    "CVX": {"name": "Chevron", "kind": "stock", "role": "equity",
            "category": "Energy", "sector": "Energy",
            "note": "integrated oil and gas with a long dividend record"},

    # ---- Real estate -----------------------------------------------------
    "VNQ": {"name": "US real estate ETF", "kind": "fund", "role": "equity",
            "category": "Real estate", "sector": "Real Estate",
            "note": "a basket of US property trusts"},
    "O": {"name": "Realty Income", "kind": "stock", "role": "equity",
          "category": "Real estate", "sector": "Real Estate",
          "note": "a property trust that pays monthly"},

    # ---- Broad index -----------------------------------------------------
    "VTI": {"name": "Total US market ETF", "kind": "fund", "role": "equity",
            "category": "US broad index", "sector": "US Equity",
            "note": "the whole US market in one holding"},

    # ---- International ---------------------------------------------------
    "VXUS": {"name": "Total international ETF", "kind": "fund", "role": "equity",
             "category": "International", "sector": "International Equity",
             "note": "developed and emerging markets outside the US"},
    "VWO": {"name": "Emerging markets ETF", "kind": "fund", "role": "equity",
            "category": "International", "sector": "International Equity",
            "note": "emerging markets only; more volatile than developed"},

    # ---- Small cap -------------------------------------------------------
    "IWM": {"name": "US small-cap ETF", "kind": "fund", "role": "equity",
            "category": "Small cap", "sector": "US Equity",
            "note": "smaller US companies; higher beta than the broad market"},

    # ---- Dividend income -------------------------------------------------
    "SCHD": {"name": "US dividend equity ETF", "kind": "fund", "role": "equity",
             "category": "Dividend income", "sector": "US Equity",
             "note": "screens the US market for durable dividend payers"},

    # ---- Bonds -----------------------------------------------------------
    "BND": {"name": "Total US bond ETF", "kind": "fund", "role": "bond",
            "category": "Bonds", "sector": "Fixed Income",
            "note": "the broad US investment-grade bond market"},
    "SHY": {"name": "1-3 year Treasury ETF", "kind": "fund", "role": "bond",
            "category": "Bonds", "sector": "Fixed Income",
            "note": "short government bonds; the least volatile thing here"},
    "TLT": {"name": "20+ year Treasury ETF", "kind": "fund", "role": "bond",
            "category": "Bonds", "sector": "Fixed Income",
            "note": "long government bonds; very sensitive to rate moves"},
    "LQD": {"name": "Investment-grade corporate ETF", "kind": "fund", "role": "bond",
            "category": "Bonds", "sector": "Fixed Income",
            "note": "corporate bonds rated investment grade"},
    "HYG": {"name": "High-yield corporate ETF", "kind": "fund", "role": "bond",
            "category": "Bonds", "sector": "Fixed Income",
            "note": "sub-investment-grade credit; behaves partly like equity"},

    # ---- Gold ------------------------------------------------------------
    "GLD": {"name": "Gold ETF", "kind": "fund", "role": "alternative",
            "category": "Gold", "sector": "Commodities",
            "note": "physical gold; usually uncorrelated with equities"},
}

ROLES = ("equity", "bond", "alternative")

# Roles that count toward the questionnaire's "defensive floor" — what a short
# horizon or a low loss limit requires the book to hold instead of equity.
DEFENSIVE_ROLES = ("bond", "alternative")


def tickers() -> list:
    """Every shelf symbol, in file order (category by category)."""
    return list(SHELF)


def entry(ticker: str) -> dict | None:
    return SHELF.get(str(ticker).strip().upper())


def sector_of(ticker: str) -> str | None:
    """The Contract A sector string, or None for anything off-shelf.

    Passed to `portfolio.build_portfolio(sector_for=...)` so the builder never
    calls `portfolio._lookup_sector`, which hits the network once per row.
    """
    e = entry(ticker)
    return e["sector"] if e else None


def category_of(ticker: str) -> str | None:
    e = entry(ticker)
    return e["category"] if e else None


def role_of(ticker: str) -> str | None:
    e = entry(ticker)
    return e["role"] if e else None


def is_single_stock(ticker: str) -> bool:
    e = entry(ticker)
    return bool(e and e["kind"] == "stock")


def categories() -> tuple:
    return CATEGORIES


def by_category() -> dict:
    """category -> [tickers], in CATEGORIES order. Drives the picker."""
    out = {c: [] for c in CATEGORIES}
    for tk, meta in SHELF.items():
        out.setdefault(meta["category"], []).append(tk)
    return out


def in_categories(allowed) -> list:
    """Every shelf ticker whose category is in `allowed`. Empty `allowed` means all."""
    if not allowed:
        return tickers()
    keep = set(allowed)
    return [t for t, m in SHELF.items() if m["category"] in keep]


def describe_for_prompt(allowed_tickers=None) -> str:
    """The shelf as the generator sees it — one line per ticker.

    Takes TICKERS, not categories, and `None` (not emptiness) is what means "all
    of them". The earlier signature took categories and did `if allowed else
    tickers()`, so an EMPTY allowed set — a reader who excluded every category —
    fell through to listing the whole shelf. The prompt then offered 41 names
    while the coercion step was about to drop every one of them.

    Built from SHELF rather than written out, so the prompt cannot drift from
    the universe the coercion step enforces.
    """
    lines = []
    for tk in (tickers() if allowed_tickers is None else
               [t for t in tickers() if t in set(allowed_tickers)]):
        m = SHELF[tk]
        lines.append(f"{tk} — {m['name']} ({m['category']}, {m['kind']}) — {m['note']}")
    return "\n".join(lines)
