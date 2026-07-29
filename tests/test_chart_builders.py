"""Chart builders must produce valid figures on the full mock book — these
render paths were previously only exercised by manual screenshots."""

import json
import os

import data_layer
import portfolio_metrics as pm
import tabs.dashboard as dash

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fixture():
    port = json.load(open(os.path.join(BASE, "mock_portfolio.json")))
    tickers = [p["ticker"] for p in port["positions"]]
    ctx = data_layer.get_context_batch(tickers)
    df = pm.position_values(port, ctx)
    sect = pm.sector_breakdown(df, port)
    w = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()}
    spy = data_layer.get_benchmark_history("SPY")
    return ctx, df, sect, w, spy


def test_donut_builder():
    _, _, sect, _, _ = _fixture()
    fig = dash._donut(sect, "$")
    assert len(fig.data) == 1
    assert set(fig.data[0].labels) >= {"Technology", "Commodities"}


def test_heatmap_builder_masks_diagonal():
    ctx, *_ = _fixture()
    corr = pm.correlation_matrix(ctx)
    fig = dash._heatmap(corr)
    z = fig.data[0].z
    assert z.shape == (7, 7)
    # diagonal is masked to NaN so the trivial 1.0s don't dominate the scale
    import numpy as np
    assert np.isnan(np.diag(z)).all()


def test_perf_line_builder():
    ctx, _, _, w, spy = _fixture()
    perf = pm.performance_vs_benchmark(ctx, w, spy)
    fig = dash._perf_line(perf)
    assert len(fig.data) == 2
    assert {t.name for t in fig.data} == {"Your portfolio", "S&P 500 (SPY)"}
