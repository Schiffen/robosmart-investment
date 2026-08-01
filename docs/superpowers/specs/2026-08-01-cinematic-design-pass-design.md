# Cinematic design pass — surfaces, composition, and a quiet atmosphere

**Date:** 2026-08-01 · **Baseline:** `a7fa997` (199 tests green)
**Scope:** one focused session. Surface only — no analytics, no prompts, no AI behaviour.

> **Revision 1.** This spec originally specified an animated aurora, film grain and a hero
> masthead. A design review argued that was atmosphere applied to the wrong layer, and it
> was right on the evidence. What changed and why is recorded at the end; the reasoning is
> the useful part, so it is kept rather than quietly overwritten.

## Goal

The app is correct, accessible and measured, and it reads as basic. PRODUCT.md records
the user's positioning verbatim: *"the design, the different features, the animations and
motions, and the UX and frontend implementations will be the things that differentiate
us."* This pass makes the surface carry that claim.

**The diagnosis that drives everything below:** the app has essentially one surface. The
page plane is painted, and the only things above it are Plotly rectangles, because
`style_fig` sets `paper_bgcolor=SURFACE`. The four headline numbers, the prose, the
holdings table and the section rules all sit directly on flat black. A designed dark
product has page → panel → raised element; this has page → chart. That missing hierarchy
is the actual reason it reads as basic, and no amount of light behind it helps: light
behind a flat plane produces a lit flat plane.

Second diagnosis: the page has no primary object. Nine analyses, one column, all at
content width, all separated by the same hairline, each followed by a caption in the same
grey. The type scale runs about 3× top to bottom. Uniform weight across a narrow scale
range is what "basic" means structurally.

## Hard constraints

1. **The measured colour contract does not change.** `GOOD` 5.91:1, `BAD` 5.92:1, `FOCUS`
   10.2:1, `CONNECTOR` 3.24:1 stay exactly as they are.
2. **Content sits on opaque surfaces.** Nothing behind a card may reach the text.
3. **Invariant 10 holds.** All model output reaches the page via `theme.safe` / `safe_md`.
4. **Motion follows the recorded rule.** Duration inversely proportional to firing
   frequency; nothing decorative replays on a rerun; `prefers-reduced-motion` disables
   every new animation.
5. **199 tests stay green**, offline, in ~5s.
6. `portfolio_metrics.py` and `factor_model.py` still import no Streamlit.
7. **Do not reverse a documented decision without saying so.** `theme.py` rule 6 records
   that the product name was cut from 44px/700 because it outweighed the user's own
   portfolio value: *"on an Operate surface the user's money is the headline; the
   product's name is a label."* That decision stands.

## Correction to the record

PRODUCT.md states custom components "render inside isolated iframes and cannot call one
another, so orchestrated cross-component motion … [is] **not achievable in the current
stack**", and uses it as an argument for migrating to React. That was true of Components
v1. Streamlit 1.60 ships **Components v2**, verified present:

```
st.components.v2.component(name, *, html=None, css=None, js=None, isolate_styles=True)
```

Streamlit's bundled reference: *"`window.parent.postMessage(...)` — v1 iframe
communication; **CCv2 does not use iframes**."* Shadow DOM, same document, theme piped in
as `--st-*` custom properties. Real JS animation is reachable in Streamlit today. This
pass does not need it, but the migration case rests on less than PRODUCT.md assumes.

## Work items, in build order

### 1 · Unify the radius scale (`theme.py`) — do this FIRST

Five radii are currently doing similar jobs: `999px` (badge, confidence bar), `6px`
(focus), `10px` (notice, weakest-claim box, key-uncertainty box), `14px` (verdict,
attribution card), plus Streamlit's own on `st.container(border=True)`. Adding a card
system on top of that makes incoherence worse, not better.

Declare one scale as tokens and use them everywhere:

- `RADIUS_PILL` `999px` — badges, bars
- `RADIUS_PANEL` `10px` — every standard panel
- `RADIUS_HERO` `14px` — the lede block and the verdict card only

### 2 · An authored surface system (`theme.py`)

The obvious recipe — 12px radius, 1px border all round, inset top highlight, soft drop
shadow, hover lift — is the shadcn/Bootstrap card verbatim, and applied uniformly it reads
as a component library rather than a product.

Author one variant instead: **panels lit from above.** A 1px top edge at ~7% white, *no*
full border, a bottom-weighted shadow, and an opaque vertical-gradient fill. Panels then
read as raised by light rather than as outlined boxes.

Applies to `[data-testid="stMetric"]`, `.rs-table-wrap`, and the debate/attribution cards.

Two known collisions to handle rather than ship into:

- **`.stPlotlyChart` must not simply be wrapped.** It already paints its own
  `paper_bgcolor=SURFACE` rectangle with square corners; a rounded bordered card around it
  produces a corner mismatch on all four corners. Either set `paper_bgcolor` transparent
  and let the panel be the surface, or exclude charts. Not both.
- **`.rs-notice` already carries** `border-radius:10px` and a 1px border inline. The panel
  rule would double the border and fight the radius.

### 3 · The lede block (`tabs/dashboard.py`) — the structural move

One composed unit at the top of the dashboard, ~480–520px, on the app's only hero-weight
surface, asymmetric (~7:5) rather than four equal columns:

- **Left:** total value at genuine display scale (3.5–4rem vs ~2.25rem today), with
  today's move immediately beneath it *in the same visual group* rather than as a sibling
  tile. Under those, one authored sentence naming the mover — `pm.day_move_contributions`
  already computes it, and that sentence currently sits ~900px down the page.
- **Right:** the sector donut. It earns its place here by turning a number into a picture
  without needing another section.
- **Bottom:** P&L, positions and cash reconciliation demote to a quiet meta strip.

Then everything below drops a level, and the six sections group into three named
movements: *What you own* · *What risk you carry* · *How it would have done*. Kill the
Plotly `title` on any chart already sitting under a section header — that is currently two
labelling systems for one thing.

This buys a first-five-seconds moment made of the user's own money rather than the
product's name, a ~6× type scale range instead of 3×, and depth instead of volume.

### 4 · Tabular numerals (`.streamlit/config.toml` + `theme.py`)

`codeFont` = JetBrains Mono via the `"Family:url"` Google Fonts syntax, plus `font`,
`headingFont`, `baseRadius`, `buttonRadius`, `borderColor`, `showWidgetBorder`,
`headingFontSizes`, `headingFontWeights`. The file currently sets 5 of ~35 available keys.

**Bounded to tiles and tables** — `stMetricValue`, `stMetricDelta`, `table.rs-table`,
`.rs-num`. Not running prose: mono inside "A beta of **0.60** means your invested equity
tends to move about **40% less**" fragments the sentence and undoes the plain-language
voice PRODUCT.md commits to.

A full fallback stack is mandatory, not optional — a Google Fonts fetch failing mid-defence
on Community Cloud would otherwise degrade the whole type system live.

### 5 · Static atmosphere (`theme.py`)

A **static** multi-stop wash — deep blue and violet at 6–14% over `PAGE`, strongest at the
top — plus a dim, radially-masked technical grid (`repeating-linear-gradient` hairlines at
~1.8% white) on a fixed `pointer-events:none` pseudo-element.

No drift animation. No film grain. Both were justified by the demo video and both are the
items least likely to survive being recorded: a 45s-period low-alpha gradient is either
imperceptible in a five-second shot or becomes codec banding, and high-frequency grain is
the most expensive thing you can hand an encoder — it smooths to mud or eats the bitrate
that was rendering the numbers crisply.

### 6 · Brand mark, sidebar only (`app.py`, `assets/robosmart-mark.svg`)

`st.logo()` with the authored SVG. **No hero masthead** — see constraint 7.

### 7 · Sweep every emoji (`app.py`, `theme.py`, `tabs/*.py`)

All 13 across 5 files become Material Symbols: the four router icons, 📈 in the sidebar
masthead and the performance section, 🐂🐻 in the debate, ⚠️✅ in the notices, 📄 and 🔍 in
attribution. **All or nothing** — replacing only the router's four leaves the page less
coherent than it is now.

### 8 · Bull vs bear as a confrontation (`tabs/debate.py`)

The two sides are currently visually identical `st.container(border=True)` boxes separated
by a 10px uppercase word. Give each side its own tinted panel against a shared centre
gutter, so the block reads as an argument before a word of it is read. ~30 lines of CSS on
the existing column structure — and distinctive because it is about *this* product.

### 9 · Reveal the analyst's tool trace (`tabs/chat.py`)

`expanded=True`, or a compact always-visible strip of tool names with the full trace
expandable. That trace is the strongest evidence for the 20% "AI beyond trivial use"
criterion and is currently one click from invisible.

## Cut

- **Animated aurora drift** and **film grain** — §5.
- **Hero masthead** — reverses a documented decision, and puts the session's largest
  gesture behind a label.
- **Count-up numbers** — cut, not deferred. In a framework that reruns on every sidebar
  touch, a signature-gated count-up will misfire at least once, and a number visibly
  animating while the presenter is mid-sentence about it is worse than a static number.
- **Scroll choreography**; **third-party component libraries** (all v1/iframe-era, would
  import a second design language into an app that already has a documented one).

## Verification

1. `.venv/bin/python -m pytest` — 199 pass, offline, unchanged.
2. New test: every animated selector appears in the `prefers-reduced-motion` block.
3. Live browser at 1440 / 1280 / 390: measure contrast against the **computed**
   background, not the declared token. The recorded lesson is that Streamlit darkens
   `primaryColor` for buttons and the "obvious fix" measured worse than the reported
   problem. Confirm `GOOD`/`BAD`/body/`MUTED` unchanged from baseline.
4. Headline number does not clip at 1024px (existing 1150px wrap guard).
5. Exactly one radius per role — no sixth radius introduced.
6. `prefers-reduced-motion: reduce` yields a completely static page, every element in its
   finished state.

## What changed in revision 1, and why

The original spec led with an animated aurora, film grain and a hero masthead. A design
review argued that was atmosphere aimed at the wrong layer, and four of its claims were
verified directly against the codebase before the plan was changed:

- Five distinct radii already in use — a card system would have added a sixth.
- 13 emoji across 5 files, not the 4 in the router — a partial sweep makes it worse.
- `tabs/chat.py:60` hides the tool trace behind a collapsed expander.
- `theme.py` rule 6 already argues in writing that the product name must not outweigh the
  user's money — which the proposed hero masthead would have reversed, with the session's
  largest visual gesture placed behind it.

The general lesson, worth keeping: **effects were being specified for a page whose problem
was structural.** Fix the surfaces and the composition and the app reads as designed with
no ambient effects at all — at which point a static wash is a finish rather than the
load-bearing idea.
