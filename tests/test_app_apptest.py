"""End-to-end: run the full app.py (all three tabs) through Streamlit AppTest
on mock data and assert it renders with no exception and no error blocks."""

import os

import pytest

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
    at.session_state["loaded_profile"] = None
    at.session_state["active_ticker"] = "AAPL"
    at.run()
    assert not at.exception

    remove = [b for b in at.button
              if (b.label or "").strip() == "Remove my portfolio"]
    assert remove, "no way to remove an uploaded portfolio"

    remove[0].click().run()
    assert not at.exception
    assert at.session_state["loaded_profile"] is not None, "did not return to a sample"
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
    # this test failed by flagging itself, the same way DEPLOY.md's secret-scan
    # command matches the grep inside DEPLOY.md.
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
