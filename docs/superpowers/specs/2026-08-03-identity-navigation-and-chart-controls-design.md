# Identity, navigation and chart controls — design

**Date:** 2026-08-03
**Status:** approved for planning
**Scope:** five coupled workstreams, one unit of work

---

## 0 · What this changes and why

The app is correct and measured but carries three defects that a demo will hit:

1. Four of its five charts offer a **box-zoom with no reset**, which on touch is a trap.
2. It ships under a name (`RoboSmart Investment`) that **none of its logo assets carry**.
3. It has **no explanation of itself** — a grader opening it cold gets four unlabelled
   views and no statement of what each one computes.

Plus two additions the data already supports: a sector comparison and a compare-ticker
picker.

**Constraint that outranks everything below:** 199 offline tests pass in ~5s. Nothing here
may reduce that number. Every new surface gets test cover (§6).

---

## 1 · Identity — rename and mark placement

### 1.1 The rename

Product becomes **RoboSmart Debate Club**, matching the shipped marks.

Verified: no test asserts the product-name string, so this is a mechanical change.

| File | Site |
|---|---|
| `app.py` | `set_page_config(page_title=)`, `st.logo()`, sidebar masthead, `st.title()`, footer caption, module docstring |
| `prompts/explainer.txt` | line 1 |
| `prompts/analyst.txt` | line 1 |
| `README.md` | title, closing disclaimer |
| `theme.py` | module docstring |
| `.streamlit/config.toml` | header comment |
| `CLAUDE.md` | title and prose |

`PRODUCT.md:131` records the name as "not declared immutable" — this supersedes it. Add a
line there noting the change and the date.

### 1.2 Where each mark goes

Placement follows `LOGOS.md`'s own rules. Both marks are namespace-complete standalone SVG
with outline-path lettering and no font references, so they render identically everywhere.

| Location | Mark | Size | Rationale |
|---|---|---|---|
| Sidebar masthead | `seal.svg` | 44px | 1:1, survives the narrow rail. `LOGOS.md` explicitly bans the mirror in a horizontal bar. |
| Browser tab | `seal.svg`, base64-injected | 32px | See §1.4 — `page_icon` will not reliably take an SVG. |
| Bull vs Bear empty state | `mirror.svg` | 190px tall | The mark *depicts the feature*: a claim answered by its reflection. |
| First-run / empty portfolio | `mirror.svg` | 190px tall | Per `LOGOS.md`'s own placement table. |
| Judge's verdict panel | `rose.svg` (new, §1.3) | 28px corner stamp | Seal is above its 72px minimum here; drop to the centre mark. |

Loading is via `base64` `data:` URI read server-side, never an external file reference —
Community Cloud will not serve a linked asset reliably.

**Not doing:** the seal as a background texture. `LOGOS.md` forbids the seal on busy grounds
and forbids rotating it. Only the rose is used decoratively (§1.3).

### 1.3 Two asset defects to repair

**`rose-min.svg` does not exist.** `LOGOS.md` line 43 instructs "drop to the centre mark
alone (`rose-min.svg` in the symbol set)" — there is no symbol set and no such file. The
centre mark is a `<g>` of paths inside `seal.svg`. Extract it to `logos/rose.svg` +
`logos/rose-on-light.svg`, same two-ink rule as its parents.

**The contrast table in `LOGOS.md` measures against surfaces this app does not have.** It
cites `#0B0E11` ground, `#141A20` panel, `#1C242C` raised. The app's real surfaces are
`PAGE #0d0d0d`, `SURFACE #1a1a19`, and the page **composite `#222530`** — the last being
the one that has already caused a real AA failure in this codebase (`MUTED`, 5.41 → 4.27:1).

Re-measure ink `#E6EDF3` against all three real surfaces and rewrite the table in
`LOGOS.md`. A logotype is non-text under WCAG (3:1 floor), so this is very unlikely to fail
— but the file must not carry numbers measured against a palette that isn't ours, because
the next person will trust them.

### 1.4 Favicon mechanism

`st.set_page_config(page_icon=)` does not reliably accept SVG. Set the title there; inject
the favicon separately as a base64 `data:` `<link rel="icon">`.

`app.py:66` currently passes `page_icon="assets/robosmart-mark.svg"` — verify in a live
browser whether that tab icon actually renders today. If it does not, this is a latent bug
being fixed, not a preference.

### 1.5 The mirror's idea, applied to Bull vs Bear

The mirror is ROBOSMART over a hard rule with its reflection falling away beneath. That is
literally the debate: every claim answered by its opposite.

Compose the Bull and Bear columns as two fields **reflected about a central rule** rather
than two identical bordered boxes. This closes the open thread in `CLAUDE.md`
("the two sides are still visually identical bordered boxes … it is the screen the demo
video shows off").

Constraint: must not introduce a second card system. Reuse the existing panel token
(`RADIUS_PANEL`) and the established lit-from-above treatment; the reflection is expressed
through **orientation and the shared rule**, not through a new component.

---

## 2 · Chart interaction

### 2.1 The bug

`theme.py:239` sets `displayModeBar: False` and `scrollZoom: False`. Nothing sets
`dragmode`, so Plotly's cartesian default — **box zoom on drag** — is active on every
cartesian figure, with the modebar suppressed so **no reset control exists**. Double-click
resets but is undiscoverable.

On touch this is worse: dragging is also how the page scrolls, so a user scrolling past a
chart zooms it instead and cannot get out.

The modebar was suppressed for a sound reason (7 tab stops per chart; ~24 of ~40 focus
stops on the Dashboard were plumbing). **Do not re-enable it.** The fix is authored
controls.

### 2.2 Chart-by-chart decision

| Builder | File | Type | Zoom meaningful? | Action |
|---|---|---|---|---|
| `_perf_line` | `tabs/dashboard.py:124` | Scatter, 1y series | **Yes** | `dragmode="pan"` + range presets (§2.3) |
| `_heatmap` | `tabs/dashboard.py:63` | 8×8 Heatmap | No | `dragmode=False` |
| `_contribution_bar` | `tabs/dashboard.py:84` | Categorical Bar | No | `dragmode=False` |
| `_waterfall` | `tabs/attribution.py:59` | 4-bar Waterfall | No | `dragmode=False` |
| `_donut` | `tabs/dashboard.py:41` | Pie | N/A | no change |
| sector comparison | new (§3) | Scatter, series | **Yes** | same treatment as `_perf_line` |

**Turning zoom off on four charts is most of the bug fix.** Only two charts get controls.

### 2.3 The control

Time-range presets, rendered as `st.segmented_control` beneath the chart:

```
[1M] [3M] [6M] [YTD] [● 1Y]
```

- **`1Y` is the home view and the reset.** Always visible, always one tap. There is no
  separate hidden reset state to explain.
- Real Streamlit widgets: keyboard-accessible, in tab order, ≥44px tap targets. Three to
  five tab stops replacing what would have been seven modebar buttons.
- `scrollZoom` stays `False` — the chart must never steal page scroll on mobile.
- Selection is held in `st.session_state` per chart id, so it survives reruns (the app
  reruns on every sidebar touch).

### 2.4 Declared home ranges

Every chart gets an **explicit authored range** rather than Plotly autorange, so "the focus
point each visualization starts with" is a declared value that reset returns to, not an
emergent one.

Where a range is derived from data (the series' own first/last date), it is computed once
in the builder and recorded in the figure layout.

### 2.5 Reset semantics

Two mechanisms, belt and braces, because Streamlit's preservation of Plotly UI state across
reruns must be verified rather than assumed:

1. `uirevision` in the figure layout, bound to a session-state token. Changing the token
   makes Plotly discard user axis interaction and revert to the layout ranges.
2. The `key=` argument on `st.plotly_chart` (present in the installed 1.60 signature) as the
   remount fallback.

**Verify empirically in a browser which is actually needed** before shipping both. Do not
carry redundant machinery on an assumption.

---

## 3 · Sector comparison

### 3.1 What it is

In **What Happened Today**: the active stock, its sector ETF, and SPY, all normalised to
100 at the window start. It answers the question that view already asks — was this move the
stock, its sector, or the market? — and reconciles visually with the waterfall's three
components (market / sector / idiosyncratic).

Data is already in Contract B: `sector_etf`, plus `get_benchmark_history(symbol)`.
**No new plumbing.**

### 3.2 The degenerate case — this is the important part

`market_data/live.py:285` is `etf = SECTOR_ETF.get(sector, "SPY")`. Any ticker whose sector
is unmapped or absent gets **`sector_etf = "SPY"`**.

Verified against the recorded fixture — **6 of 18 tickers** hit this:

| Ticker | Sector | sector_etf |
|---|---|---|
| BND, GLD, TLT, VNQ, VTI, VXUS | `Unknown` | **SPY** |

Every fund. The `diversified_global` profile is largely funds.

Verified live as well: `GLD` and `SPY` both return `benchmarks = ['SPY','VIX']` — the
contract already collapses the duplicate key, so the condition is detectable without
string-matching the ETF symbol.

**Required behaviour:** when the sector ETF resolves to SPY, draw **two lines, not three**,
and state why in the caption — e.g. *"GLD has no sector classification, so it is compared
against the market only."* Never draw SPY twice. Never silently hide the chart.

### 3.3 Live/offline asymmetry

Verified live: `XLI`, `XLU`, `XLRE`, `XLB` all fetch cleanly (251 rows, 0 NaN closes) —
but **none are in the recorded fixture**, because no recorded ticker maps to them.

This is safe as-is: `refresh.py:220-228` derives the benchmark set from the recorded
contexts' own `sector_etf` values, so any ticker added later brings its sector ETF with it.
No action required. Recorded here so a future session does not "fix" it.

### 3.4 Compare-ticker picker

Verified live: `data_layer.get_context` resolves tickers absent from the fixture
(`BA`→XLI, `NEE`→XLU, `PLD`→XLRE, `BRK-B`→XLF) and raises cleanly on bad input
(`TickerNotFoundError` for unknown, `ValueError` for empty).

Behaviour must differ by run mode, and say so:

| Mode | Input | Failure |
|---|---|---|
| Live data | free text, any ticker | `TickerNotFoundError` → inline message naming the symbol |
| Recorded data | constrained to the 18 recorded tickers | not reachable |

An unconstrained text input that silently fails in `USE_MOCK=1` is unacceptable — that is
the mode the demo runs in.

---

## 4 · About dialog

`st.dialog` (verified present in 1.60), opened from a sidebar button.

**Not a fifth router pill** — the router is already four items and is the tightest thing on
a phone (§5.3).

Contents:

1. **What this is** — one paragraph, and the not-advice statement.
2. **The four views**, each with what it computes and what it shows:
   - *Dashboard* — holdings, weights, sector mix, correlation, contribution, 1y performance
   - *Ask the analyst* — tool-using agent; every figure comes from a tool call, and the
     "How I worked this out" trace is what makes that visible
   - *Bull vs Bear* — five-call debate, two personas and a judge
   - *What Happened Today* — OLS decomposition into market / sector / idiosyncratic
3. **How to navigate** — the router, the sample investor books, uploading a CSV
   (with the column format), the stock selector.
4. **Reading the freshness line** — close-to-close, last settled close, what
   "Recorded snapshot" means.

Copy rule: any app-authored string containing two `$` must go through `fmt_money_md`.
This has already bitten the dashboard's cash-reconciliation caption once.

---

## 5 · Mobile

### 5.1 Tap-outside dismisses the sidebar

**Feasibility is unverified.** `backdrop` and `scrim` strings exist in Streamlit's bundle
but may belong to the dialog component rather than the sidebar.

Verify first, in a real browser at 390px, by inspecting the DOM:

- **If a clickable backdrop element exists** → pure CSS/behaviour, trivial.
- **If not** → zero-height `st.components.v1.html` with a listener reaching
  `window.parent.document`. `st.markdown(unsafe_allow_html=True)` strips `<script>`, so
  this is the only route short of a CCv2 component.

If the fallback is needed it must be inert on failure: height 0, wrapped, and unable to
affect anything else on the page.

### 5.2 Correlation heatmap at 390px

An 8×8 matrix with ticker labels on both axes is unreadable on a phone. Needs a smaller
label treatment or horizontal scroll within its panel. Decide against a rendered result,
not in the abstract.

### 5.3 Router overflow

Four pills with Material Symbol icons at 390px — verify whether it wraps, scrolls or
clips. Clipping is the only unacceptable outcome.

### 5.4 New controls

The range presets (§2.3) and the About dialog are built mobile-first: ≥44px targets, and
the preset strip must wrap rather than clip.

### 5.5 Existing guards

`theme.py:560` (≤1150px → 2-across) and `theme.py:575` (≤720px → stack) already exist and
are correct. New multi-column layouts must not reintroduce the 50%-floor defect those
comments describe — a headline number that ellipsis-clips is quietly wrong.

---

## 6 · Testing

Every workstream gets cover. Offline suite must stay green and must not get slower in a way
that matters.

| Area | Test |
|---|---|
| Rename | AppTest asserts title and masthead read "RoboSmart Debate Club" |
| Logo assets | each SVG parses as XML, has a `viewBox`, contains no `<text>`/font reference/external href; the only diff between a file and its `-on-light` twin is the ink value |
| Rose extraction | `rose.svg` parses and its paths match the corresponding group in `seal.svg` |
| Contrast | ink `#E6EDF3` re-measured against `PAGE`, `SURFACE`, composite `#222530`; asserted ≥3:1 |
| `dragmode` | every cartesian builder asserts its expected `dragmode` — this is the regression guard for the actual bug |
| Home ranges | each chart declares an explicit range; assert it is present and finite |
| Range presets | AppTest: selecting `3M` narrows the range; selecting `1Y` restores the declared home exactly |
| Sector comparison | 3 traces for a mapped ticker (AAPL→XLK); **2 traces for GLD/BND/TLT/VNQ/VTI/VXUS**, and SPY never appears twice |
| Compare picker | offline, constrained to recorded tickers; unknown ticker surfaces the error rather than raising |
| About dialog | opens; contains one entry per router view |
| Money copy | any new caption with two `$` goes through `fmt_money_md` (extends `test_model_output_safety.py`) |
| Metric count | existing AppTest metric-count assertions still hold — this caught a real regression before |

**Live-marked (`--live`)**: sector-ETF history fetches for the full `SECTOR_ETF` map,
asserting non-empty and no NaN closes. Must carry `@pytest.mark.live`; the suite is offline
by default and a network dependency must never be acquired by accident.

---

## 7 · Verification before any completion claim

Browser verification is required, not optional, and must cover **both run modes**:

- desktop and 390px mobile
- `USE_MOCK=1` **and** live data — the defect in §3.2 was invisible in the fixture-only
  check and only surfaced under live inspection
- all four views
- charts: confirm dragging no longer zooms where zoom is disabled, and that `1Y` restores
  the declared home view exactly

No claim that a visual change works until it has been seen rendered, in the state being
claimed. This codebase has twice recorded a measurement taken in the wrong state as a
general fact.

---

## 8 · Explicitly out of scope

- React/FastAPI migration — unchanged, still the user's call
- `DEPLOY.md` rewrite (documents the dead Hugging Face path)
- `docs/summary_document.pdf` rewrite
- `docs/video_script.md` re-script — **but note it will be further stale after this work**,
  since it already describes a UI that no longer exists
- Any change to `portfolio_metrics.py` or `factor_model.py`. The analytics layer imports no
  Streamlit and this work must not change that.

---

## 9 · Invariants this work must not break

From `CLAUDE.md`, the ones this work comes near:

- **#6** — `portfolio_metrics.py` / `factor_model.py` import no Streamlit
- **#7** — prompts own the rules; the rename touches prompt headers only, no rule changes
- **#10** — all model output reaches the page through `theme.safe` / `safe_md`
- **#4** — one benchmark source, `data_layer.get_benchmark_history`. The sector comparison
  uses it, so its numbers cannot disagree with the dashboard or the factor model.
