"""
app.py — RoboSmart Investment (Person 1: shell + wiring).
========================================================
No business logic here — this only wires the sidebar, session state, and the
three tabs together. Each tab is one function from another module.

Modes (see run_mode.py): USE_MOCK=1 runs the whole app offline — recorded market
data AND recorded AI output, no network and no API key. USE_MOCK_DATA /
USE_MOCK_LLM pin one axis without the other.
"""

import os

from dotenv import load_dotenv
import streamlit as st

import data_layer
import profiles
import run_mode
from portfolio import PortfolioError, parse_portfolio

# The book the app opens on. Balanced rather than alarming: the first thing a
# visitor sees should be the tool working, not a wall of red warnings.
DEFAULT_PROFILE = "balanced_growth"

# Local dev: read .env so ANTHROPIC_API_KEY / ANTHROPIC_MODEL / USE_MOCK are
# picked up without needing to `export` them. No-op where the host injects real
# env vars. Runs before any module reads os.environ.
load_dotenv()

# Config keys this app understands, in the one place they are enumerated.
_CONFIG_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                "USE_MOCK", "USE_MOCK_DATA", "USE_MOCK_LLM")


def _adopt_streamlit_secrets() -> None:
    """Copy Streamlit-managed secrets into the environment.

    Streamlit Community Cloud exposes secrets through `st.secrets` and does NOT
    set them as environment variables. Both `run_mode` and `agents/llm` read
    `os.environ`, so without this the deployed app would find no API key and
    quietly serve RECORDED debate output while looking completely healthy — the
    worst kind of failure, because nothing errors.

    An existing environment variable always wins, so a local `.env` still
    overrides the deployed configuration.
    """
    try:
        secrets = st.secrets
    except Exception:  # noqa: BLE001 — no secrets configured; normal locally
        return
    for key in _CONFIG_KEYS:
        try:
            if key in secrets and not os.environ.get(key):
                os.environ[key] = str(secrets[key])
        except Exception:  # noqa: BLE001 — malformed entry must not kill boot
            continue


# MUST run before anything reads os.environ — the auto-load gate below and every
# tab import resolve their mode from it.
_adopt_streamlit_secrets()

st.set_page_config(page_title="RoboSmart Investment", layout="wide", page_icon="📈")

ss = st.session_state
ss.setdefault("portfolio", None)
ss.setdefault("active_ticker", None)


def _load(portfolio: dict) -> None:
    ss.portfolio = portfolio
    tickers = [p["ticker"] for p in portfolio.get("positions", [])]
    ss.active_ticker = tickers[0] if tickers else None


# Land on a populated dashboard rather than an empty one. Previously this only
# happened on recorded data, so anyone opening the DEPLOYED app saw an upload
# prompt and an empty tab — a poor first five seconds for a tool whose whole
# point is what it computes. Reset still clears it.
# MUST run before the sidebar: the holdings summary, the active-ticker selectbox
# and Reset are all gated on `ss.portfolio` being set, so loading afterwards left
# the first paint with a full dashboard and no way to switch ticker.
if ss.portfolio is None and not ss.get("cleared"):
    _load(profiles.load_portfolio(DEFAULT_PROFILE))
    ss.loaded_profile = DEFAULT_PROFILE


# ---- Sidebar -------------------------------------------------------------
with st.sidebar:
    st.title("📈 RoboSmart")
    st.caption("Explore a sample investor, or upload your own portfolio.")

    # ---- Sample investor books ------------------------------------------
    # One engine, five different verdicts. Each profile states what it should
    # demonstrate, and tests/test_profiles.py enforces that claim against the
    # numbers, so these captions cannot drift into being wrong.
    catalogue = profiles.list_profiles()
    by_label = {profiles.label(p): p for p in catalogue}
    picked = st.selectbox("Sample investor", list(by_label),
                          index=list(by_label).index(
                              profiles.label(next(p for p in catalogue
                                                  if p["id"] == DEFAULT_PROFILE))))
    chosen = by_label[picked]
    st.caption(chosen["tagline"])
    if st.button("Load this investor", use_container_width=True, type="primary"):
        _load(profiles.load_portfolio(chosen["id"]))
        ss.pop("cleared", None)
        ss.loaded_profile = chosen["id"]
        st.rerun()

    with st.expander("Upload your own CSV"):
        st.caption("Columns: ticker, shares, cost_basis · optional sector · a CASH row sets cash.")
        up = st.file_uploader("Portfolio CSV", type=["csv"], label_visibility="collapsed")
        if up is not None:
            try:
                _load(parse_portfolio(up))
                ss.pop("cleared", None)
                ss.pop("loaded_profile", None)
                st.success("Portfolio loaded.")
            except PortfolioError as e:
                st.error(str(e))

    if ss.portfolio:
        st.divider()
        positions = ss.portfolio.get("positions", [])
        st.write(f"**{len(positions)} holdings** · cash "
                 f"${ss.portfolio.get('cash', 0):,.0f}")
        tickers = [p["ticker"] for p in positions]
        if tickers:
            idx = tickers.index(ss.active_ticker) if ss.active_ticker in tickers else 0
            ss.active_ticker = st.selectbox("Active ticker (tabs 2 & 3)", tickers, index=idx)
        if st.button("Clear"):
            ss.portfolio = None
            ss.active_ticker = None
            ss.pop("loaded_profile", None)
            # Sticky, or the auto-load above would immediately repopulate and
            # "Clear" would look like it did nothing.
            ss.cleared = True
            st.rerun()

    # State the resolved mode explicitly. Recorded data that looks live is the
    # failure this whole layer exists to prevent, so the snapshot date is named.
    mode_line = run_mode.summary_line()
    if mode_line:
        st.caption(mode_line)

# ---- Header --------------------------------------------------------------
st.title("RoboSmart Investment")
st.caption("Upload a stock portfolio and get an AI-assisted analysis across three tools.")

# When a sample investor is loaded, say what it is meant to demonstrate. The
# point of five books is that one engine reaches five different verdicts — and
# that only lands if the reader knows what to look for. `expect` is enforced
# against the real numbers by tests/test_profiles.py, so this is a checked claim
# rather than marketing copy.
if ss.get("loaded_profile"):
    _meta = next((p for p in profiles.list_profiles()
                  if p["id"] == ss.loaded_profile), None)
    if _meta:
        st.info(f"**{profiles.label(_meta)}** — {_meta['expect']}")

from tabs.attribution import render as render_attribution
from tabs.dashboard import render as render_dashboard
from tabs.debate import render as render_debate

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "⚔️ Bull vs Bear", "🔍 What Happened Today"])


def _active_context():
    if not ss.active_ticker:
        return None
    try:
        return data_layer.get_context(ss.active_ticker)
    except Exception as e:  # noqa: BLE001
        st.error(f"Couldn't load market data for {ss.active_ticker}: {e}")
        return None


with tab1:
    try:
        render_dashboard(ss.portfolio)
    except Exception as e:  # noqa: BLE001 — one broken tab never kills the app
        st.error(f"Dashboard unavailable: {e}")

with tab2:
    if not ss.portfolio:
        st.info("⚔️ Load a portfolio and pick a ticker to start a Bull vs Bear debate.")
    else:
        try:
            render_debate(_active_context())
        except Exception as e:  # noqa: BLE001
            st.error(f"Debate unavailable: {e}")

with tab3:
    if not ss.portfolio:
        st.info("🔍 Load a portfolio and pick a ticker to break down its move.")
    else:
        try:
            render_attribution(_active_context())
        except Exception as e:  # noqa: BLE001
            st.error(f"Attribution unavailable: {e}")

st.divider()
st.caption("RoboSmart is an educational university project. **This is not investment advice.**")
