"""
app.py — RoboSmart Debate Club (shell + wiring).
================================================
No business logic here — this only wires the sidebar, session state, and the
three views together. Each view is one function from another module.

Modes (see run_mode.py): USE_MOCK=1 runs the whole app offline — recorded market
data AND recorded AI output, no network and no API key. USE_MOCK_DATA /
USE_MOCK_LLM pin one axis without the other.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

import about
import brand
import data_layer
from reporting import panel as export
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

# ABSOLUTE, not "assets/robosmart-mark.svg". Both of these resolve a relative
# path against the PROCESS WORKING DIRECTORY, not against app.py — and when the
# file is not found, page_config's favicon path swallows the error in a bare
# `except Exception` (the fall-through that lets `:shark:` work) and hands the
# frontend the raw string, which then 404s. No exception, no warning, no log
# line: the tab just shows the browser's default icon and nobody notices until
# someone else is looking at the screen. Community Cloud happens to run from
# the repo root, so this was correct by luck rather than by construction.
_MARK = str(brand.LOGO_DIR / "seal.svg")
st.set_page_config(page_title=brand.PRODUCT, layout="wide", page_icon=_MARK)
# THE SEAL, not assets/robosmart-mark.svg. Rendering the app put both on screen
# at once — the old blue rising-line glyph in Streamlit's top-left logo slot and
# the new drawn seal in the sidebar masthead, ~90px apart. Two marks visible
# together do not read as one identity with two lockups; they read as an app
# that changed its mind. LOGOS.md assigns this position to the seal (1:1,
# survives the narrow rail, legible small), so the seal takes it.
#
# st.logo reads the file server-side and inlines it as a base64 data: URI, so
# there is no network fetch and nothing to fail on a cold Community Cloud start.
st.logo(_MARK, size="large")
theme.inject_css()
# The favicon goes in SEPARATELY from page_icon above. page_icon is not a
# reliable route for SVG, and a tab icon that silently does not render is the
# kind of thing nobody notices until someone else is looking at the screen.
# This is belt and braces: whichever of the two works, the tab is marked.
st.markdown(brand.favicon_tag(), unsafe_allow_html=True)

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
    #
    # Now the drawn seal beside the wordmark rather than the wordmark alone.
    # See brand.masthead() for why 44px is correct here despite LOGOS.md's
    # 72px floor — the floor protects a seal carrying the name BY ITSELF, and
    # here the name is set in type immediately beside it.
    st.markdown(brand.masthead(), unsafe_allow_html=True)

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
        st.caption(":material/description: Showing **your uploaded portfolio**. Pick a book above to "
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
# The title and the two global actions share one row. Both actions apply to the
# WHOLE app rather than to any one view — "what is this" explains all four, and
# the export carries whatever the app currently knows — so they belong beside
# the product name, not buried at the bottom of a single tab where the export
# used to sit and where nobody scrolls to find it.
_head, _actions = st.columns([7, 3], vertical_alignment="bottom")
with _head:
    # The drawn mirror IS the h1 — see brand.page_title(). The product name was
    # set twice on this screen: as type here and as the seal-plus-wordmark
    # lockup in the sidebar, ~40px apart. Now each lockup appears once, in the
    # role LOGOS.md assigns it: the seal in the narrow rail, the mirror as the
    # title, and the rose as the stamp on an exported report.
    #
    # GUARDED, like every view below it. This is the one thing on the page that
    # was not, and it cost a total outage: Streamlit Community Cloud re-runs
    # app.py on a push but can keep an already-imported module in sys.modules,
    # so a deploy that adds a NEW function to brand.py can land new app.py
    # against old brand. `masthead()` resolved, `page_title()` did not, and an
    # unguarded AttributeError at module scope takes the entire app down —
    # sidebar rendered, everything else replaced by a traceback.
    #
    # A title is decoration; the portfolio underneath it is the product. Losing
    # the drawn mark to a typeset one is a cosmetic degradation, and that is the
    # correct failure for this. Nothing at module scope should be able to white-
    # screen the app.
    try:
        st.markdown(brand.page_title(), unsafe_allow_html=True)
    except Exception:  # noqa: BLE001 — never let the masthead kill the page
        st.title(brand.PRODUCT)
with _actions:
    # Guarded for the same reason as the wordmark above: these are the newest
    # surface in the app and the likeliest to meet a stale module on a deploy.
    # A missing Guide button is an inconvenience; a traceback where the
    # dashboard should be is an outage.
    try:
        _a1, _a2 = st.columns(2)
        with _a1:
            about.open_button()
        with _a2:
            export.open_button()
    except Exception:  # noqa: BLE001
        pass

# Re-asserted on EVERY run, not opened once from the button's own branch. A
# dialog exists only for the script run that calls it, and this app reruns on
# every sidebar interaction — so a dialog opened inside `if st.button(...)`
# would disappear the moment the reader touched anything. The open state lives
# in session_state; this replays it. See about.py.
try:
    about.maybe_render()
    export.maybe_render(ss.portfolio)
except Exception as e:  # noqa: BLE001 — a dialog never takes the page with it
    st.error(f"That panel is unavailable: {e}")


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
# Material Symbols, not emoji. Four emoji meant four glyphs at four different
# weights, colour temperatures and baselines — the loudest unauthored signal on
# the page, sitting on its only navigation. These inherit the text colour and
# the type's optical weight, so the router reads as one control.
#
# The trailing space is load-bearing: Streamlit's leading-icon parser only
# fires when the token is followed by whitespace, and ":material/chat:Ask"
# renders the literal text ":material_chat:Ask".
_ICON = {"Dashboard": ":material/analytics:",
         "Ask the analyst": ":material/forum:",
         "Bull vs Bear": ":material/balance:",
         "What Happened Today": ":material/troubleshoot:"}

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
st.caption(f"{brand.PRODUCT} is an educational university project. "
           f"**This is not investment advice.**")
