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
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    at = AppTest.from_file(APP, default_timeout=120).run()
    # find and click the "Start the Debate" button, then re-run
    btns = [b for b in at.button if "Debate" in (b.label or "")]
    if btns:
        btns[0].click().run()
        assert not at.exception
        assert len(at.error) == 0


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
