# Cinematic design pass — aurora + terminal

**Date:** 2026-08-01 · **Baseline:** `d3cd9ee` (199 tests green)
**Scope:** one focused session. Surface only — no analytics, no prompts, no AI behaviour.

## Goal

The app is correct, accessible and measured, and it reads as basic. PRODUCT.md records
the user's positioning verbatim: *"the design, the different features, the animations and
motions, and the UX and frontend implementations will be the things that differentiate
us."* This pass makes the surface carry that claim.

Direction chosen: **aurora + terminal**. Drifting coloured light behind the masthead and
the top of the page for the first five seconds of a demo; a technical grid, film grain and
monospace numerals everywhere the actual analysis lives.

## Hard constraints

1. **The measured colour contract does not change.** `GOOD` 5.91:1, `BAD` 5.92:1, `FOCUS`
   10.2:1, `CONNECTOR` 3.24:1 all stay exactly as they are. Contrast was fixed once by
   measurement; decoration is added *underneath and around* it, never on top of it.
2. **Content sits on opaque surfaces.** Nothing behind a card may reach the text, so no
   ratio can drift. Glass is used only where no text sits on it.
3. **Invariant 10 holds.** All model output still reaches the page through
   `theme.safe` / `theme.safe_md`.
4. **Motion follows the recorded rule.** Duration is inversely proportional to how often
   a thing fires, because Streamlit rebuilds the DOM on every rerun. Nothing decorative
   replays on a rerun. `prefers-reduced-motion` disables every new animation.
5. **199 tests stay green**, offline, in ~5s.
6. `portfolio_metrics.py` and `factor_model.py` still import no Streamlit.

## Correction to the record

PRODUCT.md states custom components "render inside isolated iframes and cannot call one
another, so orchestrated cross-component motion … [is] **not achievable in the current
stack**." That was true of Components v1. Streamlit 1.60 ships **Components v2**, verified
present:

```
st.components.v2.component(name, *, html=None, css=None, js=None, isolate_styles=True)
```

Streamlit's own bundled reference states: *"`window.parent.postMessage(...)` — v1 iframe
communication; **CCv2 does not use iframes**."* It is Shadow DOM in the same document,
with the theme piped in as `--st-*` custom properties. Real JS animation is reachable in
Streamlit today, and the React-migration case is correspondingly weaker.

**This spec still uses CSS, not CCv2, for the background.** For a full-page ambient layer
CSS wins on robustness: no component mount, nothing to re-initialise when Streamlit
rebuilds the DOM, no CDN dependency that can fail on Community Cloud. CCv2 is held in
reserve for the one item CSS genuinely cannot do (§7).

## Work items

### 1 · Aurora (`theme.py`, rule 5)

Extend `[data-testid="stAppViewContainer"]`'s existing radial wash into three layered
gradient blobs — deep blue, violet, a cyan hint — each at 6–14% alpha over `PAGE`,
drifting on a single ~45s `alternate ease-in-out` keyframe. Strongest behind the masthead,
falling off down the page. Animates `background-position` only.

The app shell element is not the part Streamlit replaces on rerun, so the animation runs
continuously rather than restarting.

### 2 · Terminal overlay (`theme.py`, new rule)

Two fixed, `pointer-events:none` pseudo-elements on the app container:

- `::before` — technical grid. `repeating-linear-gradient` hairlines every 64px at
  ~1.8% white, radially masked so it fades out at the edges.
- `::after` — film grain. Inline SVG `feTurbulence` as a data URI (no image file, no
  network request), ~3.5% opacity, `mix-blend-mode: overlay`.

`[data-testid="stMain"]` and the sidebar take `position:relative; z-index:1` so content
paints above both layers.

### 3 · Card system (`theme.py`, new rule)

Driven off Streamlit's own test IDs so the four tab modules need no restructuring:
`[data-testid="stMetric"]`, `.stPlotlyChart`, `.rs-table-wrap`, `.rs-notice`.

Opaque vertical-gradient surface, 1px border, 12px radius, an inset top-edge highlight at
~4% white, and a soft drop shadow. A 1px lift on hover at `--rs-quick`.

### 4 · Typography and shape (`.streamlit/config.toml`)

The file sets 5 theme keys; 1.60 supports ~35. Add: `font` and `headingFont` (Inter, via
the `"Family:url"` Google Fonts syntax), `codeFont` (JetBrains Mono), `baseRadius`,
`buttonRadius`, `borderColor`, `showWidgetBorder`, `headingFontSizes`,
`headingFontWeights`, `linkUnderline`.

Then in CSS: **every number on the page renders in JetBrains Mono** — metric values and
deltas, `.rs-num`, `table.rs-table`. This single change does more for "terminal
instrument" than any effect. A full fallback stack is required in case the Google Fonts
fetch fails on Community Cloud.

Where a new config key makes an existing `!important` CSS rule redundant, delete the rule.

### 5 · Masthead (`app.py`, `assets/robosmart-mark.svg`)

`st.title("RoboSmart Investment")` becomes a hero block via `st.html`: a hand-authored SVG
mark (rising-line monogram), display-scale wordmark, the tagline, and the freshness line
as a chip rather than a caption. The aurora peaks behind exactly this block. The same SVG
is wired to `st.logo()` for the sidebar.

Exactly one `<h1>` on the page — the heading outline stays fixed.

### 6 · Icons (`app.py`)

The view router's emoji (📊 ⚔️ 🔍 💬) become Material Symbols
(`:material/analytics:`, `:material/swords:`, `:material/search:`, `:material/chat:`).
Streamlit's bundled design reference calls this out explicitly. Verify they render inside
`st.segmented_control`'s `format_func`; fall back to emoji if not.

### 7 · Count-up numbers — STRETCH, attempted only after 1–6 verify

The most product-like motion available, and the only item needing JS (a CCv2 inline
component). Correctness requires gating on a portfolio signature in session state so it
fires on a state change the user caused and not on every rerun — which is exactly the item
most likely to overrun the session. Not started until everything above is verified.

## Explicitly out of scope

- Scroll-choreographed reveals — fights Streamlit's rerun model, would eat the session.
- Third-party component libraries (`streamlit-shadcn-ui`, `streamlit-antd-components`,
  `streamlit-extras`). All v1/iframe-era; they would import a second design language into
  an app that already has a documented one, and cannot share a motion timeline.
- Any change to analytics, prompts, agents, or AI behaviour.

## Verification

1. `.venv/bin/python -m pytest` — 199 pass, offline, unchanged.
2. New test: every animated selector added here appears in the
   `prefers-reduced-motion` block. Guards the rule rather than restating it.
3. In a live browser at 1440 and 1280 and 390: measure text contrast against the
   **computed** background, not the declared token — the recorded lesson is that
   Streamlit darkens `primaryColor` for buttons and the "obvious fix" measured worse than
   the reported problem. Confirm `GOOD`/`BAD`/body/`MUTED` are unchanged from baseline.
4. Confirm the headline number does not clip at 1024px (the existing 1150px wrap guard).
5. Confirm the aurora does not restart on rerun: switch investor, watch the drift.
6. Force `prefers-reduced-motion: reduce` and confirm a completely static page with every
   element in its finished state.
