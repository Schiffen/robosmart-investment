# CLAUDE.md — RoboSmart Debate Club

Streamlit app: upload a stock portfolio (CSV) and get four tools — a **Portfolio
Dashboard**, a tool-using **analyst agent**, a **Bull vs Bear** multi-agent LLM debate, and
an **OLS factor-model** breakdown of a stock's daily move — plus a branded **PDF export** of
whatever the app currently knows. Educational university project. Not investment advice.

*(Renamed from "RoboSmart Investment" on 2026-08-03 to match the shipped marks. The name
lives in `brand.PRODUCT`; a test fails on any stale literal.)*

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
.venv/bin/python -m pytest                    # 660 tests, fully offline, ~21s
.venv/bin/python -m pytest --live             # + parity checks against real yfinance
.venv/bin/python -m pytest --llm              # + groundedness vs the real model (spends credit)
.venv/bin/python -m market_data.refresh       # re-record the offline fixture
.venv/bin/python -m market_data.refresh TSLA  # ...plus extra tickers
```

The suite is **offline by default**: a network dependency must be declared with a
`@pytest.mark.live` / `@pytest.mark.llm` marker, never acquired by accident. Two tests
previously failed exactly because they reached Yahoo silently.

> **Running without `USE_MOCK` does NOT give you a live test run.** `tests/conftest.py` has
> an **autouse** fixture (`offline_by_default`) that sets `USE_MOCK_DATA=1` for every test
> not marked `live`. `env -u USE_MOCK … pytest` therefore runs 100% on the fixture while
> looking like a live run — it even finishes in the same ~4s, which is the only tell.
> **`--live` is the only way to reach Yahoo.** This wasted a round trip; do not repeat it.

## Architecture

```
app.py                  Streamlit shell: sidebar, session state, header, 4 views
brand.py                the marks: seal / mirror / rose, inlined as data: URIs
about.py                the Guide dialog
reporting/document.py     the PDF: cover, tables, debate, figures
reporting/charts.py       those figures, via matplotlib — NO browser, draws only
reporting/panel.py        the export dialog in the header
run_mode.py             resolves live-vs-recorded for data and LLM
portfolio.py            Contract A: validate_rows / build_portfolio / from_weights
                        + parse_portfolio, now only the CSV adapter
book_source.py          where the book came from: profile/upload/built/drafted
shelf.py                the curated 41-ticker universe the builder draws on
book_spec.py            the investor questionnaire, its bounds, and the tensions
agents/book_builder.py  drafts an example book from the questionnaire
tabs/build.py           the full-page builder (the only new Streamlit module)
data_layer.py           Contract-B facade; dispatches to a provider PER CALL
market_data/live.py       yfinance (production)
market_data/fixture.py    replay of a recorded snapshot
market_data/refresh.py    records the snapshot, validates before writing
portfolio_metrics.py    pure portfolio math — NO streamlit import, ever
factor_model.py         OLS market/sector/idiosyncratic decomposition — also pure
agents/llm.py           shared Anthropic client (recorded-first)
agents/debate.py        5-call Bull/Bear/Judge engine (on_stage reports real progress)
agents/explainer.py     residual-only news explainer
agents/tools.py         the analyst agent's 7 tools — thin wrappers over the tested
                        analytics; NOTHING here computes finance
agents/analyst.py       tool-using agent: manual tool-use loop, MAX_ITERATIONS bound
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
8. **The analyst agent is given no portfolio data in its prompt.** Every figure it can
   state has to come back from a tool call. Passing the book into the system prompt as a
   convenience would destroy the one property that makes it trustworthy.
9. **`simulate_trade` is pure and never mutates session state.** The agent models a
   trade; only the user applies one. A test asserts the caller's portfolio is unchanged —
   if it ever fails, "what if I sold everything?" sells everything.
10. **A portfolio enters `ss.portfolio` only through `portfolio.build_portfolio`.**
   CSV, hand-built book and drafted book all pass the one validator, so a rule
   can never hold on one path and not another. `_load(portfolio, source=...)` is
   the single writer, and `source` is required so a new producer cannot forget
   to say what it is.
11. **The generator returns WEIGHTS, never shares, dollars or a cost basis** — and
   is not merely asked not to, it is never given prices. `from_weights` derives
   shares from the settled close. A model-authored share count would imply a
   model-authored price, and "Invested" sits directly under a computed book
   total.
12. **All model output reaches the page through `theme.safe`/`safe_md`.** `safe` for raw
   HTML we control (escapes quotes, emits `$` as `&#36;`), `safe_md` for markdown prose
   (`quote=False` — escaping apostrophes breaks the entity and renders `&#x27;`).

## Working conventions

- **Never commit unless explicitly asked.**
- Exploratory project — no backward-compat obligations; schemas may change.
- Before claiming something works, run it. Spot-check against real data.
- When an LLM output is wrong, strengthen the prompt first. Escalate to multi-pass only
  after a prompt fix has been tried and observed to fail.

## Current state

**660 tests passing offline** (~21s), and 678 with `--live`. The suite grew from 305 with the
builder below; the CSV boundary in particular had **zero** coverage before it.

### Building a portfolio without a CSV (2026-08-04)

Three ways a book now arrives instead of one: upload a CSV, type it into the builder, or
answer a seven-item investor questionnaire and have an **example book** drafted from a
curated shelf. A drafted book is a demonstration so a reader has something of their own to
explore with — never a recommendation — and it lands in the editable table, not in the
portfolio, until the reader presses the button. That human step is what keeps the feature
on the right side of the line the analyst agent's refusal behaviour already draws.

The AI layer is now **three** shapes: a fixed chain (five debate calls, one explainer), a
tool-using agent, and a constrained generator scored against numeric bounds.

**Why the questionnaire is seven items and shaped the way it is.** Researched against
Grable & Lytton, MiFID II, and the FCA's FG11/05 — which reviewed eleven real
risk-profiling tools and found **nine flawed**. Hence: no 1–10 risk slider (the risk each
number stands for is undefined, so user and system do not share a meaning), no neutral rung
on the two risk items (a non-answer scored as a mid-range attitude manufactures a moderate
investor who does not exist), no income or net-worth questions (real capacity questions, but
asking them would imply a suitability assessment that is explicitly not being made), and
nothing pre-selected (a pre-selected answer is an answer the reader did not give).

> One research finding corrected a premise worth not repeating: "people overstate their risk
> tolerance in a bull market" is **not** what the evidence says. FinaMetrica's panel of
> 341,782 responses across 2007–2012 found measured *tolerance* barely moved (SD 1.86%
> against the S&P's 17.27%); what moves is risk *perception*. So the design does not correct
> for a drifting trait — it anchors every risk question in concrete money-and-percent
> magnitudes so perception has less room to move the answer.

**Bounds, not vibes.** Each answer maps to a numeric bound (`equity_weight`,
`defensive_floor`, `beta_max`, `single_stock_max`, `position_max`, `holdings`, `hhi_max`),
and they merge by **intersection** — which *is* the "resolve stated tolerance against stated
behaviour toward the more cautious" rule rather than a special case for it. An empty band is
not an error; it means the answers are irreconcilable, which is a tension to surface.

**Tensions are arithmetic, not opinion.** Computed in pure Python against
`portfolio_metrics`, so each names a number the reader can go and check on the Dashboard a
moment later. They name both sides and stop — saying which way to resolve one would be
advice. This is FG11/05's own named good practice.

#### What only a live run caught

The offline suite was green through all of these. They are the argument for running the
thing against the real model rather than trusting the tests.

- **`max_tokens` caps thinking AND text together.** At 2500 roughly one live draft in three
  came back truncated mid-object and fell through to the rule allocator; at 4096, one in
  two. `agents/analyst.py` already used 8000 for this exact reason. At 8000: 4/4.
- **A unit mismatch between the generator and every measurement in the app.** Allocation
  weights summed to `100 − cash_pct`, so a holding capped at 15% of the whole book was
  printed by the dashboard as 17.65% of the *invested* money — `portfolio_metrics` excludes
  cash from every weight (finance assumption 1). The tension rules read that same
  cash-excluded figure, so **the app flagged a breach against a book it had just generated**.
  Weights are now a share of the invested money and sum to 100, cash outside them.
- **An equity ceiling that was stated and never enforced.** "Shares: 75% to 95%" went into
  the prompt, but `defensive_floor` for a long horizon is zero, so a live draft came back
  100% equity and nothing caught it. The ceiling now derives a floor, once, in `constraints()`.
- **The position cap gave up instead of doing what it could.** When the cap was
  arithmetically unreachable — a 15% cap cannot hold over five holdings summing to 100 — the
  guard returned the allocation *untouched*, and a live draft came out with one holding at
  45%. It now spreads evenly, which is the allocation that minimises the largest holding, and
  says so.

#### What an adversarial review pass caught that 590 green tests did not

Two reviewers (a Streamlit-mechanics one and a correctness one, deliberately
non-overlapping) fuzzed the generator across the answer space. The offline suite was
green throughout all of these.

- **The single-share cap was enforced NOWHERE that mattered.** `_coerce` — the live-model
  path — never applied it at all; every reference lived in the rule allocator. 62% of
  fuzzed model books breached it, and the test that "covered" it only ever ran against the
  allocator. A beginner answering "None" could be handed four individual company shares.
- **Two app-authored sentences asserted arithmetic the next line undid.** "reduced the
  single-share portion to what your experience answer allows" sat over a **100% NVDA**
  book, because the rescale was followed by a renormalise that scaled it straight back;
  "raised bonds and gold to the N%" sat over a book at a third of that, because the floor
  step ended by calling the position cap. This codebase draws a hard line between a claim
  the tests enforce and prose nobody checked — those put unchecked claims on the *checked*
  side of it, which is worse than the model doing it, because the app controls this text.

  Both were symptoms of one shape: a chain of one-shot fixups, each appending a message and
  then having its work undone by the next. Replaced by **`_settle`** — adjust in a loop
  because the constraints genuinely interact, then **measure the final book and report only
  the bounds it misses.** Nothing is announced as done; success is silent. Two tests now
  pin that in both directions: no shortfall may be reported that the book does not have,
  and no bound may be missed without being named.
- **"Would like included" was a whitelist, not a tilt.** A control labelled *"Leave empty
  for no preference"* cut 41 tickers to six on one click. That was the root cause of the
  worst output: with one category left there was often nothing to satisfy the caps *with*.
  Inclusion now only reorders; **only exclusions narrow the shelf.**
- **"Start over" reset the table and nothing else** — every radio stayed selected, cash
  stayed put, and the draft button stayed enabled, because Streamlit lets a surviving
  widget key beat `value=`/`index=`. It even *looked* right.
- **The tension numbers described the drafted book, not the edited one** — `_measure` read
  `builder_draft`, which is deliberately never written from the editor. Gut the table,
  commit, and the PDF asserted a beta about a book that no longer existed. Those numbers
  are the feature's whole claim to be checkable arithmetic; attached to the wrong book they
  are worse than none.
- **`except ImportError` around the builder takeover was the wrong class.** A failed import
  is evicted from `sys.modules`, so an exception raised *by* `tabs/build.py` at import time
  — the stale-module case this file already documents — would escape at module scope and
  white-screen the app while the sidebar printed a reassuring "Builder unavailable".

#### Two defects found by running the parser rather than reading it

- `parse_portfolio("ticker,shares,cost_basis\nAAPL,,150.00")` returned `shares: NaN`. The
  guard was `if shares <= 0`, and **`nan <= 0` is `False`** — so a NaN-share position entered
  Contract A and `position_values` silently redistributed every other weight around it.
- The CSV example the sidebar **printed** parsed to **$1** of cash while the template it
  offered for **download** parsed to $5,000. Cash reads from the `shares` column. A test now
  regexes that literal out of `app.py` and asserts what it claims.

#### Also in this pass

- **The stock selector moved out of the sidebar** to sit under the router, on the only two
  views that consume it. Streamlit sweeps widget state for widgets not rendered on a run and
  does it at *end* of run, so a keyed picker resets on the **second** view switch — a
  one-switch test passes against the broken version. `ss.active_ticker` + `index=` and no
  `key=` survives; `key="active_ticker"` while assigning to it is a hard
  `StreamlitAPIException`. Gating `_active_context()` also removed a `get_context` fetch from
  two of four views.
- **Cash is editable** in the sidebar at any time, and editing it on a sample book keeps that
  book's identity — measured, cash 5,000 → 500,000 moves *no* weight, so no `expect` claim
  can be invalidated.
- **Provenance** (`book_source.py`). `reporting/panel._book_label()` returned `None` for
  everything that was not a sample profile, and the cover reads
  `subject = profile_label or "Your uploaded portfolio"` — so a built or drafted book would
  have gone out under a cover saying it was uploaded.
- **`st.data_editor` is the same canvas grid as `st.dataframe`** and inherits the exact a11y
  defect this repo rejected `st.dataframe` for: the a11y tree reads `.data`, never
  `.displayData`, so `format="dollar"` paints `$513.84` and announces `513.8399999999999`.
  With **no** `format=` the two are the same string. Also: `num_rows="dynamic"` hashes the
  element id from the *serialized frame*, so a frame that changes value silently drops
  pending edits — the draft is app-owned and written only by explicit actions.
- **The shelf is 41 tickers** (was 18) with hand-authored `category` metadata, because
  yfinance returns `sector == "Unknown"` for **every** fund on it. `refresh.demo_book_tickers()`
  is the union of shelf and profiles, so editing the shelf can never drop a shipped book's
  holding from the fixture.

*(Historical, before the portfolio builder:)* **305 tests passing offline** (~6s) and **323 with `--live`**, plus
model-groundedness (`--llm`). Verified end to end in all three modes, locally and on the
deployed app — and, as of 2026-08-03, in a real browser at 1440px and at an emulated 390px
phone, on **live market data** rather than only on the fixture.

The **analyst agent** (4th view, "Ask the analyst") is built and verified against the live
API: it picks the right tool per question, calls tools in parallel when they're
independent, refuses advice cleanly ("Should I buy more NVDA?" → zero tool calls, offers
the legitimate alternative), and corrected a false premise rather than confabulating
("why am I down?" → "your portfolio actually looks slightly up"). The UI shows every tool
call in a "How I worked this out" panel — that trace is what makes the grounding visible
rather than merely claimed. It is **open by default** as of 2026-08-01, with an
always-visible strip naming which tools ran: collapsed, it was one click from invisible,
and nobody opens an expander during a five-minute demo.

### Design pass 3 — identity, chart interaction, mobile (2026-08-03)

**The product is now `RoboSmart Debate Club`**, matching the shipped marks. The name lives
in **`brand.PRODUCT`** and nowhere else; a test fails on any literal `"RoboSmart Investment"`
in `app.py` / `about.py` / `brand.py`.

**`logos/` + `brand.py`** — seal (masthead 44px, favicon, `st.logo`), mirror (ceremonial),
and **`rose.svg`, newly extracted from the seal** because `LOGOS.md` instructed callers to
use a `rose-min.svg` that never existed. Marks are inlined as base64 `data:` URIs, never
file paths. A test pins the rose's paths to the seal's group so they cannot drift.

`st.logo` previously used `assets/robosmart-mark.svg` while the masthead used the seal —
**two different marks ~90px apart on screen**, which reads as an app that changed its mind,
not as one identity. Only rendering it revealed that. Both are the seal now.

#### The chart-zoom bug — deny-by-default in `style_fig`

Plotly's cartesian default is `dragmode="zoom"` (box-zoom on drag). Nothing ever set it, and
`CHART_CONFIG` suppresses the modebar that would normally **reset** it. So every cartesian
chart zoomed in on drag with **no control anywhere on the page to get back out**. On touch it
was worse: dragging is also how the page scrolls, so scrolling past a chart zoomed it and
trapped you there.

`style_fig(..., zoom=False)` is now the default. Four of five charts have no meaningful zoom
(pie, correlation matrix, categorical bar, 4-bar waterfall) and are inert to drag; only a
real time series opts in, and gets `dragmode="pan"` — reversible by the same gesture.
`theme.range_control` / `range_bounds` provide `1M·3M·6M·YTD·1Y`, where **`1Y` is both the
home view and the reset**, so reset is always visible rather than a hidden state.

> **Streamlit PERSISTS Plotly pan/zoom across reruns.** Every relayout writes the whole
> mutated figure into `WidgetStateManager.elementStates`, keyed on an element id Streamlit
> hashes **from the figure spec**. Switching preset changes the spec → new id → remount →
> pan discarded, so reset *appears* to work perfectly. But pan while already on `1Y` and
> press `1Y`: spec is byte-identical, no remount, **the pan survives the button that exists
> to undo it**. `theme.chart_key()` puts an epoch in `key=` to close this. Verified in a
> live browser — panned to a window starting 5 months before the data, one tap restored the
> exact declared range. Not `uirevision`: Streamlit never reads it; it only "works" by
> perturbing the same spec hash.

#### Mobile

- **The sidebar squeezed rather than overlaid.** Measured at a real 390px: opening it left
  `section.stMain` at **90px**, wrapping the title to one word per line. It is now
  `position: fixed` below 767.98px.
- **Streamlit already ships outside-tap-to-dismiss** (document-level `mousedown`, live below
  767.98px). It works; it was simply invisible, because Streamlit draws no scrim. The scrim
  here is a **`box-shadow: 0 0 0 100vmax`** — an overlay `<div>` would become the mousedown
  target, and a box-shadow cannot take a pointer event at all, so the working handler stays
  untouched by construction.
- Verified at 390px: router wraps to 2 rows, range control fits one row, headline does not
  clip, page never scrolls horizontally, `.rs-table-wrap` scrolls inside its own container.

> **Clear `localStorage` before judging mobile.** `stSidebarCollapsed-<hash>` persists, and a
> stale `false` made the app look like it opens with the sidebar covering the screen and the
> headline clipped. That was self-inflicted, not a defect. Also: `resize_page` alone leaves
> Streamlit's internal width state stale — **emulate a device and reload**, or you will
> measure desktop behaviour and believe it is mobile.

#### Sector comparison, and the collapse that guards it

New in *What Happened Today*: the stock, its sector ETF and SPY, rebased to 100 — the
waterfall's three components over a year instead of a day. No new plumbing; `sector_etf` and
`get_benchmark_history` already existed.

> `live.py:285` is `SECTOR_ETF.get(sector, "SPY")`, so **anything yfinance cannot classify
> resolves to SPY itself** — six of eighteen recorded tickers, i.e. every fund, and
> `diversified_global` is mostly funds. A naive three-line chart plots **SPY twice**, one
> line labelled "its sector". `attrib._sector_etf()` returns None there and the chart
> collapses to two honest lines with a caption saying why. *A fixture-only reading of the
> data would not have surfaced this; it took looking at live behaviour.*

#### About dialog (`about.py`)

`st.dialog` from the sidebar, not a fifth router pill (the router already wraps to 2 rows at
390px). Three non-obvious constraints, all verified:

1. **A dialog does not survive a rerun** — it exists only for the run that calls it, and this
   app reruns on every sidebar touch. Gate on `session_state` and re-assert each run.
2. **`on_dismiss` defaults to `"ignore"`**, closing client-side with *no* rerun — so the flag
   stays set and the dialog reappears, reading as a modal that will not stay shut. Pass a
   callback that clears it.
3. **It renders in a portal, outside `section.stMain`**, so none of this app's CSS reaches
   it. Build dialog content from native widgets, which pick up `config.toml` globally.

#### Also fixed

- `page_icon="assets/…"` resolves against the **process CWD**, not `app.py`, and
  `page_config` swallows the failure in a bare `except` — yielding a silent 404 favicon with
  no exception, no warning, no log line. Absolute paths now. Proven from `cwd=/tmp`.
- `LOGOS.md`'s contrast table measured `#0B0E11`/`#141A20`/`#1C242C` — **surfaces this app
  does not have**. Rewritten against `PAGE`/`SURFACE`/composite, every ratio recomputed here
  rather than taken on trust. It also mis-stated WCAG: SC 1.4.11 **exempts logotypes**, so
  the 3:1 is a house rule, not a conformance obligation.
- `LOGOS.md`'s "only the ink may differ between twins" is **false for the mirror**, which
  also namespaces its gradient/mask ids (`mgd`/`mmd` vs `mgl`/`mml`). It must: both files are
  inlined into one document, and identical ids would collide so one reflection mask would
  win for both. A test caught this the moment it was written.
- `test_model_output_safety` asserted no `<img` anywhere, as a proxy for "no model-authored
  tag survived". The masthead legitimately emits one. The sweep now strips **only** `<img>`
  whose src is an inline SVG data URI — a shape `<img src=x onerror=…>` cannot reach — so
  the guard keeps full strength rather than being widened to pass.

#### PDF export (`report.py` + `report_charts.py`)

"Download PDF" from the **header**, beside the Guide. reportlab + svglib build the
document; **matplotlib** draws the figures. All three are pure Python, so the export is
**not conditional on the environment** — the earlier design made charts optional and that
was wrong: a report without figures is a spreadsheet, and "generate it locally for charts"
cannot be said about a feature whose purpose is that users save and send it.

> **Do not reach for kaleido.** It is the obvious way to rasterise a Plotly figure and it
> fails three ways: 0.2.1 ships no macOS arm64 binary (installs clean, dies at render);
> 1.x refuses Plotly 5.24 through `fig.to_image()`; and 1.x drives a **real headless
> Chrome**, which Community Cloud has not got. That last one left the DEPLOYED export with
> tables and no charts. `report_charts` redraws the same DataFrames with matplotlib — no
> browser, manylinux wheels, all five figures in ~0.5s against kaleido's ~7s.

> `report_charts` is a second **renderer**, never a second source of numbers. Every
> function takes the DataFrame the matching Plotly builder takes. A test parses its
> imports (not its source — the docstring names `portfolio_metrics` while explaining this
> very rule) and fails if it ever imports an analytics module.

> **The cover is `mirror-print-on-light.svg`, generated.** svglib renders paths but
> **drops `<mask>`**, so the real mirror's reflection came out as solid ink — the wordmark
> upside-down beneath itself. LOGOS.md anticipates this ("the first thing a bad
> reproduction loses") and says fall back to the seal; instead the fade is **baked** into
> 26 clipped bands at the alpha the gradient had at that height. Both clipping and
> fill-opacity survive svglib. Regenerate if the source mirror changes.

> Cover positions are **derived from the mark's rendered height**, never hard-coded. The
> first version put the subtitle at a fixed offset and printed "Portfolio report" straight
> through "DEBATE CLUB".

#### Header actions, and the Guide

**Guide** and **Export** live in the header beside the product name, not in the sidebar and
not at the foot of the Dashboard. Both are global — the Guide explains all four views, the
export carries all four — so scoping either to one view misrepresented it, and the export
in particular sat below a full page of charts where nobody looks for an action.

The Guide is a **map**, not prose: the mirror mark, then the four views as a 2x2 card grid
in router order, then numbered steps. A reader's question there is "which of these four do
I want", which is a comparison — and a comparison read down one column of prose is the one
shape that makes it hard.

> **Dialog CSS must be scoped to `[data-testid="stDialog"]`, NOT nested under
> `section.stMain`.** A dialog renders through a portal outside the main section, so the
> house scoping rule matches nothing there and the Guide renders as unstyled default
> output. This is the one place that rule is deliberately set aside (theme.py rule 15).

**The report carries the ANALYSIS, not just the tables.** This was a deliberate correction:
the first version exported holdings and two charts, which is what a spreadsheet does. The
export exists so a user can **save it, send it, and show it to someone who was never in
front of the app** — and on that framing the shareable content is the Bull vs Bear debate
(both cases, strengths, the judge's verdict, confidence, the weakest claim on *each* side,
and the falsifiers) plus the day's factor decomposition. Both are optional; the report
covers whatever the app currently knows. The Dashboard states, before you press Generate,
whether a debate will be included — while you can still go and run one.

> **`report.pdf_safe()` is `theme.safe` for a new medium**, and invariant #10 now has two
> boundaries, not one. reportlab's `Paragraph` parses a small HTML dialect, so a verdict
> containing `P/E < 20 & falling` **raises and kills the export**, and one containing
> `<font color=white>` would be *obeyed*. Do not reuse `theme.safe` here — it emits `&#36;`
> for `$`, correct for Streamlit's LaTeX parser and wrong for reportlab, which has none and
> would print the entity. A hostile-debate test mirrors `test_model_output_safety.py`.

> Model text is flowed through a `Frame`, never `drawString`: model output has no length
> contract and `drawString` neither wraps nor paginates. A test proves content that cannot
> fit opens another page — and finding that test failing is what exposed that the report was
> **silently truncating** claims/falsifiers/explanations to the first 3–4. Those caps are
> gone; an artifact people send onward must not quietly drop analysis.

**305 offline · 323 with `--live`** (was 199/209). *(Now 660 / 678.)*

### Design pass 2 — surfaces and composition (2026-08-01)

The app was correct, accessible and measured, and still read as basic. Diagnosis, which
is the transferable part: **it had exactly one surface.** The plane was painted and the
only things above it were Plotly's own rectangles, so the headline numbers, the prose and
the holdings table all sat on flat black — page → chart, where a designed dark product has
page → panel → raised element. It also had no primary object: nine analyses, one column,
all at content width, type scale ~3× top to bottom.

The session was originally specced as atmosphere (animated aurora, film grain, a hero
masthead). A review argued that was aimed at the wrong layer and was right — **light
behind a flat plane is a lit flat plane.** Atmosphere was cut to a static wash plus a dim
grid, and the effort went to structure:

- **The lede block** — one composed unit, asymmetric 7:5. Total value at display scale in
  JetBrains Mono, today's move beneath it, and the sentence naming the holding that caused
  it (already computed by `pm.day_move_contributions`, previously ~900px down the page).
  Type scale now ~6×. Built on `st.metric`, **not** hand-written HTML — the first version
  used raw markup for display type and the AppTest suite caught it instantly (metric count
  9 → 5), because that count stood for the label/value/delta relationship, the delta's
  direction arrow and the help tooltip. Display scale is a CSS problem.
- **Panels lit from above** — top edge, no full border, bottom shadow. Deliberately not
  the shadcn/Bootstrap card, which applied uniformly reads as a component library. Charts
  paint **no background at all** now, so the panel is the surface and the square-in-round
  corner mismatch cannot occur.
- Radii unified from five near-miss values to three tokens; `.streamlit/config.toml` went
  from 5 theme keys to 28; emoji swept to Material Symbols (notice icons are inline SVG on
  `currentColor` — three distinct *shapes*, and no longer a font the OS picks).
- The debate's empty state draws `STAGES` as a five-step strip instead of ~130px of void
  above a button, from the same tuple that drives real progress so it cannot drift.

**Two latent bugs surfaced only by rendering the result and looking at it:**

1. Every untitled Plotly chart rendered the literal word **"undefined"** as its heading.
   `style_fig` set `title=dict(font=...)` unconditionally, so plotly.py emitted a title
   with a font and no text and Streamlit's wrapper did `String(undefined)`. It had done so
   for a long time, hidden inside the 48px margin reserved for titles.
2. **"Ask the analyst" rendered with none of the design system.** All 44 CSS rules were
   scoped to `[data-testid="stMain"]`, and Streamlit renames that testid to
   `stAppScrollToBottomContainer` on any view using `st.chat_input`. Silent; h1 at 41px
   against 22px everywhere else. **Scope to `section.stMain`** — the class survives the
   rename, the testid does not.

**Streamlit 1.60 ships its own agent skill, version-matched, already on disk:**
`.venv/lib/python3.12/site-packages/streamlit/.agents/skills/developing-with-streamlit/`
— 25 references (`theme.md`, `design.md`, `custom-components-v2.md`), six dashboard
templates and twelve ready-made theme configs. Prefer it over any blog post.

`.claude/agents/` now holds three reviewers with deliberately non-overlapping remits —
`design-director`, `contrast-auditor`, `streamlit-realist` — each instructed to stay out
of the others' territory so their feedback does not collapse into the same generic notes.
They found most of what is listed above. Note they only register at session start.

**Numerical note:** `_aligned_portfolio_returns` wraps its matmul in `np.errstate`. Those
"divide by zero in matmul" warnings were **stale FPU status flags** (matmul doesn't
divide) surfaced by BLAS, not corruption — inputs and outputs verified finite. The
`np.where(isfinite)` guard after it is the part that actually protects correctness.

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
| Rewrite `docs/summary_document.pdf` | stale — predates the data layer, profiles, deployment, the analyst agent AND the 2026-08-01 design pass. **20% of the grade — the biggest single lever left** |
| Record the 3–5 min demo video | `docs/video_script.md` is itself stale: it describes a UI that no longer exists (no lede block, no stage strip, emoji router). Re-script before recording |
| Submit the course survey | **5% of the grade**, free points |
| Deadline | **weeks away** as of 2026-08-01 (user-confirmed). No longer a blocker on planning large work |
| Bull vs Bear confrontation panels | the two sides are still visually identical bordered boxes. Ungraded, but it is the screen the demo video shows off |

### Grading reality (drives prioritisation)

50% architecture and technical implementation · 20% AI creativity *beyond trivial use* ·
20% documentation · 5% defense · 5% survey. **UI/design is not a graded line item** — it
serves the defense and the "complete product" impression only.

The 20% AI criterion is **answered** — this section used to say "the AI layer is currently
a prompt chain, not an agent … adding a tool-using chat agent is the single change that
targets the 20% criterion directly." That work is done and verified (see Current state).
The AI layer is now deliberately **two shapes**: a fixed chain (five debate calls, one
explainer) and a tool-using agent that chooses among seven tools with a bounded loop.

Nothing else in the build buys 20%-criterion points, so remaining effort is better spent
on the **20% documentation** line, which is still stale.

### Design phase (in progress)

`PRODUCT.md` is written (Impeccable `init`). Key recorded decisions: beginner-primary with
evaluator-legible depth; **substance preserved, structure free to change**; positioning is
**execution-led** — the user's stated differentiator is design, motion and frontend craft.

This was recorded as colliding with the stack — *"custom components render in isolated
iframes and cannot call each other, so orchestrated motion is unreachable"* — which made
the React + FastAPI migration look forced rather than preferred. **That collision does not
exist.** It described Components v1. Streamlit 1.60 ships **v2**, which uses Shadow DOM in
the same document, not iframes, so a shared timeline across the page is reachable here.
`gsap-scrolltrigger` was written off as React-only on the same reasoning; GSAP is vanilla
JS and runs fine inside a CCv2 component. (`motion-framer` genuinely is React-only.)

The migration question stays open because it is the user's call, but see PRODUCT.md: no
argument for it currently survives contact with the evidence.

Impeccable's detector **does** work here (it reads CSS inside Python strings). Both
previously-open `border-left:3px solid` findings are closed.

### Design pass — done, and what it settled

A dual-agent critique scored the deployed app **19/40** on Nielsen's heuristics (archived
under `.impeccable/critique/`). The fixes below are applied and verified in a live browser.
The in-page detector went from 9 findings to 4, and all 4 remaining are Streamlit's own
chrome (`.stApp` overflow, sidebar transition, dead maplibregl CSS) — zero app-owned.

- **`theme.safe` / `theme.safe_md` is the model-output boundary.** A judge verdict with
  `$5B … $5B` had the span between the dollar signs eaten by Streamlit's LaTeX parser and
  painted as a code block mid-sentence; model text also flowed unescaped into
  `unsafe_allow_html=True`. `tests/test_model_output_safety.py` pins both halves.
  **Any new app-authored copy containing two `$` needs `fmt_money_md`** — this bit the
  dashboard's own cash-reconciliation caption immediately after the model fix landed.
- **`run_debate(context, on_stage=...)`** reports progress at the five real call
  boundaries. The three `time.sleep(0.7)` calls that faked staging *after* all five calls
  had already returned are gone.
- **`st.segmented_control` router, not `st.tabs`** — `st.tabs` has no selected-index API
  and re-mounted at index 0 on every rerun. Only the selected view renders now (~2/3 less
  per-rerun work).
- **Holdings is a semantic `<table>`**; `st.dataframe` paints to canvas and its a11y
  fallback leaked raw floats regardless of the pandas Styler.
- **Contrast**: loss-red 4.05 → 5.92:1 (now balanced with gain-green's 5.79); waterfall
  connectors 1.24 → 3.24:1; focus ring added to the router, which had none at all.

**Verify colours against the COMPUTED background — and in the STATE you are claiming.**

⚠️ *This paragraph previously asserted the opposite conclusion and was wrong. It is kept
in corrected form rather than deleted, because the wrong version is what stopped the bug
being fixed for two revisions.*

A detector flagged white-on-`#3987e5` at 3.64:1 on primary buttons. This file used to
answer: "Streamlit darkens primaryColor to `rgb(24,96,185)` for the button, where white
measures 6.15:1, so the detector is wrong." Re-measured in the live DOM: the resting
background is `rgb(57,135,229)` — **the declared value, not darkened**. `rgb(24,96,185)`
is Streamlit's **:hover** background. The original measurement sampled a hovered button
and generalised it to the control, and the detector had been right the whole time.

`primaryColor` is now **`#1d74dd`**, where white measures 4.57:1 and passes. The label is
15px/650, which is not WCAG "large text" (≥24px, or ≥18.66px bold), so 4.5:1 is the
applicable threshold and 3:1 was never available.

Second-order trap found while fixing it: **`primaryColor` serves two opposite roles** — a
*fill* behind white on a button, and *ink* on a 10% tint for the selected
`segmented_control` item. Darkening it fixed the button and pushed the router from a
passing 4.85:1 to 3.02:1. One token cannot be both fill and ink; the router's ink is now
decoupled (white on that tint, 17.99:1 measured).

**There are now THREE surfaces to measure against, not two.** `SURFACE #1a1a19`,
`PAGE #0d0d0d`, and the page **composite `#222530`** — what the page actually is at its
lightest once the wash and grid overlay are composited, 4.6× `PAGE`'s luminance. Text on a
panel is safe by construction (the panel gradient only runs darker than `SURFACE`); text
directly on the page is not. `MUTED` failed exactly this way (5.41 → 4.27:1) and is now
`#9d9b94`.

`mock_debate.json` had its evidence strings reformatted from machine field names
(`revenue_growth of 22%`) to spoken phrasing, matching the new prompt rule. Numbers and
claims are unchanged; the file records this in its own `_note` key.

**Bearing on the two open decisions.** The critique found the 19/40 was overwhelmingly
*not* Streamlit's fault — the genuinely stack-blocked list is short (orchestrated motion,
page-load choreography, a semantic grid, branded cold start, URL state, owning the frame),
and everything in P0/P1 was plain Python. Migrating before these fixes would have carried
every defect into React for the same score. Combined with the grading reality above —
**UI/design is not a graded line item** — the migration is hard to justify on grade, and
the 20% AI criterion is the only place a large build still buys points.
