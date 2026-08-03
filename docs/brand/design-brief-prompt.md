# Design brief — paste this whole file into the design agent

> Copy everything below the line into Claude Desktop (or claude.ai).
>
> Scope is narrow on purpose: **symbols, logos, and backgrounds only.** No screen design,
> no layout, no UX. Three families of artefact, 3–4 distinct options in each.
>
> §4 is technical physics, verified by testing. §5 governs the format of the handback.
> Nothing else here tells you what to draw.

---

You are the designer. You have complete creative authority over what this looks like.

I am giving you the product, the surfaces the work has to live on, and the technical facts
of the platform. I am **not** giving you references, palettes, sketches, moodboards or prior
attempts — deliberately. Anything I showed you would anchor you to it, and I would rather
have your thinking than mine rendered more neatly.

Think first. Then show me genuinely different options, then tell me what you'd choose.

---

## 1. What this product is

Someone uploads a list of stocks they own. The application helps them understand:

- **What they actually hold** — the shape of it, how concentrated it really is, what moved
  today and which holding caused that.
- **The case for and the case against a stock** — a structured argument in which one voice
  makes the bull case, another makes the bear case, each answers the other, and a third
  adjudicates between them. Every claim has to cite evidence it was actually handed.
- **Why a price moved** — a statistical model separates a day's move into how much was the
  whole market, how much was that industry, and how much was the company itself. Only
  *after* that runs may an AI speak, and only about the residue the statistics could not
  account for.
- **Answers to their own questions** — an AI agent holding no data in its prompt, so every
  figure it states had to come back from a tool that ran real, tested mathematics. It can
  model a hypothetical trade but never execute one, and it will not give advice.

### What it believes

**Numbers before narrative.** The mathematics runs first and independently. Language only
gets to interpret what the mathematics could not explain. The AI is deliberately
*constrained* rather than oracular, and that constraint is the whole basis of its claim to
be trusted.

It says **"no clear cause found"** when that is true. Here that is a finished answer, not a
failure.

It is an educational university project. It never recommends buying or selling. It has **no
users, no customers, no track record and no performance history** — none of these may be
implied.

### Who it is for

Primarily **someone new to investing** — owns a few stocks, doesn't know what "beta" means,
arrives asking *"my stock moved, why?"* Secondarily **someone technical**, judging in about
ten minutes how serious the machinery underneath really is.

### The name

**RoboSmart Debate Club.**

### The surface this has to live on

A dark, dense, data-heavy web application. Numbers, tables, charts, and long passages of
generated argument. Text density is high and legibility is not negotiable.

The current version is at `https://robosmart-investment-proj.streamlit.app/` — worth a look
to understand the density and where things sit. **Its present identity is placeholder and
carries no authority whatsoever.** Ignore how it looks; note only what has to be
accommodated.

---

## 2. What I need from you

Three families. **3–4 options in each, each from a genuinely different premise** — different
ideas, not one idea in several colourways.

### A. A symbol system

Not a single glyph. **A system of marks** that can be patched into many points across the
application without being redrawn each time. This is the part I care most about.

The requirement is **modularity**. Marks need to drop into different places at different
sizes and different weights of emphasis, against different backgrounds. Some places want the
full thing; some want it reduced almost to a gesture; some want it as quiet texture behind
content.

Places a mark may need to sit — given as *functions*, so you can decide which actually
warrant one and which don't:

- A browser tab, at 16px
- A persistent application masthead
- The head of a section or a view
- Beside a heading, indicating what kind of content follows
- Marking one side of an opposed pair — and marking the other side of it
- Standing in an empty state, where there is nothing yet to show
- Signalling that work is under way and the answer has not arrived
- Signalling that the honest answer is *"I don't know"*
- As a large, quiet watermark behind or beside content
- On a document, a slide, or a social preview, entirely outside the app

Tell me how the system scales up and reduces down, what its atoms are, and what the rules
are for using it.

### B. The logo

The identity proper — the name made into a thing. Wordmark, mark-plus-wordmark, or whatever
you argue for. Horizontal and stacked arrangements, clear-space and minimum sizes, and a
variant that holds up on a light background (browser tab, printed page, slide) as well as in
the dark application.

Tell me the typeface you chose and why, or show me the letterforms you drew.

### C. The background

The plane the whole application sits on. It has to carry dense text, tables and charts
without competing with them, and it should be a *designed* surface rather than the absence
of one.

Everything is available to you: colour, gradient, texture, grain, depth, structure, light,
pattern, motion. The one hard requirement is that **text and data stay legible on it**,
measured (see §4e), including wherever the treatment is at its lightest or its busiest.

Show each background **rendered with realistic dense content on top** — small text, a table,
a chart — never as an empty swatch. A background that only works empty is not a background.

---

## 3. Also tell me

- One sentence per option on what the idea actually *is*.
- Which you'd choose in each family, and why.
- Which combinations across the three families work together, and which fight each other.
- What you tried and discarded.

Depth over volume. Three thought-through directions beat a dozen variations.

---

## 4. Technical constraints — verified, not preferences

Built in **Python + Streamlit**. These come from testing, not from taste. A design that
violates them cannot be built.

### 4a. Symbol and logo files

Marks are inlined as **base64 `data:` URIs inside `<img>` tags**, and also used as inline
SVG. Therefore:

- **No external fonts load.** Any lettering must be **converted to outline paths**. A font
  reference silently falls back to whatever the system happens to have.
- **No scripts run**, and **no external resources** load — no linked images, no external CSS.
- **CSS `@keyframes` animation inside the file does work.** Verified by pixel-diffing
  rendered frames. Animated marks are genuinely available to you.
- Files are parsed as **strict XML**. One malformed attribute and the asset does not render
  at all — it vanishes rather than degrading.
- Each must be **self-contained**: no `currentColor`, no CSS variables, no dependency on the
  page's stylesheet. These render where the application's CSS never reaches — browser tab,
  PDF, slide deck, social preview.
- Because they get patched into many places, **each mark must be a standalone file with its
  own stated `viewBox`**, and must not rely on a surrounding plate or backdrop unless that
  plate is part of the file itself.

### 4b. Sizes marks must survive

`16` · `24` · `32` · `48` · `180` · `512`, plus large decorative use. If detail cannot
survive the small end, supply a **separate simplified variant** — normal practice, and far
better than one mark that turns to mush.

### 4c. Typefaces

Anything used in the **interface** must be on **Google Fonts** — the only webfont mechanism
this platform supports. A **logotype** has no such limit, since it becomes outline paths.

### 4d. Backgrounds and CSS

- The platform rebuilds the DOM on **every interaction**. A background must survive a full
  re-render without restarting, flashing or reflowing.
- **Plain CSS only.** No React, no Tailwind, no component library, no build step — it is
  injected as a string into a Python application.
- Scope selectors to **`section.stMain`**, never `[data-testid="stMain"]`. The platform
  renames that testid on any view containing a chat input, which silently unstyles that
  entire view. The class survives the rename; the testid does not.
- Real JavaScript *is* reachable through the platform's component system (Shadow DOM in the
  same document, not iframes), so an animated or generative background is possible — but
  propose it as an enhancement over a CSS baseline, never as a requirement for legibility.
- A background may be a CSS gradient, layered gradients, an inline SVG data URI, a canvas,
  or generated. It may not be an external image file.

### 4e. Legibility — a floor, not a target

- Normal text **4.5:1** minimum contrast; large text (≥24px, or ≥18.66px bold) 3:1.
- **State the measured ratio** for every text/background pair, naming the background it was
  measured against. Never assert a ratio you have not calculated.
- **A translucent layer changes what "the background" is.** If you stack anything over a
  surface, text must be measured against the resulting *composite*, not the value
  underneath. Measure at the treatment's lightest and busiest point, not its average.
- Never encode meaning by colour alone — pair it with shape, sign or label.
- All motion must honour `prefers-reduced-motion: reduce`.
- If colour anywhere distinguishes a gain from a loss, match the two on **saturation as well
  as luminance**, so an equally-sized loss does not read quieter than the gain. That is a
  fairness property, not an aesthetic one.

---

## 5. Output contract — follow this literally

Governs **format only**. It says nothing about what you design. It exists because this gets
implemented verbatim by an engineer who will copy your values exactly.

**a. Raw SVG source for every mark, variant and lockup**, in separate fenced code blocks,
each labelled with where it is meant to be used. State every `viewBox`. All lettering as
`<path>` — no `<text>`, no font references, no `currentColor`, no external references.
Valid, namespace-complete XML. Any animation as CSS `@keyframes` inside the file, including
`@media (prefers-reduced-motion: reduce)`.

**b. Every background as copy-pasteable CSS**, in fenced blocks, scoped to
`section.stMain`. Where a background uses an inline SVG data URI, give the readable SVG
source as well, not only the encoded string.

**c. One self-contained HTML file**, no external assets, showing everything: each mark
inline as `<svg>` at 16/24/32/48/128 on dark, on a panel, and on light; every lockup at real
size; **each background rendered full-bleed with realistic dense content over it** — small
text, a table, a chart; and colour swatches with hex values and measured ratios printed as
text.

**d. A token table** — name, hex, role, measured ratio, and which background it was measured
against.

**e. Type declarations** — exact face names, weights, whether each is on Google Fonts, and
the full `https://fonts.googleapis.com/css2?...` URL where it is. Flag any face that is
logotype-only.

**f. Usage rules for the symbol system** — which mark goes where, minimum sizes, clear space,
what may and may not be recoloured, and how the pieces relate to one another.

---

## 6. Do not

- Do not return raster images as final assets. PNGs are fine for showing a direction; they
  cannot ship. Every final asset must exist as SVG or CSS source.
- Do not require a build step, framework or component library.
- Do not propose an interface typeface that is not on Google Fonts.
- Do not invent users, testimonials, metrics, performance or customers. There are none.
- Do not show a background without real content on top of it.
- Do not state a contrast ratio you have not calculated.

Beyond these and §4, there are no rules. The more surprising, and the more specific to
*this* product rather than to fintech in general, the better.
