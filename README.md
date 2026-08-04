# RoboSmart Debate Club

An AI‑assisted portfolio analysis app. Bring a stock portfolio — upload a CSV, build one by
hand, or answer a short questionnaire and have an example book drafted for you — then explore
it through four views: a **Portfolio Dashboard**, a tool‑using **analyst agent**, a **Bull vs
Bear** multi‑agent debate, and an **OLS factor‑model** breakdown of a stock's daily move.
Everything the app currently knows can be exported as a branded **PDF**.

**Live app:** <https://robosmart-investment-proj.streamlit.app/> ·
**Licence:** [MIT](LICENSE) · **Python:** 3.12

> ⚠️ **Educational university project. Not investment advice.** Nothing here is a
> recommendation to buy or sell any security. The drafted example books are demonstrations
> of the mechanics, not suggestions — see [Drafted books](#drafted-books-are-demonstrations).

---

## Screenshots

| Dashboard | Bull vs Bear | What Happened Today |
|---|---|---|
| ![dashboard](docs/screenshots/dashboard.png) | ![debate](docs/screenshots/debate.png) | ![attribution](docs/screenshots/attribution.png) |

## What it does

**Portfolio Dashboard** — total value, P&L, sector allocation with concentration warnings, a
correlation matrix of daily returns, portfolio beta (with R²), volatility / max drawdown /
effective holdings, and performance against the S&P 500. The lede names the single holding
that caused today's move.

**Ask the analyst** — a tool‑using agent with **seven tools** (portfolio summary, day
contributions, risk metrics, correlations, stock‑move decomposition, stock details, and a
pure `simulate_trade`) and a bounded reasoning loop. It is deliberately given **no portfolio
data in its system prompt**: every figure it states has to come back from a tool call, and
the "How I worked this out" panel shows each call it made. It declines advice questions
rather than answering them.

**Bull vs Bear** — three LLM agents (Bull, Bear, Judge) debate one holding across five calls.
Every claim must cite a number from the data; the Judge returns a verdict, a confidence
score, the weakest claim on each side, and three concrete falsifiers.

**What Happened Today** — an OLS factor model decomposes the day's move into market /
sector / company‑specific parts, and the LLM then explains *only* the residual from news. It
is allowed to answer "no clear cause found." A rebased one‑year comparison of the stock, its
sector ETF and SPY sits alongside it.

**PDF export** — from the header, next to the Guide. The report carries the analysis, not
just the tables: holdings, the debate (both cases, the verdict, the falsifiers), the factor
decomposition and five figures. Built with reportlab + matplotlib, so it needs no browser
and produces identical output locally and on Streamlit Community Cloud.

## Quickstart

**Python 3.12 is required.** pandas 2.2.3 segfaults on 3.14.

```bash
git clone https://github.com/Schiffen/robosmart-investment
cd robosmart-investment
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Option A — fully offline: recorded market data AND recorded AI. No key, no network.
USE_MOCK=1 streamlit run app.py

# Option B — live data + live model:
cp .env.example .env         # then put your key in .env
streamlit run app.py

# Option C — frozen data, real model. The input can't move, so an output change is
# attributable to the prompt. The mode to use while iterating on prompts.
USE_MOCK_DATA=1 streamlit run app.py
```

### Run modes

Two independent axes, resolved per call in `run_mode.py`. `USE_MOCK` sets both;
`USE_MOCK_DATA` / `USE_MOCK_LLM` override their own axis and beat it. With no API key at
all, the AI is recorded regardless of flags. The sidebar always states the resolved mode and
the snapshot date, so recorded output can never be mistaken for live.

| Env | Market data | AI |
|---|---|---|
| *(none)* | live yfinance | live Anthropic |
| `USE_MOCK=1` | recorded fixture | recorded |
| `USE_MOCK_DATA=1` | recorded fixture | live |
| `USE_MOCK_LLM=1` | live yfinance | recorded |

Re-record the offline snapshot (validated before it is written):

```bash
python -m market_data.refresh              # the demo book
python -m market_data.refresh TSLA PLTR    # plus extras
```

## Getting a portfolio in

Three producers, **one validator**. CSV upload, the hand‑built book and the drafted book all
pass through `portfolio.build_portfolio`, so a rule can never hold on one path and not
another.

**1 — Upload a CSV.** [`fixtures/sample_portfolio.csv`](fixtures/sample_portfolio.csv) ships
in the repo so a reader never has to invent one:

```csv
ticker,shares,cost_basis,sector
NVDA,12,150.00,Technology
AAPL,30,175.00,Technology
JNJ,25,170.00,Healthcare
CASH,5000,0,
```

Columns are case‑insensitive; `sector` is optional (looked up if omitted); a `CASH` row sets
the cash balance; duplicate tickers merge at weighted‑average cost.

**2 — Build one by hand** in the full‑page builder, from a curated 41‑ticker shelf.

**3 — Draft an example book** from a seven‑item investor questionnaire. Each answer maps to a
numeric bound (equity weight, defensive floor, beta ceiling, single‑stock cap, position cap,
holding count, concentration), and the bounds merge by **intersection** — so "resolve stated
tolerance against stated behaviour toward the more cautious" falls out of the arithmetic
rather than being a special case. An empty band is not an error; it means the answers are
irreconcilable, which the app surfaces as a **tension**. Tensions are computed in pure Python
against `portfolio_metrics`, so each names a number you can go and check on the Dashboard a
moment later — and they name both sides and stop, because saying which way to resolve one
would be advice.

The questionnaire's shape is researched rather than improvised (Grable & Lytton, MiFID II,
the FCA's FG11/05): no 1–10 risk slider, no neutral rung on the risk items, no income or
net‑worth questions, and nothing pre‑selected. The reasoning is written up in
[`docs/PRODUCT.md`](docs/PRODUCT.md) and in `CLAUDE.md`.

### Drafted books are demonstrations

A drafted book lands in an **editable table**, not in your portfolio, until you press the
button. The generator returns **weights, never shares or a cost basis** — and is not merely
asked not to, it is never given prices. `from_weights` derives shares from the settled close,
so a model‑authored share count (which would imply a model‑authored price, directly under a
computed book total) is impossible by construction.

## Architecture

```
app.py                    Streamlit shell: sidebar, session state, header, 4 views
brand.py                  the marks: seal / mirror / rose, inlined as data: URIs
about.py                  the Guide dialog
theme.py                  shared design tokens + the model-output boundary (safe/safe_md)

portfolio.py              Contract A: validate_rows / build_portfolio / from_weights
book_source.py            where the book came from: profile / upload / built / drafted
shelf.py                  the curated 41-ticker universe the builder draws on
book_spec.py              the investor questionnaire, its bounds, and the tensions
profiles.py               the shipped sample books

data_layer.py             Contract B facade; dispatches to a provider PER CALL
market_data/live.py         yfinance (production)
market_data/fixture.py      replay of a recorded snapshot
market_data/refresh.py      records the snapshot, validates before writing
market_data/fixtures/       the recorded snapshot itself
run_mode.py               resolves live-vs-recorded for data and the model

portfolio_metrics.py      pure portfolio math — NO streamlit import, ever
factor_model.py           OLS market/sector/idiosyncratic decomposition — also pure

agents/llm.py             shared Anthropic client (recorded-first)
agents/debate.py          5-call Bull/Bear/Judge engine
agents/explainer.py       residual-only news explainer
agents/analyst.py         tool-using agent: manual tool-use loop, bounded iterations
agents/tools.py           the analyst's 7 tools — thin wrappers over the tested analytics
agents/book_builder.py    drafts an example book from the questionnaire
prompts/*.txt             externalised system prompts — rules live HERE, not in code

tabs/*.py                 render only; all numbers come from the pure modules
tabs/build.py             the full-page portfolio builder
reporting/document.py     the PDF: cover, tables, debate, figures
reporting/charts.py       those figures, via matplotlib — no browser, draws only
reporting/panel.py        the export dialog in the header

fixtures/                 canned inputs the app ships with: the demo book, the recorded
                          debate, the synthetic context, the sample CSV
profiles/                 five sample portfolios selectable from the sidebar
logos/                    the shipped marks + LOGOS.md, their placement contract
docs/                     project documentation — see docs/README.md
tests/                    the offline suite
```

Two rules carry most of the weight. **The analytics layer imports no Streamlit**, which is
what makes it portable to any frontend. And **all model output reaches the page through
`theme.safe` / `theme.safe_md`** (and `reporting.document.pdf_safe` for the PDF, which is a
different escaping problem) — model text is untrusted input to both renderers.

The behavioural contract between the data layer and its consumers is frozen in
[`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md).

## Tests

```bash
pytest              # 660 tests, fully offline, ~22s — the default
pytest --live       # + parity checks against real yfinance (678 total)
pytest --llm        # + groundedness checks against the real model (costs API credit)
```

The suite is **offline by default**: a network dependency has to be declared with a
`@pytest.mark.live` / `@pytest.mark.llm` marker, never acquired by accident. An autouse
fixture in `tests/conftest.py` forces `USE_MOCK_DATA=1` for every unmarked test, so `--live`
is the only way to reach Yahoo.

## API keys & secrets

The AI views need an `ANTHROPIC_API_KEY`, loaded from the environment — **never hardcoded**.
Copy `.env.example` to `.env` (git‑ignored). On Streamlit Community Cloud, secrets arrive
through `st.secrets` rather than the environment; `app.py`'s `_adopt_streamlit_secrets()`
bridges them, and two tests guard that bridge. The Dashboard needs no key, and the whole app
runs with `USE_MOCK=1` and no key at all.

No secrets are committed in this repo.

## Documentation

| Document | What it is |
|---|---|
| [`docs/README.md`](docs/README.md) | index of everything below |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | positioning, principles, the user it is built for |
| [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md) | the frozen data contracts |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | deployment |
| [`logos/LOGOS.md`](logos/LOGOS.md) | the marks and where each one is allowed to go |
| [`CLAUDE.md`](CLAUDE.md) | the standing engineering briefing: invariants, traps, and what only a live run caught |

## Workstreams

A five‑person course project. Ownership as originally split:

| Slice | Files |
|---|---|
| Core & integration | `app.py`, `portfolio.py`, `data_layer.py`, `market_data/`, deployment |
| Dashboard | `portfolio_metrics.py`, `tabs/dashboard.py` |
| Bull vs Bear | `agents/debate.py`, `tabs/debate.py`, `prompts/` |
| Attribution | `factor_model.py`, `agents/explainer.py`, `tabs/attribution.py` |
| Docs & PM | `docs/`, this README, the demo video |

The analyst agent, the portfolio builder, the PDF export and the design system were added
after that split and are not covered by it.

## Limitations

Betas are unstable and regime‑dependent, and R² is low for many stocks; yfinance news is thin
and lagging; correlation of daily returns understates tail dependence; LLMs can be fluent,
confident and wrong, and the debate's confidence score is **not calibrated**; the performance
chart is a hypothetical constant‑weight backtest with no costs or slippage; the questionnaire
is not a suitability assessment and deliberately asks nothing about income or net worth. Full
discussion in [`docs/summary_document.md`](docs/summary_document.md).

## Licence

[MIT](LICENSE). Educational project — **not investment advice.**
