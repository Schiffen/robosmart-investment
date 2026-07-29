"""
app.py — RoboSmart Investment (Person 1: shell + wiring).
========================================================
No business logic here — this only wires the sidebar, session state, and the
three tabs together. Each tab is one function from another module.

Modes (see run_mode.py): USE_MOCK=1 runs the whole app offline — recorded market
data AND recorded AI output, no network and no API key. USE_MOCK_DATA /
USE_MOCK_LLM pin one axis without the other.
"""

from dotenv import load_dotenv
import streamlit as st

import data_layer
import run_mode
from portfolio import PortfolioError, parse_portfolio, sample_portfolio

# Local dev: read .env so ANTHROPIC_API_KEY / ANTHROPIC_MODEL / USE_MOCK are
# picked up without needing to `export` them. No-op on Hugging Face, where the
# Space injects secrets as real env vars. Runs before any module reads os.environ.
load_dotenv()

st.set_page_config(page_title="RoboSmart Investment", layout="wide", page_icon="📈")

ss = st.session_state
ss.setdefault("portfolio", None)
ss.setdefault("active_ticker", None)


def _load(portfolio: dict) -> None:
    ss.portfolio = portfolio
    tickers = [p["ticker"] for p in portfolio.get("positions", [])]
    ss.active_ticker = tickers[0] if tickers else None


# Auto-load the demo when running on recorded data, so the app is never empty on
# a fresh boot. MUST run before the sidebar: the holdings summary, the
# active-ticker selectbox and Reset are all gated on `ss.portfolio` being set, so
# loading afterwards left the first paint with a full dashboard and no way to
# switch ticker.
if ss.portfolio is None and run_mode.use_fixture_data():
    _load(sample_portfolio())


# ---- Sidebar -------------------------------------------------------------
with st.sidebar:
    st.title("📈 RoboSmart")
    st.caption("Upload your portfolio (CSV) or load the demo.")

    up = st.file_uploader("Portfolio CSV", type=["csv"])
    if up is not None:
        try:
            _load(parse_portfolio(up))
            st.success("Portfolio loaded.")
        except PortfolioError as e:
            st.error(str(e))

    if st.button("Try demo portfolio"):
        _load(sample_portfolio())

    if ss.portfolio:
        st.divider()
        positions = ss.portfolio.get("positions", [])
        st.write(f"**{len(positions)} holdings** · cash "
                 f"${ss.portfolio.get('cash', 0):,.0f}")
        tickers = [p["ticker"] for p in positions]
        if tickers:
            idx = tickers.index(ss.active_ticker) if ss.active_ticker in tickers else 0
            ss.active_ticker = st.selectbox("Active ticker (tabs 2 & 3)", tickers, index=idx)
        if st.button("Reset"):
            ss.portfolio = None
            ss.active_ticker = None
            st.rerun()

    # State the resolved mode explicitly. Recorded data that looks live is the
    # failure this whole layer exists to prevent, so the snapshot date is named.
    mode_line = run_mode.summary_line()
    if mode_line:
        st.caption(mode_line)

# ---- Header --------------------------------------------------------------
st.title("RoboSmart Investment")
st.caption("Upload a stock portfolio and get an AI-assisted analysis across three tools.")

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
