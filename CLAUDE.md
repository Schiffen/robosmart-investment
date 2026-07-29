# CLAUDE.md — RoboSmart Investment

Streamlit app: upload a stock portfolio (CSV) and get three tools — a **Portfolio
Dashboard**, a **Bull vs Bear** multi-agent LLM debate, and an **OLS factor-model**
breakdown of a stock's daily move. Educational university project. Not investment advice.

> This file exists to override `~/Downloads/CLAUDE.md`, which describes a different
> project entirely (a CX Email Triage Agent on the TS Agent SDK). Nothing in that file
> applies here — no SPEC.md, no subagent router, no action-layer hooks.

## Environment — read this first

**Use `.venv/bin/python` (3.12). Never the system `python3` (3.14) — pandas 2.2.3
segfaults on it.**

```bash
.venv/bin/streamlit run app.py
.venv/bin/python -m pytest
```

## Run modes

Two independent axes, resolved per call in `run_mode.py`. `USE_MOCK` sets both;
`USE_MOCK_DATA` / `USE_MOCK_LLM` override their own axis and beat it.

| Env | Market data | AI |
|---|---|---|
| *(none)* | live yfinance | live Anthropic |
| `USE_MOCK=1` | recorded fixture | recorded |
| `USE_MOCK_DATA=1` | recorded fixture | live |
| `USE_MOCK_LLM=1` | live yfinance | recorded |

`USE_MOCK_DATA=1` is the mode for prompt iteration: the model's input is frozen, so an
output change is attributable to the prompt rather than to the market moving.

No API key at all ⇒ recorded AI regardless of flags.

## Commands

```bash
.venv/bin/python -m pytest                    # 133 tests, fully offline, ~5s
.venv/bin/python -m pytest --live             # + parity checks against real yfinance
.venv/bin/python -m pytest --llm              # + groundedness vs the real model (spends credit)
.venv/bin/python -m market_data.refresh       # re-record the offline fixture
.venv/bin/python -m market_data.refresh TSLA  # ...plus extra tickers
```

The suite is **offline by default**: a network dependency must be declared with a
`@pytest.mark.live` / `@pytest.mark.llm` marker, never acquired by accident. Two tests
previously failed exactly because they reached Yahoo silently.

## Architecture

```
app.py                  Streamlit shell: sidebar, session state, 3 tabs
run_mode.py             resolves live-vs-recorded for data and LLM
portfolio.py            CSV -> portfolio dict (Contract A)
data_layer.py           Contract-B facade; dispatches to a provider PER CALL
market_data/live.py       yfinance (production)
market_data/fixture.py    replay of a recorded snapshot
market_data/refresh.py    records the snapshot, validates before writing
portfolio_metrics.py    pure portfolio math — NO streamlit import, ever
factor_model.py         OLS market/sector/idiosyncratic decomposition — also pure
agents/llm.py           shared Anthropic client (recorded-first)
agents/debate.py        5-call Bull/Bear/Judge engine
agents/explainer.py     residual-only news explainer
prompts/*.txt           externalised system prompts — rules live HERE, not in code
tabs/*.py               render only; all numbers come from the pure modules
theme.py                shared design tokens
```

## Invariants — do not break these

1. **Contract B keys are always present**, `None` when missing, never omitted. Frozen in
   `INTEGRATION_CONTRACT.md` §1.
2. **`clean_history` runs at the fetch boundary.** Yahoo serves the newest bar with
   O/H/L/V but a NaN Close until it settles. Every consumer ends on `.iloc[-1]`, so one
   unguarded NaN blanks the entire app — price, technicals, returns, weights, beta, risk
   tiles, perf chart, waterfall. Fix it once at the fetch, never per-consumer.
3. **`current` is the last SETTLED close.** Everything stays close-to-close so portfolio
   beta and the attribution waterfall reconcile against the same SPY series.
4. **One benchmark source** — `data_layer.get_benchmark_history`. The dashboard and the
   factor model both use it so their numbers cannot disagree (`INTEGRATION_CONTRACT.md` §3).
5. **News fields are always text.** `published` arrives as a Unix epoch int from
   `yf.Ticker().news` and an ISO string from `yf.Search`; it is normalised in the data
   layer. These strings go into prompts, so a stray int crashes an agent.
6. **`portfolio_metrics.py` and `factor_model.py` import no Streamlit.** This is what
   makes the analytics layer portable to any frontend. Keep it that way.
7. **Prompts own the rules.** Personas, citation requirements and the "no clear cause
   found" escape hatch live in `prompts/*.txt`, not in Python.

## Working conventions

- **Never commit unless explicitly asked.**
- Exploratory project — no backward-compat obligations; schemas may change.
- Before claiming something works, run it. Spot-check against real data.
- When an LLM output is wrong, strengthen the prompt first. Escalate to multi-pass only
  after a prompt fix has been tried and observed to fail.

## Current state

133 tests passing offline, 10 live-parity, 16 model-groundedness. App verified end to end
in all three modes against both live Yahoo and the fixture.

**Known outstanding:** the `ANTHROPIC_API_KEY` in `.env` is unrotated (`DEPLOY.md` step 0);
`.env` is gitignored, and the real key is not in git history. `statsmodels` is pinned but
imported nowhere (~151 MB with scipy). `mock_context.json` (372 KB) is loaded by nothing at
runtime. Not yet deployed — a React + FastAPI migration is under consideration, which would
replace `app.py`/`tabs/`/`theme.py` (~1,220 lines) and move Hugging Face from the Streamlit
SDK to the Docker SDK; the ~2,365 lines of analytics and all tests would carry over intact.
