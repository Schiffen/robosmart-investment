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

CONTRAST IS A CONTRACT HERE. Every token below was measured against the two
surfaces it renders on (PAGE #0d0d0d, SURFACE #1a1a19) and the ratio is written
next to it. If you change a colour, re-measure it — do not eyeball it. The
previous BAD (#d03b3b) sat at 4.05:1 while its GOOD counterpart sat at 5.79:1,
which meant losses were literally harder to read than gains.
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
MUTED = "#898781"        # axis / labels            5.4:1 on page
GRID = "#3a3a37"         # hairline gridline — recessive by design, non-essential
AXIS = "#383835"         # baseline / axis
CONNECTOR = "#6b6b64"    # waterfall connectors     3.2:1 on surface — MEANINGFUL,
                         # carries "these parts sum to the whole". Never drop it
                         # to GRID: at 1.2:1 the waterfall reads as four
                         # disconnected floating bars and the chart loses its point.
FOCUS = "#8ec0f7"        # keyboard focus ring     10.2:1 on page

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

def style_fig(fig, height: int = 340):
    """Apply the shared dark Plotly styling to any figure. Works on donut,
    heatmap, line, waterfall, bar — anything the tabs draw.

    `displayModeBar` is suppressed at the call site (see chart_config): the
    modebar contributed 7 tab stops per chart, and on the Dashboard that was
    ~24 of ~40 focus stops going to plumbing rather than to the app.
    """
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=INK_2, size=13, family="Source Sans Pro, system-ui, sans-serif"),
        margin=dict(l=10, r=10, t=48, b=10),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        title=dict(font=dict(color=INK, size=15)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=CONNECTOR,
                        font=dict(color=INK, size=12)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    return fig


# Passed to every st.plotly_chart. Kills the 7-button modebar.
CHART_CONFIG = {"displayModeBar": False, "displaylogo": False,
                "staticPlot": False, "scrollZoom": False}


def badge(text: str, kind: str = "medium") -> str:
    """Return an HTML pill for a strength/likelihood/side label. Use with
    st.markdown(..., unsafe_allow_html=True). `kind` is high/medium/low or
    bull/bear/inconclusive; unknown kinds fall back to muted.

    12px, not 11px: this pill carries the judge's verdict — the payoff of a
    five-call orchestration — and 11px was below any practical UI floor.
    """
    color = LEVEL_COLOR.get(kind.lower(), SIDE_COLOR.get(kind.lower(), MUTED))
    return (f"<span class='rs-badge' style='background:{color};color:{PAGE};"
            f"padding:3px 10px;border-radius:999px;font-size:12px;"
            f"font-weight:700;letter-spacing:.02em;white-space:nowrap'>"
            f"{safe(text)}</span>")


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


def signed_color(v) -> str:
    """CSS color string for a signed number: green up, red down, muted zero/NaN.

    Colour is REDUNDANT here, never sole: fmt_pct always emits an explicit
    +/- sign and st.metric deltas carry an arrow glyph, so the meaning survives
    for a red-green colour-blind reader with colour stripped entirely.
    """
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return f"color: {MUTED}"
    if v > 0:
        return f"color: {GOOD}"
    if v < 0:
        return f"color: {BAD}"
    return f"color: {INK_2}"


# --------------------------------------------------------------------------
# The CSS layer
# --------------------------------------------------------------------------
# Streamlit gives you framework defaults for everything a user touches. This is
# the one place the product gets to overrule them. Keep it small and keep every
# rule justified — this is a design system, not a stylesheet dump.

_CSS = f"""
<style>
/* ---- 1. Keyboard focus -------------------------------------------------
   The tab strip previously had NO focus indicator at all: outline none,
   box-shadow none, no pseudo-element. The app's only top-level navigation was
   invisible to a keyboard user. :focus-visible keeps it off for mouse users. */
[data-testid="stMain"] :is(button, a, input, select, summary, [role="tab"],
                           [role="combobox"], [tabindex="0"]):focus-visible,
[data-testid="stSidebar"] :is(button, a, input, select, summary,
                              [role="combobox"], [tabindex="0"]):focus-visible {{
  outline: 2px solid {FOCUS} !important;
  outline-offset: 2px !important;
  border-radius: 6px;
}}

/* ---- 2. Primary buttons ------------------------------------------------
   Text colour is deliberately NOT overridden here.

   A detector reported white-on-#3987e5 at 3.64:1 and the obvious fix looked
   like flipping the label to ink, matching the idiom badge() uses. Measured on
   the running app, that is wrong: Streamlit darkens primaryColor to
   rgb(24,96,185) for the button background in the dark theme, where white
   measures 6.15:1 (passes) and ink measures 3.16:1 (fails). Overriding it
   would have made the contrast worse than it started.

   If primaryColor ever changes in .streamlit/config.toml, re-measure the
   COMPUTED background of a rendered button rather than the declared token. */
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
[data-testid="stMain"] [data-testid="stMarkdownContainer"] > p {{
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
   A single low-contrast wash that gives the content column a centre of
   gravity. Deliberately not glass, not a gradient sweep, and not decoration
   with a blur radius: on an Operate surface the background's job is to stay
   out of the way while making the raised panels read as raised. */
[data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(1100px 620px at 50% -8%, #16161a 0%, {PAGE} 62%),
    {PAGE};
}}
[data-testid="stSidebar"] {{
  background: {SURFACE};
  border-right: 1px solid {AXIS};
}}

/* ---- 6. Masthead -------------------------------------------------------
   The 44px/700 product name outweighed the user's own portfolio value
   (36px/400) on every screen. On an Operate surface the user's money is the
   headline; the product's name is a label. */
[data-testid="stMain"] h1 {{
  font-size: 1.45rem !important;
  font-weight: 640 !important;
  letter-spacing: -0.012em;
  margin-bottom: .1rem !important;
}}
/* View titles. h2 so the outline nests h1 > h2 view > h3 section without a
   skip; sized down from Streamlit's default so the user's numbers stay the
   loudest thing on the page. `:not(.rs-section)` keeps the section labels
   below on their own much quieter treatment. */
[data-testid="stMain"] h2:not(.rs-section) {{
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
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    flex: 1 1 calc(50% - 1rem) !important;
    min-width: calc(50% - 1rem) !important;
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
[data-testid="stMain"] [data-testid="stMetric"],
[data-testid="stMain"] .stPlotlyChart,
[data-testid="stMain"] .rs-table-wrap {{
  animation: rs-rise var(--rs-settle) var(--rs-ease) both;
}}
@keyframes rs-rise {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to   {{ opacity: 1; transform: none; }}
}}
[data-testid="stMain"] [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] {{ animation-delay: 0ms; }}
[data-testid="stMain"] [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {{ animation-delay: 45ms; }}
[data-testid="stMain"] [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {{ animation-delay: 90ms; }}
[data-testid="stMain"] [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {{ animation-delay: 135ms; }}

/* Constant-frequency interactions: felt, not watched. */
[data-testid="stMain"] [role="radio"] {{
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
  [data-testid="stMain"] [data-testid="stMetric"],
  [data-testid="stMain"] .stPlotlyChart,
  [data-testid="stMain"] .rs-table-wrap {{
    animation: none !important;
  }}
  button[kind="primary"], button[data-testid="stBaseButton-primary"],
  [data-testid="stMain"] [role="radio"], table.rs-table tbody tr {{
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

/* ---- 9. Tab strip ------------------------------------------------------
   Gives the selected view a weight difference a scanning eye can catch
   without reading, on top of the focus ring in rule 1. */
[data-testid="stMain"] [role="tab"][aria-selected="true"] {{
  font-weight: 650;
}}
</style>
"""


def inject_css() -> None:
    """Install the product's CSS layer. Call once, early, from app.py."""
    import streamlit as st
    st.markdown(_CSS, unsafe_allow_html=True)


_NOTICE = {
    "warn": (WARN, "rgba(250,178,25,.09)", "⚠️"),
    "good": (GOOD, "rgba(12,163,12,.10)", "✅"),
    "info": (CATEGORICAL[0], "rgba(57,135,229,.10)", "›"),
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
    color, tint, icon = _NOTICE.get(kind, _NOTICE["warn"])
    st.markdown(
        f"<div role='status' class='rs-notice' data-notice='{kind}' style='background:{tint};"
        f"border:1px solid {color}44;border-radius:10px;padding:.7rem .9rem;"
        f"margin:.35rem 0;display:flex;gap:.6rem;align-items:flex-start'>"
        f"<span aria-hidden='true' style='color:{color};line-height:1.5'>{icon}</span>"
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
