# RoboSmart — Person 2 slice: Portfolio Dashboard

This is **Team Member 2's** vertical slice, built to the fixed Day‑0 contract.
It runs **standalone on synthetic mock data** — no network, no API key — so it
was developed without waiting on anyone.

## What's here

| File | Owner | Purpose |
|---|---|---|
| `portfolio_metrics.py` | **You (P2)** | Pure, Streamlit‑free, unit‑tested finance: values, P&L, sectors, concentration, correlation, beta (+R²), performance vs SPY. |
| `tabs/dashboard.py` | **You (P2)** | `render(portfolio)` — renders only; all numbers come from `portfolio_metrics`. |
| `tests/test_portfolio_metrics.py` | **You (P2)** | 18 tests asserting the *finance*, not just that it runs. |
| `data_layer.py` | **Person 1 (mock stand‑in)** | Synthetic, correlated 1y OHLCV. Replace with P1's real yfinance version at integration. |
| `mock_portfolio.json` | P1 (stand‑in) | Demo portfolio matching Contract A. |
| `_preview_app.py`, `_shot.py`, `.streamlit/config.toml` | dev only | Local preview harness — **delete before submission** (P1's `app.py` does the real wiring). |
| `requirements-dev.txt` | dev | Merge these pins into P1's master `requirements.txt`. |

## Run it

```bash
pip install -r requirements-dev.txt
python portfolio_metrics.py     # prints the full breakdown from the terminal
pytest -q                       # 18 tests, all green
streamlit run _preview_app.py   # live dashboard on mock data
```

## Integration checklist (when P1's data_layer is ready)

1. Delete `data_layer.py` (mock), `mock_portfolio.json`, `_preview_app.py`, `_shot.py`, `.streamlit/config.toml`.
2. `tabs/dashboard.py` already imports `from data_layer import get_context_batch` — no change needed once P1's real module is on the path.
3. Beta & performance fetch SPY through `portfolio_metrics._fetch_benchmark_history` (yfinance). Ask P1 to `@st.cache_data` the SPY fetch, or let P1 pass SPY history in — either works.
4. Keep the function **signatures** exactly as‑is; the contract is frozen.

## Design decisions (defend these — see the project doc for full Q&A)

- **Weights are on invested equity, cash excluded** — concentration/correlation/beta are equity‑risk concepts.
- **Correlation of daily returns, not prices** — prices trend together and fake correlation.
- **Beta is regressed on the portfolio's own return series** (same series as the chart) → beta *and* R² are consistent with the performance line.
- **Performance chart is a labeled hypothetical backtest**, not a realized track record.

_Not investment advice._
