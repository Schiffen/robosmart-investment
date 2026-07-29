# RoboSmart Investment 📈

An AI‑assisted portfolio analysis app: upload your stock portfolio (CSV) and get three tools — a **Portfolio Dashboard**, a **Bull vs Bear** multi‑agent debate, and an **OLS factor‑model** breakdown of a stock's daily move.

**Live app:** <https://robosmart-investment-proj.streamlit.app/>

**Source:** <https://github.com/Schiffen/robosmart-investment>

> ⚠️ Educational university project. **Not investment advice.**

---

## Screenshots

| Dashboard | Bull vs Bear | What Happened Today |
|---|---|---|
| _![dashboard](docs/screenshot_dashboard.png)_ | _![debate](docs/screenshot_debate.png)_ | _![attribution](docs/screenshot_attribution.png)_ |

## Features

- **Portfolio Dashboard** — total value, P&L, sector allocation with concentration warnings, correlation matrix of daily returns, portfolio beta (with R²), volatility / max drawdown / effective‑holdings, and performance vs the S&P 500.
- **Bull vs Bear** — three LLM agents (Bull, Bear, Judge) debate a holding across five rounds. Every claim must cite a number from the data; the Judge returns a verdict, a confidence score, and three concrete falsifiers.
- **What Happened Today** — an OLS factor model decomposes the day's move into market / sector / company‑specific parts; the LLM then explains *only* the residual from news, and is allowed to answer "no clear cause found."

## Architecture

```
app.py                 # Streamlit shell: sidebar, session state, 3 tabs (Person 1)
portfolio.py           # CSV -> portfolio dict, with validation (Person 1)
run_mode.py            # resolves live-vs-recorded for market data and the LLM
data_layer.py          # Contract-B facade; dispatches to a provider per call
market_data/live.py    #   yfinance (production)
market_data/fixture.py #   replay of a recorded snapshot (offline)
market_data/refresh.py #   records the snapshot: python -m market_data.refresh
theme.py               # shared dark design system used by every tab
portfolio_metrics.py   # pure, tested portfolio math (Person 2)
tabs/dashboard.py      # dashboard UI (Person 2)
factor_model.py        # OLS market/sector/idiosyncratic decomposition (Person 4)
agents/llm.py          # shared LLM client (mock-first)
agents/debate.py       # 3-agent Bull vs Bear engine (Person 3)
agents/explainer.py    # residual-only news explainer (Person 4)
prompts/               # externalized prompt templates (Persons 3 & 4)
tabs/debate.py         # debate UI (Person 3)
tabs/attribution.py    # waterfall + explanation UI (Person 4)
tests/                 # unit + AppTest suite
docs/                  # 5-page summary + video script (Person 5)
```

## Setup (copy‑paste)

```bash
git clone <your-repo-url>
cd robosmart
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Option A — fully offline: recorded market data AND recorded AI. No key, no network.
USE_MOCK=1 streamlit run app.py

# Option B — live data + live LLMs:
cp .env.example .env         # then put your key in .env
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py

# Option C — frozen data, real model. The input can't move, so an output change
# is attributable to the prompt. The useful mode for prompt iteration.
USE_MOCK_DATA=1 streamlit run app.py
```

`USE_MOCK` sets both axes; `USE_MOCK_DATA` / `USE_MOCK_LLM` override their own and beat it.
The sidebar always states the resolved mode and the snapshot date, so recorded data is never
mistaken for live.

Re-record the offline snapshot (validated before it is written):

```bash
python -m market_data.refresh              # the demo book
python -m market_data.refresh TSLA PLTR    # plus extras
```

### Tests

```bash
pytest              # 133 tests, fully offline, ~5s — the default
pytest --live       # + parity checks against real yfinance
pytest --llm        # + groundedness checks against the real model (costs API credit)
```

The suite is offline by default: a network dependency has to be declared with a marker,
not acquired by accident.

## API keys & secrets

The LLM tabs need an `ANTHROPIC_API_KEY`, loaded from the environment — **never hardcoded**. Copy `.env.example` to `.env` (git‑ignored). On Hugging Face Spaces, add it under **Settings → Variables and secrets → New secret** (`ANTHROPIC_API_KEY`). **No secrets are committed in this repo** (verify with `git log -p | grep -i ANTHROPIC` → no matches). The Dashboard tab needs no key.

## Sample CSV

`sample_portfolio.csv` (ships in the repo, so a grader never has to invent a portfolio):

```csv
ticker,shares,cost_basis,sector
NVDA,12,150.00,Technology
AAPL,30,175.00,Technology
JNJ,25,170.00,Healthcare
CASH,5000,0,
```
Columns are case‑insensitive; `sector` is optional (looked up if omitted); a `CASH` row sets the cash balance; duplicate tickers merge at weighted‑average cost.

## Team — who built what

| # | Member | Slice |
|---|---|---|
| 1 | Core | `app.py`, `portfolio.py`, `data_layer.py`, deployment, integration |
| 2 | Dashboard | `portfolio_metrics.py`, `tabs/dashboard.py` |
| 3 | Bull vs Bear | `agents/debate.py`, `tabs/debate.py`, `prompts/*` |
| 4 | Attribution | `factor_model.py`, `agents/explainer.py`, `tabs/attribution.py` |
| 5 | Docs / PM | `docs/`, this README, the demo video |

## Limitations

Betas are unstable and regime‑dependent; R² is low for many stocks; yfinance news is thin and lagging; correlation of daily returns understates tail dependence; LLMs can be fluent, confident, and wrong, and the debate's confidence score is not calibrated; the performance chart is a hypothetical constant‑weight backtest with no costs or slippage. Full discussion in [`docs/summary_document.md`](docs/summary_document.md).

## ⚠️ Not investment advice

RoboSmart is an educational project. Nothing here is a recommendation to buy or sell any security.
