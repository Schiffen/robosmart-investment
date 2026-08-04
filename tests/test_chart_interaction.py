"""Chart INTERACTION, as opposed to chart content (test_chart_builders.py).

This file exists because of a bug that was invisible to every other test in the
suite and to every screenshot: Plotly's cartesian default is
`dragmode="zoom"` — box-zoom on drag — and theme.style_fig never set it, while
theme.CHART_CONFIG suppressed the modebar that would normally RESET it.

So every cartesian chart in the app zoomed in on drag with no control anywhere
on the page to get back out. Double-click does reset, but nothing says so. On
touch it was worse than undiscoverable: dragging is also how the page scrolls,
so scrolling PAST a chart zoomed it instead and then trapped the reader there.

Nothing in the rendered FIGURE CONTENT was wrong, which is exactly why content
tests could not see it. The assertions here are about behaviour, and the
`dragmode` test in particular is the regression guard for the original defect.
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

import data_layer
import portfolio_metrics as pm
import tabs.attribution as attrib
import tabs.dashboard as dash
import theme

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _book():
    port = json.load(open(os.path.join(BASE, "fixtures", "mock_portfolio.json")))
    tickers = [p["ticker"] for p in port["positions"]]
    ctx = data_layer.get_context_batch(tickers)
    df = pm.position_values(port, ctx)
    w = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()}
    spy = data_layer.get_benchmark_history("SPY")
    return port, ctx, df, w, spy


def _perf():
    _, ctx, _, w, spy = _book()
    return pm.performance_vs_benchmark(ctx, w, spy)


# --------------------------------------------------------------------------
# The bug itself
# --------------------------------------------------------------------------

def _every_figure():
    port, ctx, df, w, spy = _book()
    return {
        "donut": dash._donut(pm.sector_breakdown(df, port), "$"),
        "heatmap": dash._heatmap(pm.correlation_matrix(ctx)),
        "contribution_bar": dash._contribution_bar(
            pm.day_move_contributions(df, port.get("cash", 0.0)), "$"),
        "waterfall": attrib._waterfall(1.0, 0.5, -0.2, 1.3, "AAPL"),
        "perf_line": dash._perf_line(pm.performance_vs_benchmark(ctx, w, spy)),
    }


@pytest.mark.parametrize("name", ["donut", "heatmap", "contribution_bar",
                                  "waterfall"])
def test_non_series_charts_are_inert_to_drag(name):
    """The four charts with no meaningful zoom must not respond to drag.

    `dragmode=None` here would mean Plotly's default is in force, which IS the
    bug — so None must fail as loudly as "zoom" does.
    """
    dm = _every_figure()[name].layout.dragmode
    assert dm is False, (
        f"{name} has dragmode={dm!r}; expected False. None or 'zoom' means "
        f"drag box-zooms the chart with no modebar to reset it.")


def test_series_chart_pans_rather_than_zooms():
    """The one chart that opts in gets pan, never box-zoom.

    Panning is undone by the same gesture that caused it. Box-zoom is not,
    which is what made the original defect inescapable.
    """
    assert _every_figure()["perf_line"].layout.dragmode == "pan"


def test_scroll_zoom_stays_disabled():
    """A chart that eats the scroll wheel is unusable on a phone."""
    assert theme.CHART_CONFIG["scrollZoom"] is False
    assert theme.CHART_CONFIG["displayModeBar"] is False


def test_style_fig_denies_zoom_by_default():
    """Deny-by-default is the property that fixed four charts with one change.

    If this ever flips, a newly added chart silently inherits the trap.
    """
    import plotly.graph_objects as go
    plain = theme.style_fig(go.Figure(go.Scatter(x=[1, 2], y=[1, 2])))
    assert plain.layout.dragmode is False


# --------------------------------------------------------------------------
# range_bounds — pure, so assertable by equality
# --------------------------------------------------------------------------

@pytest.fixture
def idx():
    return pd.date_range("2025-08-01", "2026-07-31", freq="B",
                         tz="America/New_York")


def test_home_preset_is_the_full_span(idx):
    """RANGE_HOME must be the data's own span, not `today - 365 days`.

    Date arithmetic would drift daily against a frozen fixture and would leave
    a sliver of empty axis, since ~251 trading bars span a 365-day calendar.
    """
    assert theme.range_bounds(idx, theme.RANGE_HOME) == (idx[0], idx[-1])


@pytest.mark.parametrize("preset", ["1M", "3M", "6M", "YTD"])
def test_narrower_presets_are_strictly_inside_home(idx, preset):
    lo, hi = theme.range_bounds(idx, preset)
    assert lo > idx[0] and hi == idx[-1]


def test_presets_are_ordered_by_width(idx):
    widths = [theme.range_bounds(idx, p)[0] for p in ("1M", "3M", "6M")]
    assert widths[0] > widths[1] > widths[2], "presets must widen monotonically"


def test_unknown_preset_falls_back_to_home_rather_than_raising(idx):
    """A stale session-state value must not take out the Dashboard."""
    assert theme.range_bounds(idx, "17Y") == (idx[0], idx[-1])


def test_empty_and_none_index_return_none():
    assert theme.range_bounds(pd.DatetimeIndex([]), "1M") is None
    assert theme.range_bounds(None, "1M") is None


def test_short_series_is_clamped_not_left_with_empty_axis(idx):
    """An x-range reaching past the data renders as a chart that looks broken
    rather than one that is merely short."""
    short = idx[-5:]
    lo, _ = theme.range_bounds(short, "1Y")
    assert lo == short[0]
    lo_1m, _ = theme.range_bounds(short, "1M")
    assert lo_1m == short[0]


# --------------------------------------------------------------------------
# The reset contract
# --------------------------------------------------------------------------

def test_home_preset_restores_both_axes_exactly():
    """"Reset" must be an exact restoration, not a re-autorange.

    Equality rather than approximation is the whole reason range_bounds is
    pure: the claim "1Y returns you to where you started" is checkable.
    """
    perf = _perf()
    first = dash._perf_line(perf, theme.RANGE_HOME)
    dash._perf_line(perf, "1M")                       # wander off
    back = dash._perf_line(perf, theme.RANGE_HOME)    # and back
    assert back.layout.xaxis.range == first.layout.xaxis.range
    assert back.layout.yaxis.range == first.layout.yaxis.range


def test_every_series_chart_declares_explicit_ranges():
    """No autorange on a chart that has a reset button — otherwise the "initial
    view" is emergent and there is nothing exact to return to."""
    fig = dash._perf_line(_perf(), theme.RANGE_HOME)
    assert fig.layout.xaxis.range is not None
    assert fig.layout.yaxis.range is not None
    assert all(np.isfinite(v) for v in fig.layout.yaxis.range)


def test_narrowing_the_window_rescales_y():
    """The point of narrowing. Left on autorange-over-the-full-series, a 1M
    view of a year that ranged 88-140 is a flat line in a tall empty box — the
    reader zooms in and sees LESS."""
    perf = _perf()
    home = dash._perf_line(perf, theme.RANGE_HOME).layout.yaxis.range
    near = dash._perf_line(perf, "1M").layout.yaxis.range
    assert (near[1] - near[0]) < (home[1] - home[0])


def test_declared_ranges_are_primitives_not_pandas_objects():
    """A figure that cannot be serialised is broken for EVERY export path.

    This is a real regression that shipped for one build. `_apply_window` set
    layout.xaxis.range with pandas Timestamps; the browser was fine, because
    Streamlit's own serialiser handles them — but kaleido's raises
    "Type is not JSON serializable: Timestamp", so the performance chart
    silently dropped out of the PDF export while looking perfect on screen.

    Asserted on the layout values directly rather than by trial-serialising the
    whole figure. A blanket "is it JSON-serialisable" check is the obvious
    test and it is the wrong one: plotly figures legitimately carry ndarrays —
    including OBJECT-dtype ones, e.g. the heatmap's text labels — which plain
    json and bare orjson both reject, while the real export path cleans them
    through plotly's own encoder first. Such a test fails on all five charts
    for a reason that has nothing to do with the defect.
    """
    for fig in (dash._perf_line(_perf(), theme.RANGE_HOME),
                dash._perf_line(_perf(), "3M")):
        for v in fig.layout.xaxis.range:
            assert isinstance(v, (str, int, float)), \
                f"x range holds {type(v).__name__}; the export cannot serialise it"


@pytest.mark.pdf
@pytest.mark.parametrize("name", ["donut", "contribution_bar", "perf_line",
                                  "waterfall", "heatmap"])
def test_every_chart_survives_a_real_static_export(name):
    """Ground truth: actually render it through the engine the PDF uses.

    Skipped where the engine is unavailable — which is most CI and every
    Streamlit Community Cloud container, since kaleido 1.x drives real Chrome.
    That is the whole reason report.py treats charts as optional.
    """
    pytest.importorskip("kaleido")
    from reporting import document as report
    png = report._png(_every_figure()[name], width=700, height=350)
    assert png, f"{name} could not be exported"
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"


def test_flat_window_does_not_collapse_to_zero_height():
    """A window where nothing moved must still get a drawable axis."""
    idx = pd.date_range("2026-01-01", periods=40, freq="B",
                        tz="America/New_York")
    flat = pd.DataFrame({"Portfolio": np.full(40, 100.0),
                         "SPY": np.full(40, 100.0)}, index=idx)
    fig = dash._perf_line(flat, theme.RANGE_HOME)
    lo, hi = fig.layout.yaxis.range
    assert hi > lo


# --------------------------------------------------------------------------
# Against REAL market data
#
# Everything above runs on the recorded fixture, and on a synthetic
# `freq="B"` index in the pure-function tests. Neither is what production
# hands this code. A real yfinance index carries market holidays, early
# closes, and a tz-aware DatetimeIndex whose gaps are not weekly-periodic —
# so a window boundary can land on a day that does not exist in the series,
# and `.loc[]` slicing on a half-open window can come back empty in a way a
# regular business-day index never reproduces.
#
# conftest's `offline_by_default` autouse fixture pins USE_MOCK_DATA=1 for
# every test WITHOUT the `live` marker, so these do not run by accident and
# unsetting the environment variable would not be enough to reach Yahoo.
# --------------------------------------------------------------------------

@pytest.mark.live
def test_range_bounds_on_a_real_yfinance_index():
    """Real index: holidays, no fixed periodicity, tz-aware."""
    spy = data_layer.get_benchmark_history("SPY")
    idx = spy.index
    assert len(idx) > 200, "expected ~1y of daily bars"

    assert theme.range_bounds(idx, theme.RANGE_HOME) == (idx[0], idx[-1])
    for preset in ("1M", "3M", "6M", "YTD"):
        lo, hi = theme.range_bounds(idx, preset)
        assert idx[0] <= lo <= hi == idx[-1]
        # The window must actually contain bars. A boundary landing on a
        # holiday must not produce an empty slice.
        assert ((idx >= lo) & (idx <= hi)).sum() > 0, f"{preset} selected no bars"


@pytest.mark.live
def test_every_preset_yields_a_finite_window_on_live_data():
    """The full builder path, on live prices rather than recorded ones."""
    port = json.load(open(os.path.join(BASE, "fixtures", "mock_portfolio.json")))
    tickers = [p["ticker"] for p in port["positions"]]
    ctx = data_layer.get_context_batch(tickers)
    df = pm.position_values(port, ctx)
    w = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()}
    perf = pm.performance_vs_benchmark(
        ctx, w, data_layer.get_benchmark_history("SPY"))
    assert perf is not None and not perf.empty

    for preset in theme.RANGE_PRESETS:
        fig = dash._perf_line(perf, preset)
        assert fig.layout.dragmode == "pan"
        y = fig.layout.yaxis.range
        assert y is not None and all(np.isfinite(v) for v in y), \
            f"{preset} produced a non-finite y range on live data"
        assert y[1] > y[0]


@pytest.mark.live
def test_home_restores_exactly_on_live_data():
    """The reset contract has to hold on the data the app actually serves."""
    spy = data_layer.get_benchmark_history("SPY")
    perf = pd.DataFrame({"Portfolio": spy["Close"] / spy["Close"].iloc[0] * 100,
                         "SPY": spy["Close"] / spy["Close"].iloc[0] * 100})
    first = dash._perf_line(perf, theme.RANGE_HOME)
    dash._perf_line(perf, "1M")
    back = dash._perf_line(perf, theme.RANGE_HOME)
    assert back.layout.xaxis.range == first.layout.xaxis.range
    assert back.layout.yaxis.range == first.layout.yaxis.range
