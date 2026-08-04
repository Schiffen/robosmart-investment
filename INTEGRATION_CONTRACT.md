# RoboSmart — Integration Contract (shared conventions)

One page the whole team aligns on so the five slices merge cleanly and the app
reads as one product. Proposed by Person 2 off the Day‑0 plan. **Frozen — change
only by team agreement.**

## 1. Data contract (frozen field names)

**Contract A — portfolio** (`portfolio.build_portfolio` → dashboard):
`{"positions": [{"ticker": str, "shares": float, "cost_basis": float, "sector": str}], "cash": float, "currency": "USD"}`

Contract A now has **three producers** — an uploaded CSV, a book typed into the
builder, and a book drafted from the investor questionnaire — so the rules below
are written out rather than left implied. All three go through
`portfolio.build_portfolio`; nothing else may construct this dict.

| Rule | Detail |
|---|---|
| `ticker` | uppercased and stripped. A blank or `NAN` ticker is **skipped**, not an error |
| `shares` | strictly `> 0` and finite. No short positions, no zero rows. **`nan <= 0` is `False`**, so non-finite is checked separately — a blank CSV cell used to enter Contract A as `shares: NaN` and silently redistribute every other weight |
| `cost_basis` | `>= 0` and finite. **Per-share average cost, never a total.** "Money invested" is always derived as `shares × cost_basis` and is never stored |
| `sector` | optional in the source; resolved by the injected `sector_for` when absent. The builder passes `shelf.sector_of`; the CSV path falls back to a network lookup |
| duplicates | merge to a **weighted-average cost basis** — the same rule `agents.tools.simulate_trade` applies on a buy |
| `CASH` / `$CASH` row | sets the cash balance, and the amount is read from the **`shares`** column. `CASH,5000,0` is five thousand dollars; `CASH,1,5000` is one dollar. Multiple rows accumulate; an unreadable amount leaves cash at zero rather than rejecting the file |
| `currency` | hardcoded `"USD"`; no input path sets anything else |
| `universe` | the builder passes `shelf.tickers()` so a book can always be priced, including offline. The CSV path passes `None` — a user's own file may name anything |

**Generated books return WEIGHTS, never shares.** `portfolio.from_weights`
derives shares from the settled close and sets `cost_basis` to that same price.
Allocation weights are a share of the **invested** money and sum to 100; cash is
a share of the whole book and sits outside them — the same unit
`portfolio_metrics` uses, which excludes cash from every weight it computes.

**Provenance travels with the book.** `st.session_state.portfolio_source` is a
`book_source` record (`profile` / `upload` / `built` / `drafted`) written only by
`app._load`, and read by the identity banner, the sidebar, the export panel, the
PDF cover and the download filename.

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
