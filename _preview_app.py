"""_preview_app.py — dev-only preview harness for the Dashboard slice.

Renders `tabs/dashboard.py` standalone on the mock portfolio: no sidebar, no
LLM tabs, no network — the fast inner loop Person 2 used while building the
dashboard. It is NOT part of the shipped app (P1's `app.py` does the real
wiring); the AppTest suite points here to prove the dashboard renders cleanly
on mock data. Safe to delete before submission (see DASHBOARD_SLICE_README.md).
"""

import json
import os
import sys

# Make the project root importable regardless of how the harness is launched.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from tabs.dashboard import render as render_dashboard

st.set_page_config(
    page_title="RoboSmart · Dashboard preview", layout="wide", page_icon="📈"
)

with open("mock_portfolio.json") as f:
    portfolio = json.load(f)

render_dashboard(portfolio)
