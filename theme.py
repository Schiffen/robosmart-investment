"""
theme.py — SHARED design system for RoboSmart (proposed by Person 2).
=====================================================================
Every tab imports from here so the Portfolio Dashboard, the Bull vs Bear
debate, and the "What happened today" attribution tab read as ONE product.
Built on the dataviz reference palette (dark steps). Person 2's dashboard is
the reference implementation; Persons 3 & 4 import the same names.

Usage:
    import theme
    fig = theme.style_fig(fig)                      # dark Plotly styling
    st.markdown(theme.badge("HIGH", "high"), unsafe_allow_html=True)
    st.markdown(theme.badge("BULL", "bull"), unsafe_allow_html=True)
    theme.fmt_money(1234.5, "$")  -> "$1,234.50"
"""

from __future__ import annotations

import numpy as np

# --- Surfaces & ink (dataviz dark chrome) ---------------------------------
SURFACE = "#1a1a19"      # chart surface
PAGE = "#0d0d0d"         # page plane
INK = "#ffffff"          # primary text
INK_2 = "#c3c2b7"        # secondary text
MUTED = "#898781"        # axis / labels
GRID = "#2c2c2a"         # hairline gridline
AXIS = "#383835"         # baseline / axis

# --- Status palette (fixed — never used as a series colour) ----------------
GOOD = "#0ca30c"         # up / gain / bull / high
WARN = "#fab219"         # caution / medium
SERIOUS = "#ec835a"      # elevated concern
BAD = "#d03b3b"          # down / loss / bear / low-confidence

# --- Categorical (fixed order, never cycled) -------------------------------
CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767"]

# --- Diverging blue <- gray -> red (correlation, waterfall polarity) --------
DIVERGING = [[0.0, "#3987e5"], [0.5, AXIS], [1.0, "#e66767"]]

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "ILS": "₪", "JPY": "¥"}

# Badge colour lookups. `kind` maps to a status colour; text stays ink.
LEVEL_COLOR = {"high": GOOD, "medium": WARN, "low": MUTED,
               "strong": GOOD, "weak": MUTED}
SIDE_COLOR = {"bull": GOOD, "buy": GOOD, "bear": BAD, "sell": BAD,
              "inconclusive": MUTED, "neutral": MUTED}


def style_fig(fig, height: int = 340):
    """Apply the shared dark Plotly styling to any figure. Works on donut,
    heatmap, line, waterfall, bar — anything the tabs draw."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=INK_2, size=13),
        margin=dict(l=10, r=10, t=48, b=10),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        title=dict(font=dict(color=INK, size=15)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS)
    return fig


def badge(text: str, kind: str = "medium") -> str:
    """Return an HTML pill for a strength/likelihood/side label. Use with
    st.markdown(..., unsafe_allow_html=True). `kind` is high/medium/low or
    bull/bear/inconclusive; unknown kinds fall back to muted."""
    color = LEVEL_COLOR.get(kind.lower(), SIDE_COLOR.get(kind.lower(), MUTED))
    return (f"<span style='background:{color};color:#0d0d0d;padding:2px 9px;"
            f"border-radius:999px;font-size:11px;font-weight:700;"
            f"letter-spacing:.02em'>{text}</span>")


def fmt_money(x, sym: str = "$") -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    return f"{sym}{x:,.2f}"


def fmt_pct(x) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "N/A"
    return f"{x:+.2f}%"


def signed_color(v) -> str:
    """CSS color string for a signed number: green up, red down, muted zero/NaN."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return f"color: {MUTED}"
    if v > 0:
        return f"color: {GOOD}"
    if v < 0:
        return f"color: {BAD}"
    return f"color: {INK_2}"
