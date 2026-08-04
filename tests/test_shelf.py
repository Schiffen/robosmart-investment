"""The curated shelf must agree with the rest of the app, not compete with it.

Three failure modes these guard, all of which would be silent:

  * A shelf entry with no recorded market data. The generator would draft a book
    containing it and the whole app would then fail to price a holding, offline.
  * A shelf `sector` that disagrees with the string `profiles/*.json` already
    store for the same ticker. Two sources of truth for a sector means the
    dashboard's donut and a generated book can label the same holding
    differently — which is exactly the class of bug the single-benchmark rule in
    INTEGRATION_CONTRACT §3 exists to prevent.
  * A category picker that offers "Unknown". yfinance returns `sector ==
    "Unknown"` for every fund on this shelf, so `category` has to be
    hand-authored and complete.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import profiles
import shelf
from market_data import fixture, refresh


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------

def test_the_shelf_is_not_trivially_small():
    assert len(shelf.tickers()) >= 40


def test_every_entry_is_complete():
    required = {"name", "kind", "role", "category", "sector", "note"}
    for tk, meta in shelf.SHELF.items():
        assert set(meta) == required, f"{tk}: {set(meta) ^ required}"
        for k, v in meta.items():
            assert isinstance(v, str) and v.strip(), f"{tk}.{k} is empty"


def test_kinds_and_roles_are_from_the_declared_sets():
    for tk, meta in shelf.SHELF.items():
        assert meta["kind"] in ("stock", "fund"), tk
        assert meta["role"] in shelf.ROLES, tk


def test_tickers_are_uppercase_and_unique():
    ts = shelf.tickers()
    assert len(ts) == len(set(ts))
    assert all(t == t.upper().strip() for t in ts)


# --------------------------------------------------------------------------
# Categories — the axis yfinance cannot supply
# --------------------------------------------------------------------------

def test_every_category_is_declared_and_populated():
    used = {m["category"] for m in shelf.SHELF.values()}
    assert used <= set(shelf.CATEGORIES), f"undeclared: {used - set(shelf.CATEGORIES)}"
    empty = [c for c, ts in shelf.by_category().items() if not ts]
    assert not empty, f"categories with no tickers: {empty}"


def test_no_category_is_unknown():
    """The whole reason `category` exists rather than reusing yfinance's sector."""
    assert "Unknown" not in shelf.CATEGORIES
    assert all(m["category"] != "Unknown" for m in shelf.SHELF.values())


def test_by_category_covers_every_ticker_exactly_once():
    flat = [t for ts in shelf.by_category().values() for t in ts]
    assert sorted(flat) == sorted(shelf.tickers())


def test_the_defensive_roles_are_actually_available():
    """A short horizon needs somewhere to put the money that is not equity."""
    defensive = [t for t in shelf.tickers() if shelf.role_of(t) in shelf.DEFENSIVE_ROLES]
    assert len(defensive) >= 5


def test_in_categories_filters_and_defaults_to_everything():
    assert shelf.in_categories(None) == shelf.tickers()
    assert shelf.in_categories([]) == shelf.tickers()
    bonds = shelf.in_categories(["Bonds"])
    assert bonds and all(shelf.category_of(t) == "Bonds" for t in bonds)


# --------------------------------------------------------------------------
# Agreement with what the app already believes
# --------------------------------------------------------------------------

def test_the_shelf_covers_every_profile_ticker():
    missing = set(profiles.all_tickers()) - set(shelf.tickers())
    assert not missing, (
        f"{sorted(missing)} are held by a sample profile but are not on the "
        f"shelf, so the builder could not reproduce a shipped book")


@pytest.mark.parametrize("profile_id", profiles.available_ids())
def test_shelf_sectors_match_the_sectors_profiles_already_store(profile_id):
    book = profiles.load_portfolio(profile_id)
    for p in book["positions"]:
        assert shelf.sector_of(p["ticker"]) == p["sector"], (
            f"{p['ticker']}: shelf says {shelf.sector_of(p['ticker'])!r}, "
            f"{profile_id}.json says {p['sector']!r} — one of them is wrong and "
            f"the dashboard would disagree with a generated book")


def test_single_stock_classification_is_sane():
    assert shelf.is_single_stock("NVDA")
    assert not shelf.is_single_stock("VTI")
    assert not shelf.is_single_stock("BND")
    assert not shelf.is_single_stock("NOT-A-TICKER")


def test_off_shelf_lookups_return_none_rather_than_guessing():
    assert shelf.sector_of("ZZZZ") is None
    assert shelf.category_of("ZZZZ") is None
    assert shelf.role_of("ZZZZ") is None


# --------------------------------------------------------------------------
# The refresh union
# --------------------------------------------------------------------------

def test_refresh_records_the_union_of_shelf_and_profiles():
    recorded = refresh.demo_book_tickers()
    assert set(recorded) >= set(shelf.tickers())
    assert set(recorded) >= set(profiles.all_tickers()), (
        "a profile ticker fell out of what refresh records — editing shelf.py "
        "must never be able to drop a shipped book's holding from the fixture")
    assert len(recorded) == len(set(recorded))


# --------------------------------------------------------------------------
# The fixture — fails until `python -m market_data.refresh` has been run
# --------------------------------------------------------------------------

def test_every_shelf_ticker_has_recorded_market_data():
    missing = sorted(set(shelf.tickers()) - set(fixture.available_tickers()))
    assert not missing, (
        f"{missing} are on the shelf but not in the offline fixture. The "
        f"generator could draft a book holding them and nothing could price it. "
        f"Run:  .venv/bin/python -m market_data.refresh")


def test_the_prompt_block_is_built_from_the_shelf():
    block = shelf.describe_for_prompt()
    assert block.count("\n") + 1 == len(shelf.tickers())
    assert "NVDA — NVIDIA (Technology, stock)" in block
    only_bonds = shelf.describe_for_prompt(shelf.in_categories(["Bonds"]))
    assert "NVDA" not in only_bonds and "BND" in only_bonds


def test_an_empty_allowed_list_offers_nothing_rather_than_everything():
    """`None` means "all of them"; an empty list means empty.

    The earlier signature did `if allowed else tickers()`, so a reader who
    excluded every category was shown the whole 41-name shelf by the prompt
    while the coercion step was about to drop every ticker the model picked.
    """
    assert shelf.describe_for_prompt([]) == ""
    assert shelf.describe_for_prompt(None) == shelf.describe_for_prompt()
