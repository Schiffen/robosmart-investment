"""Every sample profile must actually demonstrate what it claims to demonstrate.

Each `profiles/*.json` carries a human sentence (`expect`) shown in the UI and a
machine-checkable `asserts` block. These tests enforce the second so the first
cannot quietly become false — which already happened once: "diversified global"
claimed the lowest correlation while actually having the HIGHEST, because three
of its six sleeves are equity funds.

A demo whose captions contradict its own numbers is worse than no demo.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_layer
import portfolio_metrics as pm
import profiles

ALL_IDS = profiles.available_ids()


@pytest.fixture(scope="module")
def spy():
    return data_layer.get_benchmark_history("SPY")


def _analyse(profile_id, spy_history):
    portfolio = profiles.load_portfolio(profile_id)
    tickers = [p["ticker"] for p in portfolio["positions"]]
    contexts = data_layer.get_context_batch(tickers)
    assert set(contexts) == set(tickers), (
        f"{profile_id}: offline fixture is missing "
        f"{sorted(set(tickers) - set(contexts))} — re-run market_data.refresh")

    df = pm.position_values(portfolio, contexts)
    weights = {r.ticker: r.weight_pct / 100.0
               for r in df.itertuples() if np.isfinite(r.weight_pct)}
    sectors = pm.sector_breakdown(df, portfolio)
    return {
        "portfolio": portfolio,
        "df": df,
        "sectors": sectors,
        "flags": pm.concentration_flags(df, sectors),
        "market": pm.market_model(contexts, weights, spy_history),
        "risk": pm.risk_metrics(contexts, weights, spy_history),
        "diversification": pm.diversification_score(weights),
    }


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------

def test_profiles_exist():
    assert len(ALL_IDS) >= 5
    assert "balanced_growth" in ALL_IDS


@pytest.mark.parametrize("pid", ALL_IDS)
def test_profile_metadata_is_complete(pid):
    meta = next(p for p in profiles.list_profiles() if p["id"] == pid)
    for field in ("name", "emoji", "tagline", "expect"):
        assert meta[field].strip(), f"{pid} has no {field}"
    assert profiles.label(meta).strip()


@pytest.mark.parametrize("pid", ALL_IDS)
def test_profile_is_valid_contract_a(pid):
    portfolio = profiles.load_portfolio(pid)
    assert set(portfolio) >= {"positions", "cash", "currency"}
    assert portfolio["cash"] >= 0
    for pos in portfolio["positions"]:
        assert set(pos) >= {"ticker", "shares", "cost_basis", "sector"}
        assert pos["shares"] > 0, f"{pid}/{pos['ticker']}: non-positive shares"
        assert pos["cost_basis"] > 0, f"{pid}/{pos['ticker']}: non-positive cost basis"
        # ETFs come back as sector "Unknown" from yfinance, so profiles must name
        # them explicitly or the sector donut collapses into one grey slice.
        assert pos["sector"] and pos["sector"] != "Unknown", \
            f"{pid}/{pos['ticker']}: sector must be stated explicitly"


def test_balanced_growth_mirrors_the_test_fixture():
    """profiles/balanced_growth.json and mock_portfolio.json must not drift —
    the tests use one and the UI shows the other."""
    import json
    with open(os.path.join(os.path.dirname(profiles.PROFILE_DIR),
                           "mock_portfolio.json")) as fh:
        fixture = json.load(fh)
    assert profiles.load_portfolio("balanced_growth") == fixture


def test_every_profile_ticker_is_in_the_offline_fixture():
    """profiles.all_tickers() drives market_data.refresh, so this failing means
    the fixture needs re-recording — offline mode would silently drop holdings."""
    from market_data import fixture
    missing = sorted(set(profiles.all_tickers()) - set(fixture.available_tickers()))
    assert not missing, f"not recorded: {missing} — run `python -m market_data.refresh`"


# --------------------------------------------------------------------------
# The claims themselves
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pid", ALL_IDS)
def test_profile_demonstrates_what_it_claims(pid, spy):
    import json
    doc = json.load(open(os.path.join(profiles.PROFILE_DIR, f"{pid}.json")))
    rules = doc.get("asserts") or {}
    if not rules:
        pytest.skip(f"{pid} declares no asserts")

    a = _analyse(pid, spy)
    flags, beta = a["flags"], a["market"]["beta"]
    vol, eff = a["risk"]["port_vol"], a["diversification"]["effective_n"]

    if "warnings_exactly" in rules:
        assert len(flags) == rules["warnings_exactly"], \
            f"{pid}: expected {rules['warnings_exactly']} warnings, got {len(flags)}: {flags}"
    if "warnings_min" in rules:
        assert len(flags) >= rules["warnings_min"]
    if "warning_contains" in rules:
        assert any(rules["warning_contains"] in f for f in flags)
    if "beta_max" in rules:
        assert beta <= rules["beta_max"], f"{pid}: beta {beta:.2f} > {rules['beta_max']}"
    if "beta_min" in rules:
        assert beta >= rules["beta_min"], f"{pid}: beta {beta:.2f} < {rules['beta_min']}"
    if "vol_max" in rules:
        assert vol <= rules["vol_max"], f"{pid}: vol {vol:.3f} > {rules['vol_max']}"
    if "vol_min" in rules:
        assert vol >= rules["vol_min"], f"{pid}: vol {vol:.3f} < {rules['vol_min']}"
    if "effective_n_max" in rules:
        assert eff <= rules["effective_n_max"], \
            f"{pid}: effective holdings {eff:.1f} > {rules['effective_n_max']}"
    if "min_sectors" in rules:
        n = len(a["sectors"])
        assert n >= rules["min_sectors"], f"{pid}: {n} sectors < {rules['min_sectors']}"


def test_the_profiles_actually_disagree_with_each_other(spy):
    """The whole point: one engine, five different verdicts.

    If every profile produced the same warnings and a similar beta, the set would
    be decoration rather than demonstration.
    """
    results = {pid: _analyse(pid, spy) for pid in ALL_IDS}
    warning_counts = {p: len(r["flags"]) for p, r in results.items()}
    betas = {p: r["market"]["beta"] for p, r in results.items()}
    vols = {p: r["risk"]["port_vol"] for p, r in results.items()}

    assert min(warning_counts.values()) == 0, "no profile is clean"
    assert max(warning_counts.values()) >= 3, "no profile is alarming"
    assert max(betas.values()) - min(betas.values()) > 1.0, \
        f"betas are too similar to be instructive: {betas}"
    assert max(vols.values()) / min(vols.values()) > 2.0, \
        f"volatilities are too similar: {vols}"
