"""End-to-end UI test: run the actual dashboard through Streamlit's AppTest
harness on mock data and assert it renders without exception."""

import os

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "_preview_app.py")

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


def test_dashboard_renders_without_exception(monkeypatch):
    monkeypatch.chdir(BASE)                       # so open("mock_portfolio.json") resolves
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, f"App raised: {at.exception}"
    # 4 headline tiles + 4 risk tiles
    assert len(at.metric) >= 8
    # The concentrated demo book must trip concentration warnings. These render
    # through theme.notice() rather than st.warning: st.warning is
    # aria-live="assertive" and re-announces on every rerun, interrupting a
    # screen reader with a message that has not changed.
    notices = sum(m.value.count("data-notice='warn'")
                  for m in at.markdown if isinstance(m.value, str))
    assert notices >= 1
    # no st.error blocks means every section rendered cleanly
    assert len(at.error) == 0


def test_empty_portfolio_shows_friendly_state(monkeypatch, tmp_path):
    # Point the app at an empty portfolio; it must show an info state, not crash.
    monkeypatch.chdir(BASE)
    app = f"""
import sys; sys.path.insert(0, {BASE!r})
import streamlit as st
from tabs.dashboard import render
render({{"positions": [], "cash": 0.0, "currency": "USD"}})
"""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(app, default_timeout=30).run()
    assert not at.exception
    assert len(at.info) >= 1
    assert len(at.error) == 0
