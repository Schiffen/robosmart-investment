# RoboSmart Debate Club — the two logotypes

Two lockups that do different jobs. They share one drawn alphabet, so they belong to the
same identity, but they are **not interchangeable** — each has a place it works and a place
it fails. Use both, in the positions below.

```
seal.svg              240 × 240      1 : 1        ink #E6EDF3   for dark backgrounds
seal-on-light.svg     240 × 240      1 : 1        ink #10151A   for light backgrounds
mirror.svg            715.67 × 238   3.007 : 1    ink #E6EDF3
mirror-on-light.svg   715.67 × 238   3.007 : 1    ink #10151A
rose.svg              30.3 × 30.3    1 : 1        ink #E6EDF3   the seal's centre mark
rose-on-light.svg     30.3 × 30.3    1 : 1        ink #10151A
```

All are standalone SVG: namespace-complete XML, explicit `viewBox`, no `currentColor`, no
CSS variables, no external references, no `<text>` and no font references — all lettering is
outline paths, so they render identically in the app, in a browser tab, in a PDF, on a slide
and in a social preview. `tests/test_brand_and_about.py` asserts every one of those.

**A file and its `-on-light` twin differ in the ink value and in nothing else that is
visible.** Never recolour either file any other way.

> ⚠️ *This paragraph used to say the ink was the ONLY permitted difference. That is false
> for the mirror, and a test written to enforce it failed immediately.* The mirror's twins
> also carry different internal ids — `mgd`/`mmd` against `mgl`/`mml`. They **must**:
> `brand.py` inlines marks as base64 into one document, SVG ids share a single namespace
> per document, and two `id="mgd"` elements would collide so the first reflection mask
> registered would silently apply to both marks. Keep the ids namespaced per file. The
> invariant that actually holds is *identical drawing, ink swapped, ids distinct*.

---

## THE SEAL — `seal.svg`

The drawn alphabet set around a ring, letter by letter on rotation transforms, with the
radial mark at the centre. It is the *compact, repeatable* half of the identity: square,
legible at small size, and it survives any crop that keeps the circle.

**Use it for**

| Location | Size | Note |
|---|---|---|
| Application masthead / sidebar header | 40–56px | beside the product name in the app's own face — **Inter 700**, not IBM Plex: this app ships Inter/JetBrains Mono and has no Plex anywhere. Implemented at 44px in `brand.masthead()` |
| Browser tab (favicon) | 32px | dark file — but see the favicon note at the end of this file; neither ink survives both a light and a dark tab strip |
| Avatar, social preview, OG image | 512px | on `theme.PAGE #0d0d0d` with clear space; the light file on `#F2F0EB` |
| Corner stamp on an exported PDF or slide | 48–72px | **use `seal-on-light.svg`** — these render where the app's CSS never reaches |
| Loading / splash, small | 72–120px | centred, nothing else on screen |

**Clear space** one letter height (≈24 units of the 240 viewBox) on all four sides.

**Minimum 72px when the seal states the name BY ITSELF.** At 48px the ring type becomes
decorative texture — acceptable as an avatar, never as the sole statement of the name.
Below that, drop to the centre mark alone: **`rose.svg`**.

> The placement table above says 40–56px for the masthead, which reads as a contradiction
> of that 72px floor. It is not, and the resolution is in the floor's own wording. The
> floor protects a seal carrying the name *alone*; in the masthead the name is set in type
> immediately beside it, so the ring lettering is free to become texture. `brand.py`
> encodes this as `SEAL_MIN_ALONE` rather than leaving the next reader to re-derive it.
>
> Measured consequence, worth knowing before choosing a size: the two `opacity="0.55"`
> inner rings are 1 unit of a 240 viewBox, so they render at **0.18px at 44px** and
> **0.30px at 72px** — after antialiasing that is 1.3:1 and 1.6:1 against the sidebar.
> They never clear 3:1 at any size this app uses; they resolve only around 240px. The
> outer ring (3 units) is fine from 44px up. Nothing is broken — but do not expect the
> inner rings to read at product sizes.

*(This section previously pointed at `rose-min.svg` "in the symbol set". There was no
symbol set and no such file, so the instruction could not be followed. `rose.svg` is that
mark, extracted from `seal.svg` rather than redrawn — a test pins its paths to the seal's
so the two cannot drift.)*

**Never** put the seal on a busy or photographic ground, rotate it, add a drop shadow, fill
the ring, or set anything inside the outer circle.

---

## THE MIRROR — `mirror.svg`

The name above a hard rule with its own reflection falling away beneath it. It is the
*ceremonial* half: it says what the product is about — every claim answered by its
opposite — and it needs room to say it.

**Use it for**

| Location | Size | Note |
|---|---|---|
| Landing / splash screen | 420–640px wide | centred, generous margin, nothing beside it |
| Section or chapter title page | 360–520px wide | one per view at most |
| Cover of an exported report or deck | 480px wide | **use `mirror-on-light.svg`** |
| Empty first-run state, before a portfolio is uploaded | 360px wide | above the upload control |
| README / repo header | 600px wide | dark file on a dark README, light file otherwise |

**Clear space** the rule height × 8 on all four sides. Nothing may sit inside the
reflection — it is part of the mark, not decoration around it.
**Minimum 150px tall** (≈450px wide). Below that the reflection reads as a printing fault.

**Do not use the mirror as a masthead.** In a horizontal bar it either gets cropped or
forces the bar to three times its natural height. That position belongs to the seal.

**Reproduction:** the reflection peaks at 92% ink immediately under the rule and reaches
nothing 82 units later. It is the first thing a bad reproduction loses — print it, never fax
or photocopy it. If the output is one-bit or a fax, use the seal instead.

---

## Choosing the file: dark or light

Measure the surface it will sit on, not the theme name — and measure the **computed**
background after every layer composites, never the declared token.

> ⚠️ *The table that used to be here measured `#0B0E11`, `#141A20` and `#1C242C`. **This
> app has none of those surfaces.** Its real ones are `PAGE #0d0d0d`, `SURFACE #1a1a19`
> and the page composite. The old arithmetic was sound — all five ratios reproduce exactly
> against the surfaces named — it was simply measuring somebody else's palette. One row
> was also wrong on its own terms: `#10151A` on white is 18.35, not 18.14.*

RoboSmart's page is not `backgroundColor`. `theme.py` rule 5 paints a blue/violet wash and
a fixed grid overlay on top of `PAGE`, both *under* content, so anything on the page renders
against the composite. That composite already caused one real AA failure here (`MUTED`
5.41 → 4.27:1).

### App surfaces — these govern in-product placement

| Background | What it actually is | Ink | Contrast |
|---|---|---|---|
| `#0d0d0d` `theme.PAGE` | the declared page colour — reachable only where wash and grid are both absent | `#E6EDF3` | **16.45 : 1** |
| `#1a1a19` `theme.SURFACE` | panels, the sidebar, the judge's verdict card, and the lightest point of the rule-11 / lede gradient (which only ever runs *darker*) | `#E6EDF3` | **14.74 : 1** |
| `#222530` page **composite** | `theme.py`'s recorded value for the page at its lightest | `#E6EDF3` | **12.92 : 1** |
| `#252833` composite, worst pixel | a grid-line **intersection** at 1440×721 — reachable by any stroke | `#E6EDF3` | **12.43 : 1** |
| `#2d3249` composite, ≤400px | the wash centres are `%`-positioned with `px` radii, so a phone sits in the bright core of all three gradients | `#E6EDF3` | **10.68 : 1** |
| `#21332e` bull field | lightest edge of the rule-14 tint, over the composite | `#E6EDF3` | **11.27 : 1** |
| `#372c35` bear field | lightest edge, over the composite | `#E6EDF3` | **11.29 : 1** |

**The page composite is not a constant.** It moves with the viewport, because the wash
gradients position in `%` and size in `px`. Treat `#222530` as the working value, `#252833`
as the desktop worst pixel, `#2d3249` as the ≤400px stress case — and never quote one hex
as "the page background" without saying which.

### Export surfaces — outside the app, where its CSS never reaches

| Background | File | Ink | Contrast |
|---|---|---|---|
| `#F2F0EB` paper / slide / print | `*-on-light.svg` | `#10151A` | **16.12 : 1** |
| plain white `#FFFFFF` | `*-on-light.svg` | `#10151A` | **18.35 : 1** |

**On the WCAG floor.** SC 1.4.11 Non-text Contrast explicitly **exempts logotypes** — a logo
has no minimum contrast requirement under WCAG at all. The 3:1 used throughout this file is
*this project's house rule*, kept because a mark below it reads as a rendering fault. Do not
cite it as a conformance obligation; doing so is how a real obligation elsewhere gets
discounted. *(The previous wording asserted a "3:1 floor" as though WCAG imposed it.)*

**Two things an ink ratio does not cover.**

1. **Antialiasing.** A sub-pixel stroke renders at partial coverage and its effective ratio
   falls with its width — see the seal's inner rings above.
2. **The mirror's reflection is a fade, so most of it sits below any floor.** The mask ramps
   0.92 → 0 across the glyphs; against the page composite it clears 3:1 for roughly the top
   **56%** of its height and its bottom edge measures **1.16 : 1**. That is what a fade is.
   But this file cannot also claim the reflection is "part of the mark, not decoration" *and*
   that everything here clears 4.5:1 — both are not true at once. Treat the reflection as
   decorative and claim no floor for it.

**Favicon.** The backdrop is browser chrome, which this palette does not own. `#E6EDF3` on a
white tab strip is **1.18 : 1**; `#10151A` on a dark one is **1.14 : 1**. Neither shipped file
survives both, and a `<link rel="icon">` picks exactly one. Shipping "also ship the light
one" does not solve it. The real fix is one SVG carrying a `prefers-color-scheme` rule, or a
mark with its own ground.

---

## Dropping them into Streamlit

Inline as a base64 `data:` URI. Never link to an external file — the platform will not serve
it reliably and a PDF export will lose it.

```python
import base64
from pathlib import Path
import streamlit as st

LOGOS = Path(__file__).parent / "logos"

def logo(which: str = "seal", height: int = 48, ink: str = "dark") -> str:
    """which: 'seal' | 'mirror'   ink: 'dark' | 'light'
    Minimums: seal 72px tall, mirror 150px tall."""
    suffix = "-on-light" if ink == "light" else ""
    svg = (LOGOS / f"{which}{suffix}.svg").read_text(encoding="utf-8")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{b64}" alt="RoboSmart Debate Club" '
            f'style="display:block;height:{height}px;width:auto;" />')

def favicon_tag() -> str:
    svg = (LOGOS / "seal.svg").read_text(encoding="utf-8")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,{b64}">'

# masthead
st.markdown(
    f'<div style="display:flex;align-items:center;gap:14px;">{logo("seal", 44)}'
    f'<span style="font-family:\'IBM Plex Sans\',sans-serif;font-weight:600;'
    f'font-size:19px;letter-spacing:-.01em;color:#E6EDF3;">RoboSmart Debate Club</span></div>',
    unsafe_allow_html=True)

# splash
st.markdown(f'<div style="display:flex;justify-content:center;padding:64px 0;">'
            f'{logo("mirror", 190)}</div>', unsafe_allow_html=True)
```

Two things that silently break, both worth telling whoever implements this:

1. Any CSS you scope must target **`section.stMain`**, never `[data-testid="stMain"]` —
   Streamlit renames that testid on any view containing a chat input, which unstyles the
   whole view. The class survives the rename.
2. `st.set_page_config(page_icon=…)` will not reliably accept an SVG. Set the page title
   there and inject the favicon with `favicon_tag()` instead.

---

## Quick reference

|  | Seal | Mirror |
|---|---|---|
| Shape | 1 : 1 square | 3 : 1 horizontal block, tall |
| Minimum | 72px | 150px tall / ≈450px wide |
| Masthead | **yes** | no |
| Favicon / avatar | **yes** | no |
| Splash, cover, title page | small use only | **yes** |
| Empty first-run state | no | **yes** |
| PDF / slide corner | **yes**, on-light | cover only, on-light |
| Survives one-bit reproduction | **yes** | no |

Nothing in this identity may imply users, customers, testimonials, metrics, performance or a
track record. There are none.
