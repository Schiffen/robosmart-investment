"""
app.py — RoboSmart Investment (shell + wiring).
===============================================
No business logic here — this only wires the sidebar, session state, and the
three views together. Each view is one function from another module.

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
import theme
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
# view import resolve their mode from it.
_adopt_streamlit_secrets()

st.set_page_config(page_title="RoboSmart Investment", layout="wide", page_icon="📈")
theme.inject_css()

ss = st.session_state
ss.setdefault("portfolio", None)
ss.setdefault("active_ticker", None)
ss.setdefault("view", "Dashboard")


def _load(portfolio: dict, *, profile_id: str | None = None) -> None:
    ss.portfolio = portfolio
    tickers = [p["ticker"] for p in portfolio.get("positions", [])]
    ss.active_ticker = tickers[0] if tickers else None
    ss.loaded_profile = profile_id          # None means "user's own CSV"


# Land on a populated dashboard rather than an empty one. The deployed app used
# to open on an upload prompt and an empty tab — a poor first five seconds for a
# tool whose whole point is what it computes.
if ss.portfolio is None:
    _load(profiles.load_portfolio(DEFAULT_PROFILE), profile_id=DEFAULT_PROFILE)


def _as_of(context: dict | None) -> str | None:
    """The date of the last SETTLED close actually being shown.

    Everything in this app is close-to-close (INTEGRATION_CONTRACT §3), so on a
    Monday morning the "current" price is Friday's. The interface said nothing
    about this at all: run_mode.summary_line() returns None when both axes are
    live, so the DEPLOYED app — the only one a grader sees — carried no
    freshness signal whatsoever. Principle 4 says recorded data must never look
    live; the same reasoning says stale data must never look fresh.
    """
    if not context:
        return None
    history = context.get("history")
    try:
        if history is not None and len(history) > 0:
            return history.index[-1].strftime("%-d %b %Y")
    except Exception:  # noqa: BLE001 — a missing index never blocks the page
        return None
    return None


# ---- Sidebar -------------------------------------------------------------
with st.sidebar:
    # Not st.title(): that emits a second <h1>, and a page has one. The main
    # heading is the document's h1; this is a masthead, so it is styled as one
    # rather than claiming heading semantics it does not have.
    st.markdown(
        "<div style='font-size:1.35rem;font-weight:700;letter-spacing:-.015em;"
        "margin:.2rem 0 1rem'>📈 RoboSmart</div>",
        unsafe_allow_html=True,
    )

    # ---- Sample investor books ------------------------------------------
    # One engine, five different verdicts. Each profile states what it should
    # demonstrate, and tests/test_profiles.py enforces that claim against the
    # numbers, so these captions cannot drift into being wrong.
    #
    # This used to be a dropdown showing emoji + name only, followed by a
    # separate "Load this investor" button. You could not see what you were
    # choosing between at the moment of choosing — which defeats the entire
    # point of shipping five books — and selecting without pressing Load left
    # the sidebar describing one book while the main banner described another.
    catalogue = profiles.list_profiles()
    ids = [p["id"] for p in catalogue]
    meta_by_id = {p["id"]: p for p in catalogue}

    # Tracked separately from `loaded_profile`, which is None while the user's
    # OWN uploaded CSV is loaded. Comparing the radio against `loaded_profile`
    # would make it differ on the very next rerun and silently reload the sample
    # book over the user's portfolio.
    ss.setdefault("last_profile_pick", DEFAULT_PROFILE)

    picked = st.radio(
        "Sample investor",
        ids,
        index=ids.index(ss.last_profile_pick) if ss.last_profile_pick in ids else 0,
        format_func=lambda i: profiles.label(meta_by_id[i]),
        captions=[meta_by_id[i]["tagline"] for i in ids],
        key="profile_choice",
    )
    if picked != ss.last_profile_pick:
        ss.last_profile_pick = picked
        _load(profiles.load_portfolio(picked), profile_id=picked)
        st.rerun()

    if ss.get("loaded_profile") is None and ss.portfolio:
        st.caption("📄 Showing **your uploaded portfolio**. Pick a book above to "
                   "switch back to a sample.")

    with st.expander("Or upload your own CSV"):
        st.caption("Three columns, one row per holding. `sector` is optional; a "
                   "`CASH` row sets your cash balance.")
        st.code("ticker,shares,cost_basis\nAAPL,10,150.00\nMSFT,5,310.50\nCASH,1,5000",
                language="csv")
        try:
            with open("sample_portfolio.csv", "rb") as fh:
                st.download_button("Download a template", fh.read(),
                                   file_name="robosmart_template.csv",
                                   mime="text/csv", use_container_width=True)
        except OSError:
            pass
        up = st.file_uploader("Portfolio CSV", type=["csv"],
                              label_visibility="collapsed")
        if up is not None:
            try:
                _load(parse_portfolio(up), profile_id=None)
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
            ss.active_ticker = st.selectbox(
                "Stock to analyse", tickers, index=idx,
                help="Bull vs Bear and What Happened Today both analyse this stock.")

        # Only offered when there is something of the user's own to remove.
        # The old "Clear" emptied the app into a dead end whose recovery text
        # named an action ("load the demo portfolio") that appeared nowhere in
        # the sidebar. Returning to a sample is a real destination; an empty
        # screen is not.
        if ss.get("loaded_profile") is None:
            if st.button("Remove my portfolio", use_container_width=True,
                         help="Discard the CSV you uploaded and go back to the "
                              "sample investors."):
                ss.last_profile_pick = DEFAULT_PROFILE
                _load(profiles.load_portfolio(DEFAULT_PROFILE),
                      profile_id=DEFAULT_PROFILE)
                st.rerun()

    st.divider()
    # State the resolved mode explicitly. Recorded data that looks live is the
    # failure this whole layer exists to prevent, so the snapshot date is named.
    mode_line = run_mode.summary_line()
    if mode_line:
        st.caption(mode_line)
    st.caption("Educational university project. **Not investment advice.**")


# ---- Header --------------------------------------------------------------
st.title("RoboSmart Investment")


def _active_context():
    if not ss.active_ticker:
        return None
    try:
        return data_layer.get_context(ss.active_ticker)
    except Exception as e:  # noqa: BLE001
        st.error(f"Couldn't load market data for {ss.active_ticker}: {e}")
        return None


context = _active_context()

# Freshness, always. See _as_of().
as_of = _as_of(context)
live_data = run_mode.describe()["data"] == "live"
if as_of:
    source = "Live market data" if live_data else "Recorded snapshot"
    st.caption(f"{source} · prices as of the close on **{as_of}** · "
               f"all figures close-to-close")
else:
    st.caption("Upload a portfolio and get an AI-assisted analysis across three tools.")

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
from tabs.chat import render as render_chat
from tabs.dashboard import render as render_dashboard
from tabs.debate import render as render_debate

# ---- View router ---------------------------------------------------------
# NOT st.tabs. st.tabs exposes no selected-index API, so it re-mounted at index
# 0 on every rerun — and every sidebar interaction is a rerun. A user who spent
# 25 seconds on a debate and then changed ticker was silently thrown back to the
# Dashboard. Backing the choice with session state also means only ONE view
# renders per run instead of all three, which cuts the per-rerun work by about
# two thirds.
VIEWS = ["Dashboard", "Ask the analyst", "Bull vs Bear", "What Happened Today"]
_ICON = {"Dashboard": "📊", "Ask the analyst": "💬",
         "Bull vs Bear": "⚔️", "What Happened Today": "🔍"}

chosen = st.segmented_control(
    "View", VIEWS, default=ss.view, key="view_choice",
    format_func=lambda v: f"{_ICON[v]}  {v}",
    label_visibility="collapsed",
)
# segmented_control returns None if the user deselects the active item.
if chosen:
    ss.view = chosen
view = ss.view

if view == "Dashboard":
    try:
        render_dashboard(ss.portfolio)
    except Exception as e:  # noqa: BLE001 — one broken view never kills the app
        st.error(f"Dashboard unavailable: {e}")

elif view == "Ask the analyst":
    try:
        render_chat(ss.portfolio)
    except Exception as e:  # noqa: BLE001
        st.error(f"Analyst unavailable: {e}")

elif view == "Bull vs Bear":
    try:
        render_debate(context)
    except Exception as e:  # noqa: BLE001
        st.error(f"Debate unavailable: {e}")

elif view == "What Happened Today":
    try:
        render_attribution(context)
    except Exception as e:  # noqa: BLE001
        st.error(f"Attribution unavailable: {e}")

st.divider()
st.caption("RoboSmart is an educational university project. **This is not investment advice.**")
