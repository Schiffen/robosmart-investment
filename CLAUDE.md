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

**159 tests passing offline** (~7s), plus 10 live-parity (`--live`) and 16
model-groundedness (`--llm`). Verified end to end in all three modes, locally and on the
deployed app.

- **Live:** https://robosmart-investment-proj.streamlit.app/
- **Repo:** https://github.com/Schiffen/robosmart-investment (account `Schiffen`)

### Deployment notes that contradict older docs

Hugging Face **removed the Streamlit SDK** (`sdk` accepts only `gradio|docker|static`) and
now requires a **PRO subscription** for Docker Spaces. Deployment moved to Streamlit
Community Cloud. `DEPLOY.md` still describes the dead HF path and needs rewriting. A
`Dockerfile` exists and works, but is currently unused.

Streamlit Cloud exposes secrets via `st.secrets`, **not** env vars — `app.py`'s
`_adopt_streamlit_secrets()` bridges them. Without it the deployed app silently serves
recorded AI output while looking healthy. Two tests guard this.

### Git identity — per repo, not global

This repo commits as `Schiffen <schiffen@post.bgu.ac.il>` via `.git/config` and
authenticates with `~/.ssh/id_ed25519_robosmart` pinned through `core.sshCommand`. The
global config is a *different* account and must stay untouched. Never run
`gh auth switch` for this project — it is global.

### Open threads

| Item | State |
|---|---|
| Delete old `roischiffen/robosmart-investment` | still public; needs `delete_repo` scope or the browser |
| Rotate `ANTHROPIC_API_KEY` once more before submission | current key leaked into a session transcript (local only) |
| Rewrite `docs/summary_document.pdf` | stale — predates the data layer, profiles and deployment. **20% of the grade** |
| Record the 3–5 min demo video | script exists at `docs/video_script.md`; not recorded |
| Submit the course survey | **5% of the grade**, free points |
| Deadline | **still unknown — ask before planning large work** |

### Grading reality (drives prioritisation)

50% architecture and technical implementation · 20% AI creativity *beyond trivial use* ·
20% documentation · 5% defense · 5% survey. **UI/design is not a graded line item** — it
serves the defense and the "complete product" impression only.

The AI layer is currently a **prompt chain, not an agent**: five sequential calls for the
debate, one for the explainer, zero tools and zero loops. Adding a tool-using chat agent
is the single change that targets the 20% criterion directly, and the course brief names
exactly that as its worked example.

### Design phase (in progress)

`PRODUCT.md` is written (Impeccable `init`). Key recorded decisions: beginner-primary with
evaluator-legible depth; **substance preserved, structure free to change**; positioning is
**execution-led** — the user's stated differentiator is design, motion and frontend craft.

That collides with the stack: Streamlit custom components render in isolated iframes and
cannot call each other, so orchestrated motion is unreachable. `motion-framer` and
`gsap-scrolltrigger` are React-only and cannot run against `tabs/*.py`. The React + FastAPI
migration question is therefore open on the user's own terms, not merely as a preference —
the ~2,365 lines of analytics and all tests would carry over intact.

Impeccable's detector **does** work here (it reads CSS inside Python strings). Current
open findings: `tabs/debate.py:44` and `:181` both use `border-left:3px solid`, flagged as
the side-tab accent border — "the most recognizable tell of AI-generated UIs".
