import os
import sys

import pytest

# Make the project importable (data_layer, portfolio_metrics, market_data, tabs)
# from any test.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_OPT_IN = {
    # marker -> (cli flag, why it is opt-in)
    "live": ("--live", "hits real yfinance"),
    "llm": ("--llm", "spends real Anthropic API calls"),
    # kaleido 1.x renders Plotly by driving a real Chrome process. Five of
    # these took the offline suite from 4.3s to 14.2s, and they fail wherever
    # Chrome is absent — which is most CI and every Streamlit Community Cloud
    # container. That is an EXTERNAL dependency in exactly the sense the other
    # two markers exist for, so it is declared rather than acquired by
    # accident. report.py is built so its absence degrades the PDF instead of
    # breaking it, and the tests that prove THAT stay offline.
    "pdf": ("--pdf", "renders charts through a real Chrome via kaleido"),
}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: reaches real yfinance; skipped unless --live")
    config.addinivalue_line(
        "markers", "llm: spends real Anthropic API calls; skipped unless --llm")
    config.addinivalue_line(
        "markers", "pdf: renders charts via kaleido/Chrome; skipped unless --pdf")


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False,
                     help="also run tests marked `live` (real yfinance)")
    parser.addoption("--llm", action="store_true", default=False,
                     help="also run tests marked `llm` (real Anthropic API calls, costs money)")
    parser.addoption("--pdf", action="store_true", default=False,
                     help="also run tests marked `pdf` (static chart export; needs Chrome)")


def pytest_collection_modifyitems(config, items):
    for marker, (flag, why) in _OPT_IN.items():
        if config.getoption(flag):
            continue
        skip = pytest.mark.skip(reason=f"{why}; run with {flag}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def offline_by_default(request, monkeypatch):
    """Market data comes from the recorded fixture unless the test is `live`.

    Tests that silently reach Yahoo are non-deterministic and break whenever it
    throttles or serves an unsettled bar — which is precisely how two tests in
    this suite ended up failing. Making offline the default means a network
    dependency has to be declared, not acquired by accident.

    Note `llm`-marked tests still get fixture DATA: the whole point of exercising
    a real model here is that its input is frozen, so any variation in the output
    is the model's, not the market's.
    """
    if "live" in request.keywords:
        monkeypatch.delenv("USE_MOCK_DATA", raising=False)
        monkeypatch.delenv("USE_MOCK", raising=False)
        return
    monkeypatch.setenv("USE_MOCK_DATA", "1")
