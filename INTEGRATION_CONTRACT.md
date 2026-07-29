# RoboSmart — Integration Contract (shared conventions)

One page the whole team aligns on so the five slices merge cleanly and the app
reads as one product. Proposed by Person 2 off the Day‑0 plan. **Frozen — change
only by team agreement.**

## 1. Data contract (frozen field names)

**Contract A — portfolio** (`parse_portfolio` → dashboard):
`{"positions": [{"ticker": str, "shares": float, "cost_basis": float, "sector": str}], "cash": float, "currency": "USD"}`

**Contract B — `get_context(ticker)`** (consumed by tabs 1, 2, 3): keys always
present, `None` for missing, never omitted —
`ticker, company_name, sector, sector_etf, price.{current,prev_close,day_change_pct}, returns.{1d,5d,1m,ytd}, fundamentals.{pe,forward_pe,market_cap,profit_margin,revenue_growth,debt_to_equity}, technicals.{rsi_14,sma_50,sma_200,atr}, news[{title,publisher,published,link}], benchmarks.{SPY,<sector_etf>,VIX}, history` (1y daily OHLCV DataFrame).

Everyone builds against **`mock_context.json`** (7 tickers incl. GLD) until P1's real layer lands.

## 2. Tab entry points (fixed signatures)

```python
from tabs.dashboard    import render as render_dashboard   # render_dashboard(portfolio: dict)
from tabs.debate       import render as render_debate      # render_debate(context: dict)
from tabs.attribution  import render as render_attribution # render_attribution(context: dict)
```
Session state: `st.session_state.portfolio` (dict), `st.session_state.active_ticker` (str). Tabs 2 & 3 receive `get_context(active_ticker)`.

## 3. Benchmark data — ONE source

SPY and sector‑ETF history come from **`data_layer.get_benchmark_history(symbol)`** (cached, `@st.cache_data(ttl=900)`). Person 2 (beta/perf/risk) and Person 4 (factor model) both use it — no independent yfinance SPY fetches, so the numbers reconcile.

## 4. Estimation conventions

- **Lookback: 252 trading days.** - **Returns: daily simple returns** (`close.pct_change()`). - Betas are OLS slopes on those returns.
- P2's dashboard beta = the **portfolio's** market beta; P4's `beta_mkt` = a **single stock's** (residualized vs sector). Different scopes — the doc must say so.

## 5. Shared visual system — `theme.py`

All tabs `import theme`. No private palettes.
- Colours: `theme.SURFACE/INK/INK_2/MUTED/GRID/AXIS`, status `GOOD/WARN/SERIOUS/BAD`, `CATEGORICAL` (fixed order), `DIVERGING` (blue→gray→red).
- `theme.style_fig(fig)` on every Plotly figure. `theme.badge(text, kind)` for strength/likelihood/side pills. `theme.fmt_money/fmt_pct/signed_color` for consistent formatting.
- **Green = up/good/bull; Red = down/bad/bear** everywhere.

## 6. UI rules (all tabs)

- **Dark‑mode friendly** (charts render on `theme.SURFACE`).
- **No raw JSON shown to the user, ever.**
- Never crash a tab: wrap sections in `try/except → st.error`; use `.get()` with fallbacks.
- **"Not investment advice"** — once in `app.py` footer (app‑level), plus in the doc and README.

## 7. Ownership (nobody edits another's file)

app/data/deploy = P1 · dashboard = P2 · debate = P3 · attribution = P4 · docs/video/README = P5. `theme.py` is shared; changes go through a quick team OK.
