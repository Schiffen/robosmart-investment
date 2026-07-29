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
