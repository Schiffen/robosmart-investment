"""Contract A — the CSV boundary, which had no test at all until now.

`parse_portfolio` is the oldest producer of Contract A and was the only contract
boundary in this repo with zero coverage. Every rule lived inline in one
`df.iterrows()` loop, so there was nothing to refactor against.

These are CHARACTERISATION tests: they pin the behaviour that exists so the
validator can be lifted out of that loop and shared with the in-app builder
without changing what a CSV means. Written before the extraction, deliberately.

Two of them were written RED, against defects found by running the parser rather
than by reading it:

  * `AAPL,,150.00` produced `shares: NaN`, because the guard is `shares <= 0`
    and `nan <= 0` is False. A NaN-share position entered Contract A and
    `position_values` then redistributed weights around it, silently.
  * The CSV example the sidebar PRINTS parsed to $1 of cash while the template
    it offers for DOWNLOAD parsed to $5,000 — cash reads from the `shares`
    column, so `CASH,1,5000` means one dollar.

OFFLINE NOTE. `portfolio._lookup_sector` calls `yf.Ticker().get_info()` directly
and does NOT go through `data_layer`, so conftest's `USE_MOCK_DATA=1` does not
reach it. Any test whose CSV omits `sector` would hit the network. It is stubbed
here rather than left to chance — which is also the reason step 1 makes the
sector resolver injectable.
"""

import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import portfolio as pf
from portfolio import PortfolioError, parse_portfolio

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_network_sector_lookup(monkeypatch):
    """Never let a sector lookup reach Yahoo from a unit test."""
    monkeypatch.setattr(pf, "_lookup_sector", lambda t: "Stubbed")


def csv(text: str):
    return io.StringIO(text)


HEADER = "ticker,shares,cost_basis\n"


# --------------------------------------------------------------------------
# The shape of Contract A
# --------------------------------------------------------------------------

def test_returns_contract_a_exactly():
    book = parse_portfolio(csv(HEADER + "AAPL,10,150.00\n"))
    assert set(book) == {"positions", "cash", "currency"}
    assert book["currency"] == "USD"
    assert book["cash"] == 0.0
    assert [set(p) for p in book["positions"]] == [
        {"ticker", "shares", "cost_basis", "sector"}]


def test_ticker_is_uppercased_and_stripped():
    book = parse_portfolio(csv(HEADER + "  aapl ,10,150\n"))
    assert book["positions"][0]["ticker"] == "AAPL"


def test_shares_and_cost_are_floats():
    p = parse_portfolio(csv(HEADER + "AAPL,10,150\n"))["positions"][0]
    assert isinstance(p["shares"], float) and isinstance(p["cost_basis"], float)


def test_position_order_follows_first_appearance():
    book = parse_portfolio(csv(HEADER + "MSFT,5,310\nAAPL,10,150\nMSFT,5,320\n"))
    assert [p["ticker"] for p in book["positions"]] == ["MSFT", "AAPL"]


# --------------------------------------------------------------------------
# The four error messages, pinned verbatim
# --------------------------------------------------------------------------

def test_unreadable_file_is_a_portfolio_error():
    with pytest.raises(PortfolioError, match="Couldn't read the CSV file"):
        parse_portfolio("does-not-exist-anywhere.csv")


def test_empty_file_is_named_as_empty():
    with pytest.raises(PortfolioError, match="The uploaded file is empty."):
        parse_portfolio(csv("ticker,shares,cost_basis\n"))


def test_missing_columns_are_named():
    with pytest.raises(PortfolioError) as e:
        parse_portfolio(csv("ticker,quantity\nAAPL,10\n"))
    msg = str(e.value)
    assert "cost_basis" in msg and "shares" in msg
    assert "The CSV needs: ticker, shares, cost_basis." in msg


def test_non_numeric_cell_names_the_ticker():
    with pytest.raises(PortfolioError, match="Non-numeric shares/cost_basis for ticker AAPL."):
        parse_portfolio(csv(HEADER + "AAPL,ten,150\n"))


@pytest.mark.parametrize("row", ["AAPL,0,150", "AAPL,-5,150", "AAPL,10,-1"])
def test_non_positive_shares_or_negative_cost_are_rejected(row):
    with pytest.raises(PortfolioError, match=r"Shares must be > 0 and cost_basis >= 0"):
        parse_portfolio(csv(HEADER + row + "\n"))


def test_a_file_with_no_usable_rows_says_so():
    with pytest.raises(PortfolioError, match="No valid positions found in the file."):
        parse_portfolio(csv(HEADER + ",,\n"))


# --------------------------------------------------------------------------
# Rows that are skipped rather than rejected
# --------------------------------------------------------------------------

def test_blank_and_nan_tickers_are_skipped_not_errors():
    book = parse_portfolio(csv(HEADER + ",5,10\nAAPL,10,150\n"))
    assert [p["ticker"] for p in book["positions"]] == ["AAPL"]


# --------------------------------------------------------------------------
# Cash — read from the SHARES column, which is the whole trap
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tk", ["CASH", "$CASH", "cash"])
def test_cash_row_reads_the_shares_column(tk):
    book = parse_portfolio(csv(HEADER + "AAPL,10,150\n" + f"{tk},5000,0\n"))
    assert book["cash"] == 5000.0
    assert [p["ticker"] for p in book["positions"]] == ["AAPL"]


def test_multiple_cash_rows_accumulate():
    book = parse_portfolio(csv(HEADER + "AAPL,10,150\nCASH,1000,0\nCASH,250,0\n"))
    assert book["cash"] == 1250.0


def test_a_non_numeric_cash_amount_is_swallowed_not_raised():
    # Deliberately unlike every other numeric failure: the CASH branch catches.
    book = parse_portfolio(csv(HEADER + "AAPL,10,150\nCASH,lots,0\n"))
    assert book["cash"] == 0.0


def test_no_cash_row_means_zero():
    assert parse_portfolio(csv(HEADER + "AAPL,10,150\n"))["cash"] == 0.0


# --------------------------------------------------------------------------
# Sector
# --------------------------------------------------------------------------

def test_sector_column_wins_over_lookup():
    book = parse_portfolio(csv("ticker,shares,cost_basis,sector\n"
                               "AAPL,10,150,Widgets\n"))
    assert book["positions"][0]["sector"] == "Widgets"


def test_missing_sector_falls_through_to_the_resolver():
    assert parse_portfolio(csv(HEADER + "AAPL,10,150\n"))["positions"][0]["sector"] == "Stubbed"


def test_a_blank_sector_cell_falls_through_to_the_resolver():
    book = parse_portfolio(csv("ticker,shares,cost_basis,sector\nAAPL,10,150,\n"))
    assert book["positions"][0]["sector"] == "Stubbed"


# --------------------------------------------------------------------------
# Duplicate merging — weighted-average cost basis
# --------------------------------------------------------------------------

def test_duplicates_merge_to_a_weighted_average_cost_basis():
    book = parse_portfolio(csv(HEADER + "AAPL,10,100\nAAPL,30,200\n"))
    assert len(book["positions"]) == 1
    p = book["positions"][0]
    assert p["shares"] == 40.0
    assert p["cost_basis"] == pytest.approx((100 * 10 + 200 * 30) / 40)  # 175


def test_the_merged_row_keeps_the_first_rows_sector():
    book = parse_portfolio(csv("ticker,shares,cost_basis,sector\n"
                               "AAPL,10,100,First\nAAPL,10,200,Second\n"))
    assert book["positions"][0]["sector"] == "First"


# --------------------------------------------------------------------------
# The shipped template
# --------------------------------------------------------------------------

def test_the_downloadable_template_parses():
    book = parse_portfolio(os.path.join(REPO, "fixtures", "sample_portfolio.csv"))
    assert book["cash"] == 5000.0
    assert len(book["positions"]) == 7
    assert {p["ticker"] for p in book["positions"]} == {
        "NVDA", "MSFT", "AAPL", "JNJ", "JPM", "XOM", "GLD"}


# --------------------------------------------------------------------------
# Written RED — these two fail against the parser as it stands
# --------------------------------------------------------------------------

def test_a_blank_shares_cell_never_reaches_contract_a():
    """`nan <= 0` is False, so the guard let a NaN-share position straight through.

    It is not a cosmetic defect: every weight in the app is a share of a total,
    and one NaN in that column silently redistributes every other holding's
    weight rather than failing.
    """
    with pytest.raises(PortfolioError):
        parse_portfolio(csv(HEADER + "AAPL,,150.00\n"))


def test_a_blank_cost_cell_never_reaches_contract_a():
    with pytest.raises(PortfolioError):
        parse_portfolio(csv(HEADER + "AAPL,10,\n"))


def test_the_documented_csv_example_parses_to_what_it_claims():
    """The example the sidebar PRINTS must mean what the template DOWNLOADS.

    `st.code(...)` in app.py showed `CASH,1,5000`, which parses to one dollar,
    while `sample_portfolio.csv` correctly says `CASH,5000,0`. A user who copied
    the example the app displayed lost their cash balance with no error at all.
    """
    src = open(os.path.join(REPO, "app.py")).read()
    m = re.search(r'st\.code\(\s*"((?:[^"\\]|\\.)*)"', src)
    assert m, "could not find the CSV example in app.py — has st.code moved?"
    example = m.group(1).encode().decode("unicode_escape")

    assert "ticker,shares,cost_basis" in example, example
    book = parse_portfolio(csv(example + "\n"))
    assert book["cash"] == 5000.0, (
        f"the on-screen example parses to cash={book['cash']}, but it is meant "
        f"to demonstrate a $5,000 cash balance. Cash reads from the SHARES "
        f"column.\n{example}")
