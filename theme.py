"""
theme.py — SHARED design system for RoboSmart.
==============================================
Every tab imports from here so the Portfolio Dashboard, the Bull vs Bear
debate, and the "What happened today" attribution tab read as ONE product.
Built on the dataviz reference palette (dark steps).

Usage:
    import theme
    theme.inject_css()                              # once, from app.py
    fig = theme.style_fig(fig)                      # dark Plotly styling
    st.markdown(theme.badge("HIGH", "high"), unsafe_allow_html=True)
    st.markdown(theme.safe(model_text))             # ANY model-authored string
    theme.fmt_money(1234.5, "$")  -> "$1,234.50"

CONTRAST IS A CONTRACT HERE. Every token below is measured, and the ratio is
written next to it. If you change a colour, re-measure it — do not eyeball it.
The previous BAD (#d03b3b) sat at 4.05:1 while its GOOD counterpart sat at
5.79:1, which meant losses were literally harder to read than gains.

THREE surfaces now, not two, and this is the part that catches people:

    SURFACE  #1a1a19   panels — also the LIGHTEST point of the panel gradient
    PAGE     #0d0d0d   the declared page colour
    COMPOSITE #222530  what the page ACTUALLY is at its lightest, once the
                       wash (rule 5) and the grid overlay are composited

Text on a panel is safe: the panel gradient only ever runs darker than SURFACE,
by construction. Text directly on the page is NOT — the composite is 4.6x
lighter than PAGE in luminance, and measuring against #0d0d0d there will tell
you a comfortable lie. MUTED already failed this way once (5.41 -> 4.27:1).

And measure the STATE you are claiming, not just the element: "Streamlit darkens
primaryColor for buttons" was recorded here as a general fact, is true only of
:hover, and hid a real AA failure at rest for two revisions.
"""

from __future__ import annotations

import html
import re

import numpy as np

# --- Surfaces & ink (dataviz dark chrome) ---------------------------------
SURFACE = "#1a1a19"      # chart surface / raised panel
PAGE = "#0d0d0d"         # page plane
INK = "#ffffff"          # primary text            19.4:1 on page
INK_2 = "#c3c2b7"        # secondary text          10.9:1 on page
MUTED = "#9d9b94"        # axis / labels   5.49:1 on the PAGE COMPOSITE (see below)
                         #                 6.26:1 on surface · 6.99:1 on bare PAGE
                         #
                         # Was #898781, which measured 5.41:1 "on page" and was
                         # correct when the page WAS #0d0d0d. It is not any more.
                         # The wash in CSS rule 5 plus the grid overlay composite
                         # to #222530 at their lightest point — luminance 0.0184
                         # against PAGE's 0.0040, i.e. 4.6x lighter — and every
                         # colour sitting directly on the page lost 20-25% of its
                         # ratio. MUTED was the only one close enough to the line
                         # to cross it: 5.41 -> 4.27:1, a real AA failure at 12-13px.
                         #
                         # The wash is VIEWPORT-anchored, so that worst pixel is
                         # reachable by any content at any scroll position. This
                         # is the trap in adding a background to a finished
                         # palette: nothing looks broken, and the token whose job
                         # is to recede is exactly the one that fails first.
GRID = "#3a3a37"         # hairline gridline — recessive by design, non-essential
AXIS = "#383835"         # baseline / axis
CONNECTOR = "#6b6b64"    # waterfall connectors     3.2:1 on surface — MEANINGFUL,
                         # carries "these parts sum to the whole". Never drop it
                         # to GRID: at 1.2:1 the waterfall reads as four
                         # disconnected floating bars and the chart loses its point.
FOCUS = "#8ec0f7"        # keyboard focus ring     10.2:1 on page

# --- Shape: ONE radius per role -------------------------------------------
# Five different values were previously doing similar jobs — 6px (focus ring),
# 10px (notice, weakest-claim box, key-uncertainty box), 14px (verdict card,
# attribution card), 999px (badge, confidence bar), plus Streamlit's own on
# st.container(border=True). Near-miss inconsistency of exactly that kind is
# what makes an interface read as assembled rather than designed, and a viewer
# feels it without ever being able to name it.
#
# Three tokens, each with a job. RADIUS_PANEL is kept in step with
# `baseRadius` in .streamlit/config.toml so app-authored panels and Streamlit's
# own widgets round identically — change one and you must change the other.
RADIUS_PILL = "999px"    # fully rounded: badges, confidence bars
RADIUS_PANEL = "10px"    # every standard panel, and the focus ring that wraps one
RADIUS_HERO = "14px"     # ANSWER-weight panels only: the lede block, the judge's
                         # verdict, and attribution's "no clear cause found".
                         # Three panels app-wide. If a fourth wants this radius,
                         # the question to ask is whether it is really an answer.

# --- Status palette (fixed — never used as a series colour) ----------------
# GOOD and BAD are matched on BOTH axes that make a pair feel balanced:
#
#   relative luminance   GOOD 0.2691   BAD 0.2699    (contrast parity)
#   HLS saturation       GOOD 0.720    BAD 0.720     (visual-weight parity)
#
# Luminance parity alone is not enough. The previous green (#0ca30c) already
# matched BAD's luminance almost exactly, yet as a large area fill — the
# contribution bars — it visibly outweighed the coral, because it was far more
# saturated. Equal contrast, unequal presence. Match the chroma too, or a gain
# will always shout louder than a loss of the same size.
GOOD = "#1ba420"         # up / gain / bull / high      5.91:1 page · 5.29:1 surface
WARN = "#fab219"         # caution / medium
SERIOUS = "#ec835a"      # elevated concern
BAD = "#e5665f"          # down / loss / bear / low     5.92:1 page · 5.31:1 surface

# --- Categorical (fixed order, never cycled) -------------------------------
CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767"]

# --- Diverging blue <- gray -> red (correlation, waterfall polarity) --------
DIVERGING = [[0.0, "#3987e5"], [0.5, AXIS], [1.0, "#e66767"]]

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "ILS": "₪", "JPY": "¥"}

# Badge colour lookups. `kind` maps to a status colour; text stays ink-on-colour
# at >=5:1 (see badge()).
LEVEL_COLOR = {"high": GOOD, "medium": WARN, "low": MUTED,
               "strong": GOOD, "weak": MUTED}
SIDE_COLOR = {"bull": GOOD, "buy": GOOD, "bear": BAD, "sell": BAD,
              "inconclusive": MUTED, "neutral": MUTED}


# --------------------------------------------------------------------------
# Model-output safety  (P0)
# --------------------------------------------------------------------------
# Model text used to be interpolated straight into f-strings rendered with
# `unsafe_allow_html=True`. Two things went wrong with that, one cosmetic and
# one not:
#
#   1. A judge verdict containing "$5B ... $5B" had the span between the two
#      dollar signs eaten by Streamlit's LaTeX parser and rendered as a green
#      monospace code block, mid-sentence, on the most-graded screen in the app.
#   2. Anything the model emits — including markup — reaches the DOM verbatim.
#
# `safe()` is the single boundary. Everything model-authored goes through it.

_MD_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+\-.!$~|])")


def _coerce(text) -> str | None:
    """None -> "", non-strings -> str(). A malformed model response must never
    take a tab down."""
    if text is None:
        return ""
    return text if isinstance(text, str) else str(text)


def safe(text) -> str:
    """Model text destined for a raw-HTML span WE control (the verdict card,
    badges, evidence lines).

    Escapes HTML entities, and additionally emits `$` as the `&#36;` entity.
    The entity is what makes this robust: whether or not Streamlit's LaTeX
    inline rule reaches into a raw HTML block is a detail of its markdown
    pipeline that could change under us, and `&#36;` cannot open a math span
    under any of those behaviours while rendering as a perfectly ordinary
    dollar sign.
    """
    out = _coerce(text)
    out = html.escape(out, quote=True)
    return out.replace("$", "&#36;")


def safe_md(text) -> str:
    """Model text destined for `st.markdown()` / `st.caption()` as prose.

    Escapes `&`, `<` and `>`, then backslash-escapes Markdown and LaTeX
    punctuation. `$` is handled with a backslash here rather than an entity
    because this string IS going through the markdown parser, and `\\$` is the
    escape that parser understands.

    `quote=False` is deliberate and load-bearing. With quote=True, an ordinary
    apostrophe becomes `&#x27;` — and the markdown pass then backslash-escapes
    the `#` inside it, breaking the entity so the reader literally sees
    "portfolio&#x27;s". Quotes only need escaping inside an HTML attribute,
    which is `safe()`'s job, not this one. The entities this DOES emit
    (`&amp;` `&lt;` `&gt;`) survive the markdown pass untouched, because none of
    their characters are markdown specials.
    """
    out = _coerce(text)
    out = html.escape(out, quote=False)
    return _MD_SPECIALS.sub(r"\\\1", out)


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------

def style_fig(fig, height: int = 340, *, zoom: bool = False):
    """Apply the shared dark Plotly styling to any figure. Works on donut,
    heatmap, line, waterfall, bar — anything the tabs draw.

    `displayModeBar` is suppressed at the call site (see chart_config): the
    modebar contributed 7 tab stops per chart, and on the Dashboard that was
    ~24 of ~40 focus stops going to plumbing rather than to the app.

    `zoom` DEFAULTS TO FALSE, and that default is the bug fix.

    Plotly's cartesian default is `dragmode="zoom"` — box-zoom on drag. Nothing
    here ever set it, so every cartesian figure in the app inherited it while
    the modebar that would normally RESET it was suppressed. The result: drag a
    chart and it zooms in, with no control anywhere on the page to get back.
    Double-click does reset, but nothing announces that, so in practice the
    chart was a trap. On touch it is worse than a trap — dragging is also how
    the page scrolls, so a reader scrolling PAST a chart zoomed it instead and
    then could not scroll on.

    The fix is deny-by-default, the same shape as this project's offline test
    suite: the risky capability has to be DECLARED, never inherited. Four of
    the five charts have no meaningful zoom at all —

        donut             a pie; cannot zoom
        heatmap           an 8x8 correlation matrix; a zoomed corner is noise
        contribution_bar  categorical; the y axis is ticker names
        waterfall         four bars that sum to a whole; a subset is meaningless

    — so they take the default and become inert to drag. Only a real TIME
    SERIES opts in with `zoom=True`, and when it does it gets `dragmode="pan"`,
    not `"zoom"`: panning is reversible by the same gesture that caused it,
    box-zoom is not. Range selection is the authored control instead, where
    "1Y" is simultaneously the home view and the reset (see tabs/_chart_range).

    `scrollZoom` stays False in CHART_CONFIG regardless. A chart that eats the
    scroll wheel is the single most complained-about behaviour on mobile, and
    nothing here is worth that.
    """
    # Charts paint NO background of their own. The panel underneath is the
    # surface (see CSS rule 11), and a chart that painted its own opaque
    # rectangle inside a rounded panel produced a square-in-round corner
    # mismatch on all four corners — the classic tell of an interface where the
    # card system was bolted on afterwards. Transparent here fixes it at the
    # root instead of hiding it behind matched radii that must then be kept in
    # sync forever.
    # Top margin is 48 ONLY when there is a title to hold. Charts under a
    # theme.section() heading carry no Plotly title (two labelling systems 30px
    # apart is the classic assembled-not-designed tell), and they were still
    # reserving 48px for it — dead space at the top of every chart on the page,
    # and 48px of it inside the lede where it pushed the whole block taller.
    has_title = bool(getattr(getattr(fig.layout, "title", None), "text", None))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK_2, size=13, family="Inter, system-ui, sans-serif"),
        margin=dict(l=10, r=10, t=48 if has_title else 10, b=10),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=CONNECTOR,
                        font=dict(color=INK, size=12)),
        # See the `zoom` note in the docstring. False makes the figure inert to
        # drag while leaving hover — and therefore every tooltip — untouched.
        dragmode="pan" if zoom else False,
    )
    # Only touch `title` when there IS one. Setting title=dict(font=...)
    # unconditionally makes plotly.py emit a title object with a font and no
    # text — and Streamlit's Plotly wrapper then does
    # `text: "<b>" + String(e.text) + "</b>"`, so every untitled chart rendered
    # the literal word **undefined** as its heading. It had been doing so all
    # along, hidden inside the 48px margin that used to be reserved for a title;
    # dropping that margin for untitled charts is what made it visible, clipped
    # against the panel edge. Latent for a long time, exposed by a good change.
    if has_title:
        fig.update_layout(title=dict(font=dict(color=INK, size=15)))
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    return fig


# Passed to every st.plotly_chart. Kills the 7-button modebar.
#
# `scrollZoom` is False and must STAY False. It is the one setting that would
# let a chart eat the page's scroll gesture, which on a phone means a reader
# cannot get past the chart at all. See style_fig's `zoom` note.
CHART_CONFIG = {"displayModeBar": False, "displaylogo": False,
                "staticPlot": False, "scrollZoom": False}


# --- Time-range control for series charts ---------------------------------
# The authored replacement for the modebar's zoom/reset pair.
#
# Presets rather than a +/- zoom, for three reasons that all point the same
# way. They are the vocabulary the domain already uses, so no one has to be
# taught them. They are ABSOLUTE, so pressing one twice does nothing — where
# "+" pressed twice compounds, which is precisely how the old box-zoom became
# inescapable. And the home view is one of the presets rather than a separate
# hidden state, so RESET IS ALWAYS VISIBLE and always one tap; there is no
# "how do I get back" because getting back is the rightmost pill, already lit.
RANGE_PRESETS = ("1M", "3M", "6M", "YTD", "1Y")
RANGE_HOME = "1Y"                     # the declared home view AND the reset

# Calendar days back per preset. YTD and 1Y are resolved against the data.
_RANGE_DAYS = {"1M": 30, "3M": 91, "6M": 182}


def range_bounds(index, preset: str = RANGE_HOME):
    """The x-axis window for `preset`, as (start, end) — or None if unresolvable.

    PURE: no Streamlit, no plotly. It takes a DatetimeIndex and returns two
    timestamps, which is what makes it directly testable and what lets the
    "1Y restores the home view EXACTLY" assertion be an equality check rather
    than an eyeball.

    RANGE_HOME returns the data's own full span rather than "today minus 365
    days". Those are not the same window — the series carries ~251 trading bars
    over a 365-day calendar, so a date-arithmetic 1Y would leave a sliver of
    empty axis at the left edge and, worse, would not be reproducible: it would
    drift every day while the recorded fixture stayed still. The full span is
    stable, and it is the range a reader sees on first paint.
    """
    # pandas stays out of theme.py's module-level imports, which are html/re/
    # numpy by design — same reasoning as the lazy `import streamlit` in
    # inject_css/notice/section.
    import pandas as pd

    if index is None or len(index) == 0:
        return None
    start, end = index[0], index[-1]
    if preset == RANGE_HOME:
        return (start, end)
    if preset == "YTD":
        want = end.replace(month=1, day=1)
    else:
        days = _RANGE_DAYS.get(preset)
        if days is None:                       # unknown preset -> home, not a crash
            return (start, end)
        want = end - pd.Timedelta(days=days)
    # Clamp. A short series (a young listing, or a trimmed fixture) can start
    # AFTER the requested window, and an x-range reaching into empty space
    # renders as a chart that looks broken rather than one that looks short.
    return (max(want, start), end)


def range_control(key: str, *, presets=RANGE_PRESETS, default: str = RANGE_HOME) -> str:
    """Render the range picker; return the ACTIVE preset.

    Real Streamlit widgets, not modebar icons. That buys three things the
    modebar could not: they are in the tab order and operable from the
    keyboard, they inherit the app's own 44px-plus tap targets on mobile
    instead of the modebar's ~20px glyphs, and they carry text labels rather
    than icons whose meaning has to be inferred.

    Cost is honest: 5 tab stops per series chart. The modebar was 7 per chart
    across FIVE charts (~24 of ~40 focus stops on the Dashboard were plumbing);
    this is 5 stops across the two charts that are actually series. Fewer
    stops, and every one of them does something a reader asked for.
    """
    import streamlit as st
    state_key = f"_range_{key}"
    epoch_key = f"_epoch_{key}"
    st.session_state.setdefault(state_key, default)
    st.session_state.setdefault(epoch_key, 0)

    def _bump():
        # Fires on EVERY interaction with the control, including re-selecting
        # the preset that is already active. See chart_key() for why that case
        # is the one that matters.
        st.session_state[epoch_key] += 1

    current = st.session_state[state_key]
    picked = st.segmented_control(
        "Time range", list(presets),
        default=current if current in presets else default,
        key=f"{state_key}_widget", label_visibility="collapsed",
        on_change=_bump,
    )
    # segmented_control returns None when the user clicks the ALREADY-ACTIVE
    # item, which deselects it. Falling through with None would blank the
    # chart's range and, on the next rerun, silently snap it back to the
    # default — the same class of defect that made st.tabs unusable as the view
    # router here. Keep the last real choice; a range chart always has a range.
    if picked:
        st.session_state[state_key] = picked
    return st.session_state[state_key]


def chart_key(key: str, preset: str) -> str:
    """The `key=` for a series chart's st.plotly_chart. Bumping it resets pan.

    THIS EXISTS BECAUSE STREAMLIT PERSISTS PLOTLY VIEW STATE, which is not
    obvious and is not documented where you would look for it. Every plotly
    relayout — a pan is one — writes the whole mutated figure into
    WidgetStateManager.elementStates, keyed on an element id that Streamlit
    hashes FROM THE FIGURE SPEC (streamlit/elements/plotly_chart.py, "to also
    allow non-widget Plotly charts to keep their state"). Nothing re-derives
    the axes from the incoming spec after mount.

    The consequence is a trap with a very narrow mouth. Switching preset
    changes the spec, so the id changes, so the chart remounts and the pan is
    discarded — reset appears to work perfectly. But pan while ALREADY on the
    home preset and press home again: the spec is byte-identical, the id is
    unchanged, the component never remounts, and the pan survives the button
    that exists to undo it. That is the original defect wearing a different
    hat, and it would have shipped looking fixed.

    An explicit epoch in the key closes it. `key` is hashed IN ADDITION to the
    spec (key_as_main_identity=False), so changing it always forces a remount.

    Not `uirevision`: Streamlit never reads that property — it only "works" by
    perturbing the same spec hash, which is this mechanism by accident and via
    a figure property that means something else to plotly.
    """
    import streamlit as st
    return f"{key}-{preset}-{st.session_state.get(f'_epoch_{key}', 0)}"


# A NEUTRAL ramp for strength, used where green/red already mean something else.
#
# On the Bull vs Bear exchange the two sides are now colour-coded territories,
# so GOOD/BAD read as "bull/bear" there — and a claim's strength badge drawn
# from the same palette put a GREEN "HIGH" pill inside the bear's red field,
# where it looks like good news rather than a strong argument. Two meanings for
# one colour on one screen; the newer meaning wins, so strength gets its own
# scale. Encoded by lightness, which is the natural ordering for a magnitude.
# Light TEXT on a dark chip, not dark ink on a light fill like the status
# badges. The fill version cannot work here: a three-step ramp dark enough to
# order by lightness puts "low" on a fill where the PAGE-coloured label
# measures 1.65:1. Inverting it means all three tiers order by lightness AND
# all three clear 4.5:1 — the ramp is in the ink, where there is room for it.
STRENGTH_COLOR = {"high": INK, "medium": INK_2, "low": MUTED,
                  "strong": INK, "weak": MUTED}
STRENGTH_CHIP = "#232320"   # the shared chip behind all three tiers


def badge(text: str, kind: str = "medium", *, neutral: bool = False) -> str:
    """Return an HTML pill for a strength/likelihood/side label. Use with
    st.markdown(..., unsafe_allow_html=True). `kind` is high/medium/low or
    bull/bear/inconclusive; unknown kinds fall back to muted.

    12px, not 11px: this pill carries the judge's verdict — the payoff of a
    five-call orchestration — and 11px was below any practical UI floor.
    """
    if neutral:
        ink = STRENGTH_COLOR.get(kind.lower(), MUTED)
        fill, border = STRENGTH_CHIP, f"border:1px solid {ink}55;"
    else:
        ink = PAGE
        fill = LEVEL_COLOR.get(kind.lower(),
                               SIDE_COLOR.get(kind.lower(), MUTED))
        border = ""
    return (f"<span class='rs-badge' style='background:{fill};color:{ink};"
            f"{border}padding:3px 10px;border-radius:{RADIUS_PILL};"
            f"font-size:12px;font-weight:700;letter-spacing:.02em;"
            f"white-space:nowrap'>{safe(text)}</span>")


def fmt_money(x, sym: str = "$") -> str:
    """Money, with the sign OUTSIDE the currency symbol: -$1,418.00.

    The previous form put the symbol first and produced "$-1,418.00", which
    reads as a currency called "$-" before it reads as a loss.
    """
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    if x < 0:
        return f"-{sym}{abs(x):,.2f}"
    return f"{sym}{x:,.2f}"


def fmt_money_md(x, sym: str = "$") -> str:
    """fmt_money for a MARKDOWN context (st.caption, st.markdown).

    A bare `$` opens a LaTeX span in Streamlit's markdown, so any sentence
    containing two of them silently swallows everything between — which is
    exactly how the judge card's "weakest bear claim" turned into a green code
    block, and exactly what happened again to the cash-reconciliation caption
    on the dashboard the first time it was written with plain fmt_money.
    """
    return fmt_money(x, sym).replace("$", "\\$")


def fmt_pct(x) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    return f"{x:+.2f}%"


def signed_hex(v) -> str:
    """Just the colour, for callers building their own `style=` attribute.

    signed_color() returns a whole CSS declaration ("color: #1ba420"), which
    callers were splitting on ': ' to get the hex back out — a string-surgery
    dependency on the exact spacing of another function's return value. Two
    functions, one source.
    """
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return MUTED
    if v > 0:
        return GOOD
    if v < 0:
        return BAD
    return INK_2


def signed_color(v) -> str:
    """CSS color DECLARATION for a signed number: green up, red down, muted
    zero/NaN. Use signed_hex() when you need the bare colour.

    Colour is REDUNDANT here, never sole: fmt_pct always emits an explicit
    +/- sign and st.metric deltas carry an arrow glyph, so the meaning survives
    for a red-green colour-blind reader with colour stripped entirely.
    """
    return f"color: {signed_hex(v)}"


# --------------------------------------------------------------------------
# The CSS layer
# --------------------------------------------------------------------------
# Streamlit gives you framework defaults for everything a user touches. This is
# the one place the product gets to overrule them. Keep it small and keep every
# rule justified — this is a design system, not a stylesheet dump.

# Every rule below is scoped with `section.stMain`, NOT
# `[data-testid="stMain"]`. That testid is not stable across views: when a page
# uses st.chat_input — the "Ask the analyst" view does — Streamlit renames the
# main scroller's testid to `stAppScrollToBottomContainer`. All 44 scoped rules
# in this stylesheet therefore stopped matching on that one view, and it
# silently rendered with NONE of the design system: no panels, no surface
# treatment, no focus ring, no responsive breakpoints, and headings at roughly
# double size (h1 41px against 22px everywhere else).
#
# It failed silently and looked like a different app. The class survives in
# both states; the testid does not. Prefer the class.
_CSS = f"""
<style>
/* ---- 1. Keyboard focus -------------------------------------------------
   The tab strip previously had NO focus indicator at all: outline none,
   box-shadow none, no pseudo-element. The app's only top-level navigation was
   invisible to a keyboard user. :focus-visible keeps it off for mouse users. */
/* [role="tab"] was in this list and matches NOTHING: the app moved from
   st.tabs to st.segmented_control, whose items are
   `button[data-variant="segmented_control"]` — already covered by `button`
   here. Verified zero [role="tab"] nodes across all four views. */
section.stMain :is(button, a, input, select, summary,
                           [role="combobox"], [tabindex="0"]):focus-visible,
[data-testid="stSidebar"] :is(button, a, input, select, summary,
                              [role="combobox"], [tabindex="0"]):focus-visible {{
  outline: 2px solid {FOCUS} !important;
  outline-offset: 2px !important;
  border-radius: {RADIUS_PANEL};
}}

/* ---- 2. Primary buttons ------------------------------------------------
   Text colour is deliberately NOT overridden here — but the reason recorded
   in this comment for two revisions was WRONG, and the wrong reason is why a
   real failure survived.

   The old note said: "a detector reported white-on-#3987e5 at 3.64:1, but
   Streamlit darkens primaryColor to rgb(24,96,185) where white measures
   6.15:1, so the detector is wrong and flipping the label to ink would make it
   worse." Re-measured in the live DOM: the resting background is
   rgb(57,135,229) — the declared value, NOT darkened. rgb(24,96,185) is the
   :HOVER background. The original measurement sampled a hovered button and
   generalised it to the control, and the detector had been right all along:
   3.64:1, failing AA for a 15px/650 label.

   Fixed at the source instead of here — primaryColor is now #1d74dd in
   .streamlit/config.toml, where white measures 4.57:1 and every derived state
   (hover, active, focus) moves with it. Overriding the label colour here would
   still be wrong: ink passes at rest and fails on hover, so it trades one
   broken state for another.

   The standing lesson survives, sharpened: measure the COMPUTED background of
   a rendered button — and measure it in the state you are claiming. */
button[kind="primary"], button[data-testid="stBaseButton-primary"] {{
  font-weight: 650 !important;
  border: none !important;
  transition: filter 140ms cubic-bezier(.2,.7,.3,1),
              transform 140ms cubic-bezier(.2,.7,.3,1);
}}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {{
  filter: brightness(1.12);
  transform: translateY(-1px);
}}
button[kind="primary"]:disabled, button[data-testid="stBaseButton-primary"]:disabled {{
  filter: saturate(.25) brightness(.8);
  transform: none;
  cursor: progress;
}}

/* ---- 3. Prose measure --------------------------------------------------
   The 980px content column ran body copy at ~133 characters per line, roughly
   double the readable measure. Explanatory prose is the product's whole voice;
   it should not be the hardest thing on the page to read.

   Applied to paragraphs only, never to a wrapper: wrapping markdown in a
   block-level div suspends markdown parsing (CommonMark HTML-block rule) and
   this app's copy is full of **bold**. Charts, tables, dataframes and metric
   tiles are untouched — they want the full width, and none of them is a <p>. */
section.stMain [data-testid="stMarkdownContainer"] > p {{
  max-width: 68ch;
}}

/* ---- 4. Section grouping -----------------------------------------------
   st.divider() is a 1px hairline being asked to do the work of a section
   boundary, across a 2,489px scroll containing nine distinct analyses. */
h2.rs-section {{
  /* Sentence case, not uppercase. These labels are real sentences a beginner
     is asking ("How concentrated you really are"), and setting a 37-character
     sentence in all-caps costs more legibility than the tidiness is worth —
     all-caps slows reading by removing word-shape cues, and the effect scales
     with length. The hairline rule below does the separating instead. */
  font-size: .95rem !important;
  font-weight: 600 !important;
  letter-spacing: -0.005em;
  color: {INK_2};
  margin: 2.25rem 0 .75rem !important;
  padding: 0 0 .45rem !important;
  border-bottom: 1px solid {AXIS};
}}

/* ---- 5. Page plane -----------------------------------------------------
   A blue->violet wash giving the plane a temperature, so the panels above it
   read as raised. It is NOT the design.

   It is VIEWPORT-ANCHORED, not page-anchored, and that is a property of the
   framework rather than a choice: this container is exactly viewport-sized
   (measured 1440x721 while the document scrolled to 3467), because the actual
   scroller is section.stMain. So the wash behaves like a fixed
   backdrop that content slides over — it does NOT fade out as you scroll down
   the page. Written down because the first version of this comment claimed the
   opposite, and anyone reasoning from that description would place the
   gradient stops wrong.

   STATIC, deliberately — and NOT for the reason you would guess. The rerun
   model was verified not to be the problem: an animation on this node survives
   reruns intact (startTime constant, currentTime advancing monotonically
   across four view switches), because Streamlit diffs this element rather than
   replacing it. The animation was cut on design grounds, which still hold:

     1. The demo. A 45s-period gradient at this alpha is either invisible
        inside a five-second shot or turns into codec banding. The effect was
        justified BY the video and is one of the least likely to survive being
        recorded.
     2. The data. Every headline number here is a signed red/green value whose
        whole meaning is "did this change". Continuous low-frequency luminance
        drift underneath teaches the eye to discount small changes in exactly
        that region. On this surface, the only thing that should move is data.

   Film grain was cut with it: high-frequency noise is the most expensive thing
   you can hand a video encoder, and it would eat the bitrate that is otherwise
   rendering the numbers crisply. */
[data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(1200px 680px at 18% -6%, rgba(57,135,229,.13) 0%, transparent 62%),
    radial-gradient(1000px 640px at 82% -2%, rgba(139,92,246,.11) 0%, transparent 60%),
    radial-gradient(1400px 900px at 50% 6%, #17171b 0%, {PAGE} 58%),
    {PAGE};
}}

/* The measured grid. A single fixed, non-interactive layer, radially masked so
   it is present behind the masthead and gone by the time the reader is doing
   actual work. 1.8% white — at the threshold where it registers as texture
   rather than as lines you could count. */
[data-testid="stAppViewContainer"]::before {{
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  /* .025 — arrived at from both directions. At .018 an A/B pixel diff proved
     the grid was technically rendering (72,000 pixels differing on a clean
     64px pitch) while being perceptually invisible at 1440; CSS you cannot
     point at in a defence is waste, not restraint. But .035 went too far the
     other way: this overlay composites into the effective page background, and
     at .035 it was contributing about a third of the luminance lift that
     pushed MUTED-on-page below AA. .025 registers and costs ~0.14 of a ratio
     point. Decoration that changes a contrast measurement is not decoration. */
  background-image:
    repeating-linear-gradient(to right, rgba(255,255,255,.025) 0 1px, transparent 1px 64px),
    repeating-linear-gradient(to bottom, rgba(255,255,255,.025) 0 1px, transparent 1px 64px);
  -webkit-mask-image: radial-gradient(1250px 820px at 50% -4%, #000 0%, transparent 72%);
          mask-image: radial-gradient(1250px 820px at 50% -4%, #000 0%, transparent 72%);
}}
/* Content paints above the grid. Without this the fixed layer sits over the
   app rather than under it, and every click lands on nothing. */
section.stMain, [data-testid="stSidebar"] {{
  position: relative;
  z-index: 1;
}}
[data-testid="stSidebar"] {{
  background: {SURFACE};
  border-right: 1px solid {AXIS};
}}

/* ---- 6. Masthead -------------------------------------------------------
   The 44px/700 product name outweighed the user's own portfolio value
   (36px/400) on every screen. On an Operate surface the user's money is the
   headline; the product's name is a label. */
section.stMain h1 {{
  font-size: 1.45rem !important;
  font-weight: 640 !important;
  letter-spacing: -0.012em;
  margin-bottom: .1rem !important;
}}
/* View titles. h2 so the outline nests h1 > h2 view > h3 section without a
   skip; sized down from Streamlit's default so the user's numbers stay the
   loudest thing on the page. `:not(.rs-section)` keeps the section labels
   below on their own much quieter treatment. */
section.stMain h2:not(.rs-section) {{
  font-size: 1.6rem !important;
  font-weight: 650 !important;
  letter-spacing: -0.018em;
  padding-top: .5rem !important;
}}
[data-testid="stMetricValue"] {{
  font-weight: 600 !important;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}}
[data-testid="stMetricLabel"] {{ font-size: .78rem !important; }}

/* ---- 6b. The 1024px clip ----------------------------------------------
   A 4-across metric row plus the 300px fixed sidebar left each tile 129px
   for a value needing 160px, so at 1024px the HEADLINE NUMBER — the user's
   total portfolio value — silently ellipsis-clipped to "$47,332...". A
   number that truncates is worse than no number: it is quietly wrong.

   Two independent guards, because either alone can still fail on a long
   currency or a narrow window:
     1. below 1150px the 4-across row wraps to 2x2 (2-across rows are
        unaffected — 50% basis is what they already have);
     2. the value itself may wrap instead of clipping, whatever the width. */
@media (max-width: 1150px) {{
  section.stMain [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  section.stMain [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 calc(50% - 1rem) !important;
    min-width: calc(50% - 1rem) !important;
  }}
}}
/* ...but 50% is a FLOOR as well as a basis, so on a phone it held the lede's
   7:5 split side by side in 390px and the headline clipped to "$47,332..." —
   the identical defect this app fixed once at 1024px and then reintroduced by
   generalising the fix. A number that truncates is quietly wrong, which is
   worse than absent.

   Below 720px, columns stack outright. Anything narrower than that has no
   business being two columns. */
@media (max-width: 720px) {{
  section.stMain [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }}
}}

/* ---- 6b. The sidebar OVERLAYS on a phone; it does not squeeze ----------
   Measured in a real 390px viewport, not inferred: opening the sidebar left
   `section.stMain` at 90px wide. The page title wrapped to "Robo / Smar / t /
   Deba / te / Club" — one word per line, six lines — and the lede's figures
   went with it. The sidebar is a fixed 300px, so on a 390px phone there are
   90px left over and Streamlit spends them rendering the page rather than
   getting out of the way.

   `position: fixed` lifts the sidebar out of the flex row, so main keeps the
   full viewport and the panel floats above it. That is what a drawer is.

   THE SCRIM IS A BOX-SHADOW, and that is a deliberate choice rather than a
   trick for its own sake. Streamlit already ships outside-tap-to-dismiss — a
   document-level `mousedown` listener, live below 767.98px, which collapses
   the sidebar when the event target is inside the app and outside
   `stSidebarContent`. It works; it is simply invisible, because Streamlit
   draws no dimming layer, so nothing tells a reader the gesture exists.

   An overlay <div> would announce it — and would also become the mousedown
   target. `pointer-events:none` would fix that, but it is one careless edit
   away from silently breaking a working interaction. A box-shadow cannot take
   a pointer event at all: there is no element to hit. The affordance becomes
   visible and the handler underneath it stays untouched by construction.
   Verified in the browser: with this rule applied, an outside tap still flips
   aria-expanded true -> false.

   100vmax of spread covers any viewport in both axes. Breakpoint is
   767.98px to match Streamlit's own threshold exactly (its `md` breakpoint,
   768px, minus the 0.02 it subtracts) — a near-miss here would leave a band
   of widths where the panel floats but the tap-to-dismiss does not fire.

   No transition, deliberately: rule 7's `prefers-reduced-motion` block is an
   explicit allow-list, so an animated selector added here would silently
   escape it. */
@media (max-width: 767.98px) {{
  section[data-testid="stSidebar"][aria-expanded="true"] {{
    position: fixed !important;
    top: 0; bottom: 0; left: 0;
    height: 100dvh !important;
    z-index: 999991 !important;
    box-shadow: 0 0 0 100vmax rgba(0, 0, 0, .62);
  }}
}}
[data-testid="stMetricValue"] > div,
[data-testid="stMetricLabel"] > div {{
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
}}
/* Tabular figures everywhere a number can change under the reader. */
[data-testid="stMetricDelta"], .rs-num {{ font-variant-numeric: tabular-nums; }}

/* ---- 7. Motion ---------------------------------------------------------
   ONE constraint shapes all of this: Streamlit rebuilds the DOM on every
   rerun, and with the view router a rerun happens whenever the sidebar is
   touched. So a conventional "entrance animation" is not a first-paint
   flourish here — it is something the user re-watches every single time they
   change a ticker. That rules out decorative reveals entirely.

   The rule adopted instead: motion is attached to a STATE CHANGE the user
   caused, and its duration is inversely proportional to how often it fires.
     - the verdict arriving  (rare, earned)      -> 620ms, the authored moment
     - a view being switched (occasional)        -> 420ms, a brief settle
     - hover / press         (constant)          -> 120-160ms, barely felt
   Everything eases on one exponential curve so the product moves like one
   thing, and every animated element's DEFAULT state is the finished state —
   nothing is ever stranded invisible if the animation does not run. */
:root {{
  --rs-ease: cubic-bezier(.16, 1, .3, 1);   /* exponential ease-out */
  --rs-quick: 140ms;
  --rs-settle: 420ms;
  --rs-reveal: 620ms;
}}

/* The authored moment: the verdict. Settles from slightly soft, slightly low
   and slightly small — blur is doing the work that a plain fade cannot, which
   is to read as "coming into focus" rather than "appearing". */
.rs-verdict {{ animation: rs-settle var(--rs-reveal) var(--rs-ease) both; }}
@keyframes rs-settle {{
  from {{ opacity: .55; transform: translateY(10px) scale(.994); filter: blur(3px); }}
  to   {{ opacity: 1;   transform: none;                        filter: blur(0); }}
}}
.rs-verdict-rule {{
  height: 2px; border: 0; margin: 0 0 1rem;
  background: linear-gradient(90deg, {CONNECTOR}, transparent);
  animation: rs-draw 720ms var(--rs-ease) both;
}}
@keyframes rs-draw {{ from {{ transform: scaleX(0); transform-origin: left; }} }}

/* A view switch settles its metric row and its charts. Staggered by a few
   tens of ms so the row reads left-to-right rather than flashing as a block —
   short enough that repeat viewings never feel like waiting. */
section.stMain [data-testid="stMetric"],
section.stMain .stPlotlyChart,
section.stMain .rs-table-wrap {{
  animation: rs-rise var(--rs-settle) var(--rs-ease) both;
}}
@keyframes rs-rise {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to   {{ opacity: 1; transform: none; }}
}}
section.stMain [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] {{ animation-delay: 0ms; }}
section.stMain [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {{ animation-delay: 45ms; }}
section.stMain [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {{ animation-delay: 90ms; }}
section.stMain [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {{ animation-delay: 135ms; }}

/* Constant-frequency interactions: felt, not watched. */
section.stMain [role="radio"] {{
  transition: background-color var(--rs-quick) var(--rs-ease),
              color var(--rs-quick) var(--rs-ease);
}}
table.rs-table tbody tr {{
  transition: background-color var(--rs-quick) var(--rs-ease);
}}
.rs-notice {{ animation: rs-rise var(--rs-settle) var(--rs-ease) both; }}

/* Honour the user's system setting. The app previously authored no motion at
   all, so this rule had nothing to protect; now it protects all of it. The
   `both` fill on every animation above means removing it leaves each element
   in its finished state, never mid-keyframe. */
@media (prefers-reduced-motion: reduce) {{
  .rs-verdict, .rs-verdict-rule, .rs-notice,
  section.stMain [data-testid="stMetric"],
  section.stMain .stPlotlyChart,
  section.stMain .rs-table-wrap {{
    animation: none !important;
  }}
  button[kind="primary"], button[data-testid="stBaseButton-primary"],
  section.stMain [role="radio"], table.rs-table tbody tr {{
    transition: none !important;
  }}
  button[kind="primary"]:hover {{ transform: none; }}
}}

/* ---- 8. Holdings table -------------------------------------------------
   A real <table>, replacing st.dataframe. The Streamlit grid paints to
   <canvas> and its accessibility fallback carried the RAW floats — it
   announced "513.8399999999999" where the screen showed "$513.84", and
   "150" where the screen showed "$150.00". The pandas Styler .format()
   never reached the a11y tree at all, because it only styled the paint.
   A semantic table also drops the 4-button grid toolbar and the canvas
   focus trap, which together were ~6 tab stops of plumbing. */
.rs-table-wrap {{ overflow-x: auto; margin: .25rem 0 .5rem; }}
table.rs-table {{
  width: 100%; border-collapse: collapse;
  font-variant-numeric: tabular-nums;
  font-size: .875rem;
}}
table.rs-table caption {{
  caption-side: top; text-align: left;
  color: {MUTED}; font-size: .78rem; padding-bottom: .5rem;
}}
table.rs-table th, table.rs-table td {{
  padding: .55rem .7rem; text-align: right; white-space: nowrap;
}}
table.rs-table th:first-child, table.rs-table td:first-child {{
  text-align: left; font-weight: 650;
}}
table.rs-table thead th {{
  color: {MUTED}; font-weight: 600; font-size: .74rem;
  text-transform: uppercase; letter-spacing: .05em;
  border-bottom: 1px solid {AXIS};
}}
table.rs-table tbody tr {{ border-bottom: 1px solid #232320; }}
table.rs-table tbody tr:last-child {{ border-bottom: 0; }}
table.rs-table tbody tr:hover {{ background: {SURFACE}; }}
table.rs-table td.rs-pos {{ color: {GOOD}; }}
table.rs-table td.rs-neg {{ color: {BAD}; }}
table.rs-table td.rs-flat {{ color: {INK_2}; }}

/* ---- 11. The surface system -------------------------------------------
   THE fix for "the app looks basic". Before this the app had exactly one
   surface: the page plane was painted, and the only things above it were
   Plotly's own rectangles. Four headline numbers, the prose, the holdings
   table and the section rules all sat directly on flat black. A designed dark
   product has page -> panel -> raised element; this had page -> chart. That
   missing middle is what "basic" actually was, and it is why adding light
   behind it would not have helped: light behind a flat plane is a lit flat
   plane.

   The panel is deliberately NOT the default card. The recipe everybody ships —
   1px border all round, 12px radius, inset highlight, soft even shadow, hover
   lift — is the shadcn/Bootstrap card verbatim, and applied uniformly it reads
   as a component library rather than as a product.

   This one is LIT FROM ABOVE instead: a 1px top edge, no full border, and a
   bottom-weighted shadow. Panels then read as raised by a light source the
   page shares, which is also why the wash above sits at the top. And no hover
   lift — these panels are not interactive, and animating them on hover would
   promise a click that does not exist. */
section.stMain [data-testid="stMetric"],
section.stMain .stPlotlyChart,
section.stMain .rs-table-wrap {{
  /* The gradient's LIGHTEST point is exactly SURFACE, never lighter. Every
     ratio in the contract above was measured against SURFACE, so a panel fill
     that brightened past it would silently move all of them at once — the
     first attempt (#1e1e1c -> #161615) cost GOOD and BAD 0.22 each, which is
     not visible and is exactly why it would have shipped. The gradient is
     therefore allowed to run DARKER only, where contrast improves.
     The "lit from above" reading comes from the inset top edge below, not
     from the fill. */
  background: linear-gradient(180deg, {SURFACE} 0%, #151514 100%);
  border-radius: {RADIUS_PANEL};
  box-shadow: inset 0 1px 0 rgba(255,255,255,.07),
              0 8px 22px -14px rgba(0,0,0,.95);
}}
section.stMain [data-testid="stMetric"] {{
  padding: .85rem 1rem 1rem;
  /* A row of four cards MUST share a bottom edge. One metric carrying a delta
     pill and three without left the row ragged by ~25px — a defect the panel
     treatment CREATED, because unboxed tiles hid it. */
  height: 100%;
}}
section.stMain [data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
section.stMain .stPlotlyChart {{ padding: .4rem .4rem 0; overflow: hidden; }}
section.stMain .rs-table-wrap {{ padding: .3rem 1rem .55rem; }}

/* ---- 13. The lede block ------------------------------------------------
   The page's primary object. Targeted through `.st-key-rs_lede`, the class
   Streamlit emits for `st.container(key="rs_lede")` — which is how you style a
   NATIVE container rather than rebuilding one in raw HTML and losing the
   columns, the chart and the responsive behaviour that come with it.

   Answer-weight radius and a deeper shadow than a standard panel: it is one
   level above everything else on the page, and it should be the only thing on
   the tab that is. */
section.stMain .st-key-rs_lede {{
  background: linear-gradient(180deg, {SURFACE} 0%, #151514 100%);
  border-radius: {RADIUS_HERO};
  box-shadow: inset 0 1px 0 rgba(255,255,255,.075),
              0 16px 38px -20px rgba(0,0,0,.95);
  padding: 1.35rem 1.6rem 1.05rem;
  margin-bottom: 1.6rem;
}}

/* No cards inside cards. The donut and all four metrics inherit the panel
   treatment from rule 11 by selector; inside the lede they must be plain, or
   the tab opens on boxes inside a box — the single most reliable way to make
   an interface look assembled rather than designed. */
section.stMain .st-key-rs_lede .stPlotlyChart,
section.stMain .st-key-rs_lede [data-testid="stMetric"] {{
  background: none;
  box-shadow: none;
  padding: 0;
}}

/* The headline. ~3.4rem against a .72rem label puts the page's type scale near
   6x, where it was about 3x — and a narrow scale range is most of what
   "uniform and basic" actually is.

   clamp() rather than a fixed size: this app has already shipped a headline
   number that ellipsis-clipped to "$47,332..." at 1024px, and a number that
   truncates is worse than no number because it is quietly wrong. */
section.stMain .st-key-rs_headline [data-testid="stMetricValue"] {{
  font-size: clamp(2.1rem, 4.6vw, 3.4rem) !important;
  line-height: 1.03;
  letter-spacing: -.022em;
  /* Belt as well as braces. The stacking rule above is what actually stops the
     clip; this guarantees that if a longer currency or a narrower viewport
     ever gets past it, the value WRAPS rather than silently ellipsing. */
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
}}
section.stMain .st-key-rs_headline [data-testid="stMetricLabel"] {{
  font-size: .72rem !important;
  letter-spacing: .10em;
  text-transform: uppercase;
}}
section.stMain .st-key-rs_headline [data-testid="stMetricDelta"] {{
  font-size: 1rem;
  padding-top: .25rem;
}}

/* Body face, not mono, and deliberately so: rule 12's principle is that
   figures the reader COMPARES get mono while figures the reader READS stay in
   the body face. This is a sentence. */
.rs-lede-mover {{
  color: {INK_2}; font-size: .95rem; line-height: 1.55;
  max-width: 46ch; margin: 1.1rem 0 0;
}}

/* The meta strip: same three facts that used to be headline tiles, now clearly
   subordinate. A rule above it does the separating, and the type drops to
   roughly a third of the headline's size. */
section.stMain .st-key-rs_lede_meta {{
  border-top: 1px solid {AXIS};
  margin-top: 1.2rem;
  padding-top: .9rem;
  gap: 2.4rem;
  flex-wrap: wrap;
}}
section.stMain .st-key-rs_lede_meta [data-testid="stMetricValue"] {{
  font-size: .95rem !important;
}}
section.stMain .st-key-rs_lede_meta [data-testid="stMetricLabel"] {{
  font-size: .68rem !important;
  letter-spacing: .08em;
  text-transform: uppercase;
}}
section.stMain .st-key-rs_lede_meta [data-testid="stMetricDelta"] {{
  font-size: .8rem;
}}

/* ---- 14. Bull vs Bear as a confrontation ------------------------------
   The two sides were visually identical `st.container(border=True)` boxes in
   two columns, separated by a 10px uppercase word — so the most distinctive
   thing this product does read as a two-column list of grey boxes.

   Each side now holds tinted TERRITORY. The tint is strongest at the outer
   edge and fades toward the centre gutter, so the block reads as two forces
   meeting in the middle rather than as two lists side by side. A solid 2px
   outer wall in the side's own colour anchors it.

   Deliberately no radius and no shadow: this is a FIELD, not a card. The claim
   cards inside it are the cards, and a card containing cards is how an
   interface starts to look assembled. Colour is never doing this alone — the
   side header names it, and every card repeats a `_card_marker`, because this
   header scrolls away after about one screen. */
section.stMain .st-key-rs_side_bull_open,
section.stMain .st-key-rs_side_bull_reb {{
  background: linear-gradient(90deg, rgba(27,164,32,.11) 0%, rgba(27,164,32,0) 82%);
  border-left: 2px solid {GOOD};
  padding: .85rem 1rem 1rem;
}}
section.stMain .st-key-rs_side_bear_open,
section.stMain .st-key-rs_side_bear_reb {{
  background: linear-gradient(270deg, rgba(229,102,95,.11) 0%, rgba(229,102,95,0) 82%);
  border-right: 2px solid {BAD};
  padding: .85rem 1rem 1rem;
}}
/* The claim cards inside sit ON the tint, so they need their own opaque
   surface or the tint shows through and the cards stop separating from the
   field they sit in.

   The selector matters and was got wrong once here:
   `[data-testid="stVerticalBlockBorderWrapper"]` is a testid that does NOT
   exist in Streamlit 1.60 — it is absent from the whole installed package, so
   the rule matched nothing and looked fine in code review. What
   st.container(border=True) actually emits is a stLayoutWrapper holding a
   stVerticalBlock, with the border on the inner element. Verified in the real
   DOM; grep the installed frontend bundle before trusting a testid. */
section.stMain :is(.st-key-rs_side_bull_open, .st-key-rs_side_bull_reb,
                   .st-key-rs_side_bear_open, .st-key-rs_side_bear_reb)
  [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{
  background: {SURFACE};
  border-radius: {RADIUS_PANEL};
}}

/* ---- 12. Tabular figures ----------------------------------------------
   The single cheapest change that makes the analysis read as an instrument
   rather than as a web page with numbers on it. Monospace gives every digit
   the same advance width, so a column of money aligns on the decimal without
   being told to, and a value that changes under the reader does not reflow the
   text beside it.

   BOUNDED, on purpose, to tiles and tables. It is tempting to set every digit
   in the app in mono, and it is wrong: mono inside running prose — "a beta of
   0.60 means your invested equity tends to move about 40% less" — fragments
   the sentence into a label and an argument, and undoes the plain-language
   voice this product commits to for its beginner reader. Figures the reader
   COMPARES get mono. Figures the reader READS stay in the body face.

   The fallback stack lives here rather than in config.toml because this is the
   part that must not degrade: if the Google Fonts fetch fails during a live
   defence, the numbers still land in a metric face rather than reflowing into
   a proportional one mid-demo. */
section.stMain [data-testid="stMetricValue"],
section.stMain [data-testid="stMetricDelta"],
section.stMain table.rs-table,
section.stMain .rs-num {{
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, "SF Mono",
               Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums slashed-zero;
}}
/* Mono is already evenly spaced; the -0.02em that a proportional face needed
   at display size closes it up too far here. */
section.stMain [data-testid="stMetricValue"] {{ letter-spacing: -0.005em; }}

/* .rs-notice is deliberately NOT in that list. It carries its own tinted
   background and a coloured 1px border, because a status panel must read as a
   different KIND of thing from a data panel. Adding the surface treatment on
   top would double its border and fight its radius. */

/* ---- 9. View router ----------------------------------------------------
   Gives the selected view a weight difference a scanning eye can catch
   without reading, on top of the focus ring in rule 1.

   This rule was previously written against `[role="tab"][aria-selected]` and
   styled NOTHING — it was left behind when the app moved from st.tabs to
   st.segmented_control, and dead CSS is worse than no CSS because it reads as
   a solved problem. The real markup, verified in the live DOM:

     [data-testid="stButtonGroup"]                              container
     button[data-variant="segmented_control"]                   items
     button[data-variant="segmented_control"][aria-checked]     the active item

   Use aria-checked, not data-selected: inactive items carry no data-selected
   attribute at all, so [data-selected="false"] matches nothing. */
section.stMain button[data-variant="segmented_control"][aria-checked="true"] {{
  font-weight: 650;
  /* Ink DECOUPLED from primaryColor, and this is the interesting one.
     primaryColor plays two opposite roles in Streamlit: a FILL behind white on
     a button, and INK on a 10% tint for the selected router item. Darkening it
     to #1d74dd to fix the button (3.64 -> 4.57:1) therefore pushed the router
     the other way, from a passing 4.85:1 to 3.02:1 — trading a button failure
     for a navigation failure in the same token, on the app's only top-level
     control.
     One token cannot serve as both fill and ink. White on the same tint
     measures 13.8:1 and keeps the weight cue and aria-checked doing the
     selected/unselected work. */
  color: {INK} !important;
}}
/* ---- 15. The Guide dialog ----------------------------------------------
   SCOPED TO .stDialog, DELIBERATELY NOT NESTED UNDER section.stMain.

   Every other rule in this file is scoped to `section.stMain`, and that is
   correct — it is what survives Streamlit renaming the stMain testid on any
   view carrying a chat input. But a dialog renders through a PORTAL, outside
   the main section entirely, so `section.stMain .rs-guide-card` matches
   nothing and the Guide would render as unstyled default output. This is the
   one place in the app where the house scoping rule has to be set aside, and
   the reason is worth stating so nobody "fixes" it back.

   The cards deliberately reuse the panel grammar from rule 11 — lit top edge,
   no full border — rather than introducing a card system that exists only
   here. A guide that does not look like the product it is explaining is
   working against itself. */
[data-testid="stDialog"] .rs-guide-head {{
  font-size: .78rem; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase; color: {MUTED};
  margin: 1.6rem 0 .7rem;
}}
[data-testid="stDialog"] .rs-guide-card {{
  background: linear-gradient(180deg, {SURFACE} 0%, #151514 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.07), 0 2px 10px rgba(0,0,0,.35);
  border-radius: {RADIUS_PANEL};
  padding: .95rem 1.05rem;
  height: 100%;
}}
[data-testid="stDialog"] .rs-guide-title {{
  font-weight: 650; font-size: 1rem; color: {INK}; margin-bottom: .35rem;
  letter-spacing: -.01em;
}}
[data-testid="stDialog"] .rs-guide-body {{
  color: {INK_2}; font-size: .89rem; line-height: 1.55;
}}
[data-testid="stDialog"] .rs-guide-steps {{
  color: {INK_2}; line-height: 1.62; padding-left: 1.15rem; margin: 0;
  max-width: 72ch;
}}
[data-testid="stDialog"] .rs-guide-steps li {{ margin: .3rem 0; }}
[data-testid="stDialog"] .rs-guide-steps b {{ color: {INK}; }}
[data-testid="stDialog"] .rs-guide-steps code {{
  background: #151514; color: {INK_2}; padding: .06rem .3rem;
  border-radius: 5px; font-size: .84em;
}}
/* The two card rows must stack on a phone, where the dialog is nearly the
   full viewport and a 2-across grid leaves ~150px per card. */
@media (max-width: 640px) {{
  [data-testid="stDialog"] [data-testid="stColumn"] {{
    flex: 1 1 100% !important; min-width: 100% !important;
  }}
}}
</style>
"""


def inject_css() -> None:
    """Install the product's CSS layer. Call once, early, from app.py."""
    import streamlit as st
    st.markdown(_CSS, unsafe_allow_html=True)


# Inline SVG, not emoji. Everywhere else in the app the emoji became Material
# Symbols (`:material/warning:`), but that token is a Streamlit MARKDOWN
# feature and notice() emits raw HTML, where it would render as literal text.
# So these are drawn instead — which is better anyway: an emoji is a font the
# OS picks, so ⚠️ arrived amber on macOS, flat on Windows and a different shape
# on Android, and it was the one glyph in the app the design system did not
# control. These inherit `currentColor`, so each notice's icon is exactly its
# own status colour and cannot drift.
_ICON_SVG = {
    # triangle + bang
    "warn": "<path d='M12 3 22 20H2z' fill='none' stroke='currentColor' stroke-width='2' "
            "stroke-linejoin='round'/><path d='M12 10v4' stroke='currentColor' "
            "stroke-width='2' stroke-linecap='round'/><circle cx='12' cy='17.2' r='1.15' "
            "fill='currentColor'/>",
    # check
    "good": "<path d='M4 12.5 9.5 18 20 6.5' fill='none' stroke='currentColor' "
            "stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/>",
    # chevron
    "info": "<path d='M9 5.5 16 12l-7 6.5' fill='none' stroke='currentColor' "
            "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>",
}

_NOTICE = {
    "warn": (WARN, "rgba(250,178,25,.09)", "warn"),
    "good": (GOOD, "rgba(12,163,12,.10)", "good"),
    "info": (CATEGORICAL[0], "rgba(57,135,229,.10)", "info"),
}


def notice(text: str, kind: str = "warn") -> None:
    """A polite status panel.

    st.warning / st.success render with role="alert" aria-live="assertive",
    which INTERRUPTS a screen reader. The concentration flags re-render on
    every rerun, and now that the view router reruns on every sidebar
    interaction, that is a lot of interrupting for a message that has not
    changed. role="status" is aria-live="polite": it still announces, it just
    waits for a gap in speech.

    Takes trusted, app-authored text.
    """
    import streamlit as st
    color, tint, icon_key = _NOTICE.get(kind, _NOTICE["warn"])
    icon = (f"<svg viewBox='0 0 24 24' width='16' height='16' "
            f"style='flex:0 0 16px;margin-top:.18rem'>{_ICON_SVG[icon_key]}</svg>")
    st.markdown(
        # ONE box grammar, two meanings. This used to carry a full 1px border
        # all round, which made it the only fully-outlined box in the app —
        # and because it sits near the top of every screen, the FIRST panel a
        # viewer met was in the old language and every panel after it was in
        # the new one. It should differ from a data panel by TINT, not by being
        # a different kind of object. Same lit-from-above top edge as rule 11,
        # plus a colour-coded left edge to carry the status.
        f"<div role='status' class='rs-notice' data-notice='{kind}' style='background:{tint};"
        f"border-left:2px solid {color};"
        f"box-shadow:inset 0 1px 0 rgba(255,255,255,.07);"
        f"border-radius:{RADIUS_PANEL};padding:.7rem .9rem;"
        f"margin:.35rem 0;display:flex;gap:.6rem;align-items:flex-start'>"
        f"<span aria-hidden='true' style='color:{color};line-height:1.5;display:flex'>{icon}</span>"
        f"<span style='color:{INK_2};line-height:1.55;max-width:68ch'>{text}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    """A real section boundary — the thing st.divider() was being asked to be.

    Emits an <h2>, not a styled div: the page previously went straight from
    <h1> to <h3> with no <h2> anywhere, so a screen-reader user navigating by
    heading had no way to move between the nine analyses stacked in one
    2,500px scroll. The visual treatment is deliberately quiet; the semantics
    are the point.
    """
    import streamlit as st
    st.markdown(f"<h2 class='rs-section'>{safe(label)}</h2>",
                unsafe_allow_html=True)
