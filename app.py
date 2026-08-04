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
import book_source
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
ss.setdefault("portfolio_source", None)


def _profile_source(profile_id: str) -> dict:
    """book_source record for a shipped sample, carrying its checked `expect`."""
    meta = next((p for p in profiles.list_profiles() if p["id"] == profile_id), None)
    return book_source.profile(
        profile_id,
        label=profiles.label(meta) if meta else profile_id,
        expect=(meta or {}).get("expect"))


def _load(portfolio: dict, *, source: dict) -> None:
    """The ONE way a portfolio enters session state.

    `source` is required rather than defaulted, so a new producer cannot forget
    to say what it is. Everything downstream — the identity banner, the sidebar,
    the export panel, the PDF cover and its filename — reads that one record.

    The cash widget's key is cleared here for the same reason `active_ticker` is
    reset: Streamlit lets a surviving widget key win over the `value=` argument,
    so without this, switching books would leave the previous book's cash in the
    input and then write it straight back into the new one.
    """
    ss.portfolio = portfolio
    tickers = [p["ticker"] for p in portfolio.get("positions", [])]
    ss.active_ticker = tickers[0] if tickers else None
    ss.portfolio_source = source
    ss.pop("cash_input", None)
    # A questionnaire summary belongs to the book it drafted. Cleared here so it
    # cannot follow the next book into the export and explain a portfolio that
    # is no longer on screen; the builder re-sets it immediately after the
    # commit for a book it actually drafted.
    ss.pop("portfolio_profile", None)


# Land on a populated dashboard rather than an empty one. The deployed app used
# to open on an upload prompt and an empty tab — a poor first five seconds for a
# tool whose whole point is what it computes.
if ss.portfolio is None:
    _load(profiles.load_portfolio(DEFAULT_PROFILE),
          source=_profile_source(DEFAULT_PROFILE))


def _as_of() -> str | None:
    """The date of the last SETTLED close actually being shown.

    Everything in this app is close-to-close (INTEGRATION_CONTRACT §3), so on a
    Monday morning the "current" price is Friday's. The interface said nothing
    about this at all: run_mode.summary_line() returns None when both axes are
    live, so the DEPLOYED app — the only one a grader sees — carried no
    freshness signal whatsoever. Principle 4 says recorded data must never look
    live; the same reasoning says stale data must never look fresh.

    SOURCED FROM THE BENCHMARK, NOT FROM THE SELECTED STOCK. This used to read
    `context["history"]`, which had two problems. The caption's date moved when
    you changed stock — wrong, because every figure in this app is close-to-close
    against ONE SPY series (§3 and §4), so freshness is a property of the data
    source rather than of whichever holding is selected. And it needed a context
    to exist at all, which is no longer true on the two views that do not select
    a stock. `get_benchmark_history` is the single benchmark source and is
    cached, so this costs nothing and cannot disagree with the charts.
    """
    try:
        history = data_layer.get_benchmark_history("SPY")
        if history is not None and len(history) > 0:
            return history.index[-1].strftime("%-d %b %Y")
    except Exception:  # noqa: BLE001 — a missing benchmark never blocks the page
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
        _load(profiles.load_portfolio(picked), source=_profile_source(picked))
        st.rerun()

    if ss.portfolio and book_source.is_users_own(ss.portfolio_source):
        # "Showing: **<label>**", not "Showing **<label.lower()>**". Lowercasing
        # reads fine for "your uploaded portfolio" and produced "Showing drafted
        # from your investor profile" for a generated book — a sentence with no
        # subject. The colon lets each label keep its own capitalisation.
        st.caption(f":material/description: Showing: "
                   f"**{book_source.label_of(ss.portfolio_source)}**. "
                   f"Pick a book above to switch back to a sample.")

    with st.expander("Or upload your own CSV"):
        # The CASH row reads its amount from the SHARES column, which is
        # unobvious enough that this example used to say `CASH,1,5000` — i.e.
        # one dollar — while the template offered for download correctly said
        # `CASH,5000,0`. A user who copied what the app displayed lost their
        # cash balance with no error. tests/test_portfolio.py now parses this
        # very literal out of the source and asserts it means $5,000.
        st.caption("Three columns, one row per holding. `sector` is optional. A "
                   "`CASH` row sets your cash balance — the amount goes in the "
                   "**shares** column.")
        st.code("ticker,shares,cost_basis\nAAPL,10,150.00\nMSFT,5,310.50\nCASH,5000,0",
                language="csv")
        try:
            # Absolute, for the reason page_icon is: a relative path resolves
            # against the PROCESS working directory, not against app.py, and the
            # `except OSError: pass` below would then silently drop the download
            # button with no error anywhere.
            with open(Path(__file__).parent / "sample_portfolio.csv", "rb") as fh:
                st.download_button("Download a template", fh.read(),
                                   file_name="robosmart_template.csv",
                                   mime="text/csv", use_container_width=True)
        except OSError:
            pass
        up = st.file_uploader("Portfolio CSV", type=["csv"],
                              label_visibility="collapsed")
        if up is not None:
            try:
                _load(parse_portfolio(up),
                      source=book_source.upload(getattr(up, "name", None)))
                st.success("Portfolio loaded.")
            except PortfolioError as e:
                st.error(str(e))

    # Third way in, beside the other two. Opens a full-page takeover rather
    # than a dialog — see tabs/build.py on why.
    try:
        from tabs import build as builder
        builder.open_button()
    except Exception as e:  # noqa: BLE001 — a missing builder is not an outage
        st.caption(f"Builder unavailable: {e}")

    if ss.portfolio:
        st.divider()
        positions = ss.portfolio.get("positions", [])
        st.write(f"**{len(positions)} holdings**")

        # ---- Cash, editable ------------------------------------------------
        # Cash used to be printed and never changeable: it arrived from a CASH
        # row or a profile JSON and that was that. But cash is not a property of
        # your holdings — it is a fact about your life, and it moves. It was the
        # one number in the book the app fixed at load time for no reason.
        #
        # The sidebar is right for THIS control even though the stock selector
        # was just moved out of it, and the distinction is frequency: you switch
        # stock constantly while analysing, and you change your cash balance
        # when something happens. Rare, global, and already where cash was
        # reported.
        #
        # Editing it does NOT detach a sample book from its identity. Weights
        # here are equity-based with cash excluded (portfolio_metrics, finance
        # assumption 1) — measured, cash 5,000 -> 500,000 moves no weight at all
        # — so every `expect` claim a profile makes still holds afterwards.
        _cash_now = float(ss.portfolio.get("cash", 0.0) or 0.0)
        _cash_new = st.number_input(
            "Cash", min_value=0.0, value=_cash_now, step=100.0, format="%.2f",
            key="cash_input",
            help="Uninvested cash. Counted in your total value, and deliberately "
                 "NOT counted in any weight, sector split or beta — those are "
                 "equity-risk figures and idle cash would understate them.")
        if _cash_new != _cash_now:
            # No st.rerun(): the sidebar runs before the main area, so the views
            # below already see the new number on this same run.
            ss.portfolio["cash"] = float(_cash_new)

        # The "Stock to analyse" selector used to live here. It moved to sit
        # directly under the router, because only two of the four views consume
        # it — putting it in the rail cost a sidebar trip per change and left
        # the control invisible from the screens it drives.

        # Only offered when there is something of the user's own to remove.
        # The old "Clear" emptied the app into a dead end whose recovery text
        # named an action ("load the demo portfolio") that appeared nowhere in
        # the sidebar. Returning to a sample is a real destination; an empty
        # screen is not.
        if book_source.is_users_own(ss.portfolio_source):
            if st.button("Remove my portfolio", use_container_width=True,
                         help=f"Discard this book "
                              f"({book_source.label_of(ss.portfolio_source)}) "
                              f"and go back to the sample investors."):
                ss.last_profile_pick = DEFAULT_PROFILE
                _load(profiles.load_portfolio(DEFAULT_PROFILE),
                      source=_profile_source(DEFAULT_PROFILE))
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


# Freshness, always. See _as_of().
as_of = _as_of()
live_data = run_mode.describe()["data"] == "live"
if as_of:
    source = "Live market data" if live_data else "Recorded snapshot"
    st.caption(f"{source} · prices as of the close on **{as_of}** · "
               f"all figures close-to-close")
else:
    st.caption("Upload a portfolio and get an AI-assisted analysis across three tools.")

# ---- Builder takeover -----------------------------------------------------
# While the builder is open it OWNS the page: no router, no view. The four views
# analyse the current book; this one makes one, so presenting them side by side
# would suggest the builder is a fifth thing to look at rather than a mode you
# are in. Hiding the router is the signal that you are somewhere else.
#
# Placed AFTER the freshness caption and BEFORE the identity banner, and the gap
# between those two is deliberate. The caption belongs here — it names the close
# the drafted cost basis is struck at. The banner does not: seen in a browser, it
# read "Balanced growth — One sector warning: Technology sits just above 40%"
# directly above a form for building something else entirely, warning about a
# book the reader was in the middle of replacing.
try:
    from tabs import build as builder
    if builder.is_open():
        try:
            builder.render(on_commit=_load)
        except Exception as e:  # noqa: BLE001 — never strand the user in a broken mode
            st.error(f"The builder hit a problem: {e}")
            if st.button("Go back"):
                builder.close()
                st.rerun()
        st.stop()
except Exception as e:  # noqa: BLE001
    # NOT `except ImportError`. A failed import is evicted from sys.modules, so
    # an exception raised BY tabs/build.py at import time — the stale-module
    # case app.py already documents for brand.page_title — is not an ImportError
    # and would escape at module scope and white-screen the app, while the
    # sidebar's own broad guard reassuringly printed "Builder unavailable".
    # st.stop() raises StopException, which derives from BaseException, so it is
    # not caught here.
    st.error(f"The builder is unavailable: {e}")

# ---- Whose book is this ---------------------------------------------------
# Named on EVERY view and for EVERY kind of book, not just for sample profiles.
# This used to fire only when `loaded_profile` was set, so a reader with their
# own portfolio got no statement anywhere in the main area about whose data was
# on screen — the sidebar caption was the only signal, and the sidebar is
# collapsed on a phone.
#
# The two halves are rendered DIFFERENTLY on purpose. A profile's `expect` is a
# claim tests/test_profiles.py enforces against the real numbers, so it earns
# st.info's authority. A drafted book's note is model prose: true-sounding, and
# checked by nobody. Giving them the same treatment would dress an unchecked
# claim in a checked one's clothes, which is the exact move the rest of this
# codebase refuses to make.
_src = book_source.normalise(ss.portfolio_source)
if _src["detail"] and book_source.detail_is_checked(_src):
    st.info(f"**{_src['label']}** — {_src['detail']}")
elif _src["detail"] and _src["kind"] == "drafted":
    st.caption(f":material/auto_awesome: **{theme.safe_md(_src['label'])}** — "
               f"{theme.safe_md(_src['detail'])}")
elif book_source.is_users_own(_src):
    st.caption(f":material/description: **{_src['label']}**")

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

# ---- Stock selector ------------------------------------------------------
# Only TWO of the four views take a stock: Bull vs Bear and What Happened Today
# both render `get_context(active_ticker)`, while the Dashboard and Ask the
# analyst are portfolio-wide. So the control renders on exactly those two, right
# under the router and above the thing it drives. In the sidebar it cost a trip
# to the rail for every change and was invisible from the screens it controlled;
# on all four views it would have advertised control it does not have on half.
#
# NO `key=`. Streamlit discards widget state for any widget not instantiated on
# a run, and it does the sweep at END of run — so a keyed picker resets on the
# SECOND view switch, not the first, which is how this ships broken. Keeping
# `ss.active_ticker` as plain app-owned state and passing it back as `index=`
# survives the round trip, and it is what this line already did in the sidebar.
# (`key="active_ticker"` while also assigning to `ss.active_ticker` is a hard
# StreamlitAPIException, so that shape is not available anyway.)
#
# `active_ticker` must stay non-None on EVERY view regardless: reporting/panel.py
# reads it from the header to decide which debate goes in the PDF, and it uses
# .get(), so a lost value would silently ship a report with the Bull vs Bear
# section missing — no error, no warning, and that section is the reason the
# export exists.
NEEDS_TICKER = {"Bull vs Bear", "What Happened Today"}

context = None
if view in NEEDS_TICKER:
    _tickers = [p["ticker"] for p in (ss.portfolio or {}).get("positions", [])]
    if _tickers:
        _idx = _tickers.index(ss.active_ticker) if ss.active_ticker in _tickers else 0
        _pick_col, _ = st.columns([2, 5])
        with _pick_col:
            ss.active_ticker = st.selectbox(
                "Stock to analyse", _tickers, index=_idx,
                help="Bull vs Bear and What Happened Today both analyse this "
                     "stock. The Dashboard and Ask the analyst cover your whole "
                     "book, which is why this only appears on these two.")
    # Gated, so the two portfolio-wide views no longer pay for a context they
    # never read — in live mode that was a yfinance round trip per rerun on
    # Dashboard and on Ask the analyst.
    context = _active_context()

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
