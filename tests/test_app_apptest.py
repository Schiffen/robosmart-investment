"""End-to-end: run the full app.py (all three tabs) through Streamlit AppTest
on mock data and assert it renders with no exception and no error blocks."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_source

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "app.py")

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


def test_full_app_renders_on_mock(monkeypatch):
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")      # auto-loads demo, no API key
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, f"App raised: {at.exception}"
    assert len(at.error) == 0                # every tab rendered cleanly
    # dashboard's headline + risk tiles
    assert len(at.metric) >= 8


def test_debate_button_runs_on_mock(monkeypatch):
    """Selecting the Bull vs Bear view and starting a debate must render cleanly.

    This used to be written as `if btns:` and passed VACUOUSLY once the start
    button's label changed case — and again once only the selected view renders,
    which means the button does not exist at all while the Dashboard is up. The
    assertion that the button was found is the point of the test.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["view"] = "Bull vs Bear"
    at.run()
    assert not at.exception

    btns = [b for b in at.button if "debate" in (b.label or "").lower()]
    assert btns, "no start-debate button in the Bull vs Bear view"
    btns[0].click().run()
    assert not at.exception
    assert len(at.error) == 0


def test_only_the_selected_view_renders(monkeypatch):
    """The router must render ONE view, not all three.

    st.tabs rendered every tab body on every run, so a single sidebar
    interaction re-executed all three render functions and refetched the whole
    book. It also reset the selection to tab 0 on every rerun, throwing away the
    place of anyone who had just waited 25 seconds for a debate.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")

    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["view"] = "What Happened Today"
    at.run()
    assert not at.exception
    # The dashboard's metric tiles must be absent: its view did not run.
    assert len(at.metric) <= 2, "dashboard rendered while another view was selected"

    # And the selection survives a rerun rather than snapping back to Dashboard.
    at.run()
    assert at.session_state["view"] == "What Happened Today"


# --------------------------------------------------------------------------
# Sample investor profiles
# --------------------------------------------------------------------------

def test_app_opens_on_a_populated_dashboard(monkeypatch):
    """A visitor must land on the tool working, not an upload prompt.

    The deployed app previously opened empty on live data, because auto-load was
    gated on fixture mode — so a grader's first five seconds were a file picker.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert len(at.metric) >= 8, "opened without a populated dashboard"
    assert at.info, "no profile explainer shown"
    assert "Balanced growth" in at.info[0].value


def _count_warnings(at) -> int:
    """Concentration flags render through theme.notice() rather than
    st.warning, because st.warning is aria-live="assertive" and these
    re-announce on every rerun. They carry data-notice='warn' so this
    invariant stays testable."""
    return sum(m.value.count("data-notice='warn'")
               for m in at.markdown if isinstance(m.value, str))


def test_switching_profile_changes_the_verdict(monkeypatch):
    """The point of five books is that one engine reaches five verdicts.

    Balanced trips exactly one warning; the concentrated book trips three. If
    these ever produced the same output the profiles would be decoration.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert _count_warnings(at) == 1, "balanced book should trip exactly one warning"

    picker = [r for r in at.radio if "investor" in (r.label or "").lower()]
    assert picker, "no sample-investor selector in the sidebar"
    assert len(picker[0].options) >= 5

    # Selecting loads directly — there is no separate confirm step. The old
    # two-step select-then-Load left the sidebar describing one book while the
    # main banner still described another, with nothing marking either as
    # pending: a textbook mode error.
    concentrated = next(o for o in picker[0].options if "concentrated" in o.lower())
    picker[0].set_value(concentrated).run()

    assert not at.exception
    assert len(at.error) == 0
    assert _count_warnings(at) >= 3, "concentrated book should trip three guidelines"
    assert "Concentrated" in at.info[0].value


def test_every_sample_book_is_reachable_and_captioned(monkeypatch):
    """You must be able to see what you are choosing between, at the moment of
    choosing. The books are the "one engine, five verdicts" demonstration, and a
    dropdown showing only emoji + name hid the very thing that makes them a
    demonstration."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180).run()

    picker = [r for r in at.radio if "investor" in (r.label or "").lower()][0]
    import profiles
    assert len(picker.options) == len(profiles.list_profiles())
    # Each option carries its differentiating tagline alongside it.
    taglines = [p["tagline"] for p in profiles.list_profiles()]
    assert all(t for t in taglines), "a profile is missing its tagline"


def test_no_control_strands_the_user_on_an_empty_app(monkeypatch):
    """The old "Clear" emptied the app into a dead end whose recovery text named
    an action ("load the demo portfolio") that appeared nowhere in the sidebar.

    A sample book now has no control that empties the app at all, so the dead
    end is unreachable rather than merely decorated.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180).run()

    destructive = [b for b in at.button
                   if (b.label or "").strip().lower() in ("clear", "remove my portfolio")]
    assert not destructive, "a sample book still offers a control that empties the app"
    assert len(at.metric) >= 8, "opened without a populated dashboard"


def test_uploaded_portfolio_can_be_removed_back_to_a_sample(monkeypatch):
    """The removal control appears only for the user's OWN portfolio, and it
    returns to a populated sample rather than to an empty screen."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")

    at = AppTest.from_file(APP, default_timeout=180)
    # Stand in for an uploaded CSV: a portfolio with no originating profile.
    at.session_state["portfolio"] = {
        "positions": [{"ticker": "AAPL", "shares": 10.0,
                       "cost_basis": 150.0, "sector": "Technology"}],
        "cash": 1000.0, "currency": "USD",
    }
    at.session_state["portfolio_source"] = book_source.upload("mine.csv")
    at.session_state["active_ticker"] = "AAPL"
    at.run()
    assert not at.exception

    remove = [b for b in at.button
              if (b.label or "").strip() == "Remove my portfolio"]
    assert remove, "no way to remove an uploaded portfolio"

    remove[0].click().run()
    assert not at.exception
    assert book_source.profile_id(at.session_state["portfolio_source"]), (
        "did not return to a sample")
    assert len(at.metric) >= 8, "removal left the dashboard empty"


# --------------------------------------------------------------------------
# Deployment: Streamlit-managed secrets
# --------------------------------------------------------------------------

# NOTE: these deliberately exercise the bridge with NON-SECRET keys
# (ANTHROPIC_MODEL, USE_MOCK_DATA). An earlier version asserted on
# ANTHROPIC_API_KEY, and because `load_dotenv()` loads the real .env before the
# bridge runs, a failing assertion printed the live key straight into the test
# output. A test must never be able to render a real credential — the mechanism
# is identical for every key in _CONFIG_KEYS, so nothing is lost by proving it
# with one that carries no secret.

def test_streamlit_secrets_reach_the_environment(monkeypatch):
    """Streamlit Community Cloud exposes secrets via st.secrets, NOT as env vars.

    `run_mode` and `agents/llm` both read os.environ, so without the bridge in
    app.py the deployed app finds no configuration and quietly serves RECORDED
    output while looking perfectly healthy. Nothing errors — which is exactly why
    this needs a test rather than a glance at the running app.
    """
    monkeypatch.chdir(BASE)
    for key in ("ANTHROPIC_MODEL", "USE_MOCK", "USE_MOCK_DATA", "USE_MOCK_LLM"):
        monkeypatch.delenv(key, raising=False)

    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["ANTHROPIC_MODEL"] = "claude-sonnet-5-from-secrets"
    at.secrets["USE_MOCK_DATA"] = "1"          # keep the run offline
    at.run()

    assert not at.exception, f"App raised: {at.exception}"
    assert os.environ.get("ANTHROPIC_MODEL") == "claude-sonnet-5-from-secrets"

    import run_mode
    assert run_mode.use_fixture_data() is True, "USE_MOCK_DATA did not cross the bridge"


def test_existing_env_var_beats_streamlit_secrets(monkeypatch):
    """A local .env must still win, so deployed config can't hijack dev runs."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("ANTHROPIC_MODEL", "model-from-environment")
    monkeypatch.setenv("USE_MOCK_DATA", "1")

    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["ANTHROPIC_MODEL"] = "model-from-secrets"
    at.run()

    assert not at.exception
    assert os.environ.get("ANTHROPIC_MODEL") == "model-from-environment"


def test_no_test_asserts_on_the_real_api_key():
    """Guard the guard: keep credential values out of assertion diffs forever."""
    import pathlib
    # Split so this line cannot match its own pattern — the first version of
    # this test failed by flagging itself, the same way docs/DEPLOY.md's secret-scan
    # command matches the grep inside docs/DEPLOY.md.
    needle = "ANTHROPIC_" + "API_KEY"
    offenders = []
    for path in pathlib.Path(BASE, "tests").glob("*.py"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or needle not in stripped:
                continue
            if "assert" in stripped:
                offenders.append(f"{path.name}:{n}")
    assert not offenders, (
        "these lines can print a live credential in a failure diff: " + ", ".join(offenders))


# --------------------------------------------------------------------------
# The stock selector: scoped to the two views that consume it
# --------------------------------------------------------------------------
#
# Only Bull vs Bear and What Happened Today render get_context(active_ticker);
# the Dashboard and Ask the analyst are portfolio-wide. The picker moved out of
# the sidebar to sit under the router on exactly those two.
#
# The risk this closes: Streamlit sweeps widget state for widgets not rendered
# on a run, and it does so at END of run — so a keyed picker keeps its value on
# the run that hides it and only resets on the SECOND view switch. A test that
# checks one switch passes against the broken version.

_PICKER = "Stock to analyse"


def _pickers(at):
    return [s for s in at.selectbox if (s.label or "") == _PICKER]


def _goto(at, view):
    """Change view the way a user does — by clicking the router.

    NOT `at.session_state["view"] = view`. Assigning session state and rerunning
    does NOT trigger Streamlit's stale-widget sweep, so a picker keyed on its own
    widget id keeps its value across the switch and every assertion below passes
    against the broken implementation. Measured: driving the router, the widget
    key goes absent on the hidden run and the picker returns on the first
    holding; assigning session state, it survives. Only the first is the bug.
    """
    at.segmented_control[0].set_value(view).run()
    return at


@pytest.mark.parametrize("view", ["Dashboard", "Ask the analyst"])
def test_no_stock_picker_on_the_portfolio_wide_views(monkeypatch, view):
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["view"] = view
    at.run()
    assert not at.exception
    assert not _pickers(at), (
        f"{view} is portfolio-wide, so a stock picker there would advertise "
        f"control it does not have")


@pytest.mark.parametrize("view", ["Bull vs Bear", "What Happened Today"])
def test_the_stock_picker_is_on_the_views_that_use_it(monkeypatch, view):
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["view"] = view
    at.run()
    assert not at.exception
    assert _pickers(at), f"{view} analyses one stock but offers no way to pick it"


def test_the_selected_stock_survives_two_round_trips(monkeypatch):
    """Pick a stock, leave twice, come back twice. It must still be selected.

    ONE round trip is not enough to catch the bug: Streamlit removes stale
    widget state at the end of the run, so the value is still readable on the
    run that hides the widget and only disappears afterwards.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=240)
    at.session_state["view"] = "Bull vs Bear"
    at.run()
    assert not at.exception

    options = list(_pickers(at)[0].options)
    assert len(options) > 1, "need at least two holdings to prove selection sticks"
    chosen = options[-1]
    _pickers(at)[0].select(chosen).run()
    assert at.session_state["active_ticker"] == chosen

    for i in range(2):
        _goto(at, "Dashboard")
        assert not at.exception
        assert at.session_state["active_ticker"] == chosen, (
            f"round {i}: active_ticker was swept while the picker was hidden")
        _goto(at, "Bull vs Bear")
        assert not at.exception
        assert at.session_state["active_ticker"] == chosen, (
            f"round {i}: the selection did not survive coming back")
        assert _pickers(at)[0].value == chosen, (
            f"round {i}: the picker came back on a different holding "
            f"({_pickers(at)[0].value}) than the one selected ({chosen})")


def test_the_export_reads_the_selected_stock_from_the_dashboard(monkeypatch):
    """panel.py reads active_ticker from the HEADER, which renders on all views.

    It uses .get(), so a swept value is not an error — it silently produces a
    PDF with the Bull vs Bear section missing, which is the part of the report
    most worth sending to someone.
    """
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=240)
    at.session_state["view"] = "Bull vs Bear"
    at.run()
    chosen = list(_pickers(at)[0].options)[-1]
    _pickers(at)[0].select(chosen).run()

    # A full round trip before opening the export, deliberately: after ONE
    # switch the value is still correct even in the broken version, because the
    # stale-widget sweep runs at the end of the hiding run.
    _goto(at, "Dashboard")
    _goto(at, "Bull vs Bear")
    _goto(at, "Dashboard")
    assert not at.exception
    assert at.session_state["active_ticker"] == chosen

    at.session_state["show_export"] = True
    at.run()
    assert not at.exception
    assert at.session_state["active_ticker"] == chosen, (
        "the export dialog opened from the Dashboard cannot see the stock")


def test_the_freshness_caption_does_not_depend_on_the_selected_stock(monkeypatch):
    """It is sourced from the one SPY benchmark, so it must be identical
    everywhere — including on the two views where nothing is selected."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")

    def caption_on(view):
        at = AppTest.from_file(APP, default_timeout=180)
        at.session_state["view"] = view
        at.run()
        assert not at.exception
        hits = [c.value for c in at.caption if "close on" in (c.value or "")]
        assert hits, f"no freshness caption on {view}"
        return hits[0]

    assert caption_on("Dashboard") == caption_on("Bull vs Bear")


# --------------------------------------------------------------------------
# The builder: a full-page takeover with two ways in and one review step
# --------------------------------------------------------------------------
#
# AppTest has NO data_editor accessor (50 element accessors; `dataframe` yes,
# `data_editor` no), so the table itself cannot be driven from here. That is
# precisely why the canonical draft lives in an app-owned session key rather
# than in the editor's own state — seeding `builder_draft` is the only way this
# flow is coverable at all.

def _open_builder(monkeypatch, **state):
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["show_builder"] = True
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    return at


def _btn(at, text):
    hits = [b for b in at.button if text.lower() in (b.label or "").lower()]
    assert hits, f"no button matching {text!r}; saw {[b.label for b in at.button]}"
    return hits[0]


def test_the_builder_takes_over_the_page(monkeypatch):
    """While it is open there is no router and no view — it is a mode, not a
    fifth thing to look at."""
    at = _open_builder(monkeypatch)
    assert not at.exception
    assert len(at.error) == 0
    assert not at.segmented_control, "the router is still on screen behind the builder"
    assert len(at.metric) <= 2, "a view rendered underneath the builder"


def test_the_builder_survives_partially_seeded_state(monkeypatch):
    """Arriving with only some of its keys set must not take the page down.

    Keying the whole reset off `builder_draft` alone did exactly that: the
    questionnaire then read an absent `builder_answers` and raised.
    """
    at = _open_builder(monkeypatch, builder_draft=[
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0}])
    assert not at.exception
    assert len(at.error) == 0


def test_typing_a_book_in_commits_it_and_names_it_as_built(monkeypatch):
    at = _open_builder(monkeypatch, builder_cash=1500.0, builder_draft=[
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0},
        {"ticker": "BND", "shares": 20.0, "cost_basis": 72.0}])

    _btn(at, "Use this portfolio").click().run()
    assert not at.exception

    assert at.session_state["show_builder"] is False, "the builder stayed open"
    book = at.session_state["portfolio"]
    assert [p["ticker"] for p in book["positions"]] == ["VTI", "BND"]
    assert book["cash"] == 1500.0
    assert book_source.kind_of(at.session_state["portfolio_source"]) == "built"
    assert at.session_state["active_ticker"] == "VTI"
    assert len(at.metric) >= 8, "committing did not land on a populated dashboard"


def test_sectors_come_from_the_shelf_not_from_a_network_lookup(monkeypatch):
    """portfolio._lookup_sector calls yfinance once per row and ignores
    USE_MOCK_DATA entirely. In a table that reruns as you type, that would be a
    request per keystroke per row."""
    at = _open_builder(monkeypatch, builder_draft=[
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0},
        {"ticker": "BND", "shares": 20.0, "cost_basis": 72.0}])
    _btn(at, "Use this portfolio").click().run()

    import shelf
    for p in at.session_state["portfolio"]["positions"]:
        assert p["sector"] == shelf.sector_of(p["ticker"])
        assert p["sector"] != "Unknown"


def test_cancelling_leaves_the_current_portfolio_untouched(monkeypatch):
    at = _open_builder(monkeypatch, builder_draft=[
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0}])
    before = at.session_state["portfolio"]
    before_source = at.session_state["portfolio_source"]

    _btn(at, "Back").click().run()
    assert not at.exception
    assert at.session_state["show_builder"] is False
    assert at.session_state["portfolio"] == before
    assert at.session_state["portfolio_source"] == before_source


def test_an_unanswered_questionnaire_cannot_draft_a_book(monkeypatch):
    at = _open_builder(monkeypatch)
    assert _btn(at, "Draft a book from this").disabled, (
        "a book was draftable from a form nobody had filled in")


ANSWERS_CAUTIOUS = {
    "purpose": "preservation", "horizon": "under_2y", "loss_limit": "35",
    "behaviour": "sell_all", "experience": "none", "concentration": "middle",
    "include_categories": [], "exclude_categories": [],
}


def test_drafting_fills_the_table_and_does_not_touch_the_portfolio(monkeypatch):
    """The human step between the model and the book. A draft is a proposal."""
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    before = at.session_state["portfolio"]

    _btn(at, "Draft a book from this").click().run()
    assert not at.exception
    assert len(at.error) == 0

    draft = at.session_state["builder_draft"]
    assert len(draft) >= 4
    assert all(r["ticker"] and r["shares"] > 0 and r["cost_basis"] > 0 for r in draft)
    assert at.session_state["portfolio"] == before, (
        "drafting changed the portfolio before the reader accepted it")


def test_a_drafted_book_is_marked_as_drafted_when_committed(monkeypatch):
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    _btn(at, "Draft a book from this").click().run()
    _btn(at, "Use this portfolio").click().run()
    assert not at.exception

    src = at.session_state["portfolio_source"]
    assert book_source.kind_of(src) == "drafted"
    assert "upload" not in book_source.label_of(src).lower()
    assert not book_source.detail_is_checked(src), (
        "a model-written note must not be presented as a checked claim")


def test_a_recorded_draft_says_so_on_screen(monkeypatch):
    """docs/PRODUCT.md principle 4: recorded output must never look live."""
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    _btn(at, "Draft a book from this").click().run()

    assert at.session_state["builder_generated"]["is_mock"] is True
    blob = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "rule-based allocator" in blob


def test_contradictory_answers_surface_a_tension_before_the_table(monkeypatch):
    """"Could ride out 35%" and "would sell everything" is the FCA's own named
    good practice: highlight the conflict, do not resolve it silently."""
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    blob = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "point opposite ways" in blob


def test_a_consistent_questionnaire_raises_no_tension(monkeypatch):
    calm = dict(ANSWERS_CAUTIOUS, loss_limit="5", behaviour="sell_all")
    at = _open_builder(monkeypatch, builder_answers=calm)
    blob = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "point opposite ways" not in blob


def test_a_bad_row_blocks_the_commit_and_says_why(monkeypatch):
    at = _open_builder(monkeypatch, builder_draft=[
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0},
        {"ticker": "BND", "shares": -5.0, "cost_basis": 72.0}])
    assert _btn(at, "Use this portfolio").disabled, "a negative holding was committable"
    assert any("Shares must be > 0" in (e.value or "") for e in at.error)


def test_the_drafted_book_flows_through_to_the_export(monkeypatch):
    """Whatever is built here must be what every other surface then reports on."""
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    _btn(at, "Draft a book from this").click().run()
    tickers = [r["ticker"] for r in at.session_state["builder_draft"]]
    _btn(at, "Use this portfolio").click().run()

    at.session_state["show_export"] = True
    at.run()
    assert not at.exception
    assert len(at.error) == 0

    # Asserted through book_source rather than by calling panel._filename()
    # here: those read `st.session_state`, and from the test PROCESS that is the
    # real one, not the AppTest's — so a direct call sees no source at all and
    # passes against anything. panel delegates to exactly these two functions.
    src = at.session_state["portfolio_source"]
    assert book_source.filename_slug(src) == "drafted"
    assert "upload" not in book_source.label_of(src).lower()
    assert [p["ticker"] for p in at.session_state["portfolio"]["positions"]] == tickers


def test_no_questionnaire_copy_reaches_the_page_with_an_unescaped_dollar(monkeypatch):
    """A bare `$` opens a LaTeX span in Streamlit's markdown, so a string with
    TWO of them swallows everything between.

    Caught by rendering it, not by reading it: the loss-limit question — the
    highest-signal item in the instrument — reached the page as "Say you put in
    10,000 and four months later it is worth 7,000", with both amounts gone. The
    source reads perfectly well.
    """
    import re
    at = _open_builder(monkeypatch)
    assert not at.exception

    unescaped = re.compile(r"(?<!\\)\$")
    offenders = []
    for r in at.radio:
        for text in [r.label or ""] + [str(o) for o in (r.options or [])]:
            if unescaped.search(text):
                offenders.append(text)
    assert not offenders, f"unescaped $ reaches the markdown parser: {offenders}"


def test_the_loss_limit_question_still_shows_both_amounts(monkeypatch):
    at = _open_builder(monkeypatch)
    labels = " ".join(r.label or "" for r in at.radio)
    assert "10,000" in labels and "7,000" in labels
    assert r"\$10,000" in labels, "the amount lost its escaped dollar sign"


def test_the_builder_does_not_show_the_current_books_banner(monkeypatch):
    """Seen in a browser: "Balanced growth — One sector warning: Technology sits
    just above 40%" rendered directly above the form for building a different
    book, warning about a portfolio the reader was replacing.

    The freshness caption stays — it names the close the drafted cost basis is
    struck at — but the identity banner belongs to a book you are not looking at.
    """
    at = _open_builder(monkeypatch)
    assert not at.exception
    assert not at.info, (
        f"the identity banner rendered above the builder: "
        f"{[i.value for i in at.info]}")

    blob = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "sector warning" not in blob.lower()

    # ...and the freshness line IS still there.
    assert any("close on" in (c.value or "") for c in at.caption), (
        "the builder lost the line naming which close prices come from")


def test_start_over_actually_starts_over(monkeypatch):
    """It used to reset the table and NOTHING ELSE.

    Streamlit lets a surviving widget key beat the `value=`/`index=` argument, so
    clearing only the mirror dicts left every radio selected, the cash box at its
    old figure, and — because the answers dict is repopulated from those same
    widgets on the next line of the render — the "Draft a book" button enabled.
    It even looked right: clearing GENERATED springs the questionnaire expander
    open again, over a form that is still full.
    """
    at = _open_builder(monkeypatch, builder_answers=dict(ANSWERS_CAUTIOUS))
    _btn(at, "Draft a book from this").click().run()
    assert len(at.session_state["builder_draft"]) >= 4

    _btn(at, "Start over").click().run()
    assert not at.exception

    answers = at.session_state["builder_answers"]
    assert not [v for v in answers.values() if isinstance(v, str)], (
        f"answers survived the reset: {answers}")
    assert at.session_state["builder_cash"] == 0.0
    assert at.session_state["builder_free_text"] == ""
    assert _btn(at, "Draft a book from this").disabled, (
        "a book was still draftable from a form that had just been cleared")
    for r in at.radio:
        if (r.label or "").startswith(("What is this money", "If you had to",
                                       "In that situation", "How much investing",
                                       "Which book")):
            assert r.value is None, f"{r.label!r} kept its selection"


def test_tensions_describe_the_edited_book_not_the_drafted_one(monkeypatch):
    """They used to measure `builder_draft`, which is deliberately never written
    from the editor — so gutting the table and committing shipped a PDF asserting
    a beta about a book that no longer existed.

    These numbers are the feature's whole claim to be arithmetic a reader can
    check. Attached to the wrong book they are worse than no numbers.
    """
    at = _open_builder(monkeypatch, builder_answers=dict(
        ANSWERS_CAUTIOUS, loss_limit="5", concentration="broad"))
    _btn(at, "Draft a book from this").click().run()

    # Stand in for the reader replacing the drafted book by hand.
    at.session_state["builder_draft"] = [
        {"ticker": "NVDA", "shares": 100.0, "cost_basis": 200.75}]
    at.run()
    assert not at.exception

    blob = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "largest holding is 100%" in blob, (
        "the concentration tension is still measuring the drafted book")
