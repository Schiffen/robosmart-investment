"""reporting/charts.py — the report's figures, drawn WITHOUT a browser.

WHY THIS EXISTS AT ALL
----------------------
The app draws with Plotly, which is right for the screen: it is interactive and
it is what Streamlit renders natively. But turning a Plotly figure into a raster
requires **kaleido**, and kaleido 1.x drives a real headless Chrome. Streamlit
Community Cloud has no Chrome. That left the deployed export with tables and no
figures, which is not an export — the charts are most of why anyone wants the
document.

matplotlib needs no browser. It ships manylinux wheels, renders through Agg
entirely in-process, and works identically on a Mac laptop and in a Cloud
container. So the report gets its own renderer and the charts are no longer
conditional on the environment.

THE DUPLICATION THIS DOES AND DOES NOT INTRODUCE
------------------------------------------------
It is a second RENDERER, never a second source of numbers. Every function here
takes the very same DataFrame that the matching Plotly builder in tabs/ takes —
produced by portfolio_metrics or factor_model, which are pure and tested. No
figure in this file computes anything: no sums, no weights, no returns. If a
number is wrong here it is wrong on screen too, which is the property worth
having. The one thing that is genuinely restated is the DRAWING, and that is
the whole point.

Colour comes from theme, so the report and the screen cannot drift apart on
palette. Only the chrome flips for paper: the app's INK_2 (#c3c2b7) type is
authored for a #0d0d0d page and measures about 1.9:1 on white.
"""

from __future__ import annotations

import io

import numpy as np

import theme

# Agg BEFORE pyplot. matplotlib otherwise probes for a GUI backend, which on a
# headless container is at best a wasted import and at worst a hang.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#10151A"
MUTED = "#5B6068"
RULE = "#C9CCD1"
PAPER = "#FFFFFF"

DPI = 200


def _fig(w=9.0, h=4.2):
    f, ax = plt.subplots(figsize=(w, h), dpi=DPI)
    f.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("bottom", "left"):
        ax.spines[s].set_color(RULE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=RULE, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    return f, ax


def _png(f) -> bytes:
    buf = io.BytesIO()
    f.savefig(buf, format="png", facecolor=PAPER, bbox_inches="tight",
              pad_inches=0.28)
    plt.close(f)
    return buf.getvalue()


# --------------------------------------------------------------------------
# The figures. Each mirrors one Plotly builder in tabs/.
# --------------------------------------------------------------------------

def sector_donut(sector_df, sym: str = "$") -> bytes:
    """Mirrors tabs.dashboard._donut."""
    labels = list(sector_df["sector"])
    values = np.asarray(sector_df["market_value"], dtype=float)
    total = float(np.nansum(values))
    colors = [theme.CATEGORICAL[i % len(theme.CATEGORICAL)]
              for i in range(len(labels))]

    f, ax = plt.subplots(figsize=(6.4, 4.6), dpi=DPI)
    f.patch.set_facecolor(PAPER)
    wedges, *_ = ax.pie(values, colors=colors, startangle=90,
                        counterclock=False,
                        wedgeprops=dict(width=0.38, edgecolor=PAPER,
                                        linewidth=2))
    ax.text(0, 0.06, f"{sym}{total:,.0f}", ha="center", va="center",
            fontsize=15, fontweight="bold", color=INK)
    ax.text(0, -0.14, "invested", ha="center", va="center", fontsize=9,
            color=MUTED)
    # A legend, not wedge labels: on paper a reader cannot hover, and rotated
    # labels around a small pie are the classic unreadable outcome.
    ax.legend([f"{l} — {v / total * 100:.1f}%" for l, v in zip(labels, values)],
              loc="center left", bbox_to_anchor=(0.98, 0.5), frameon=False,
              fontsize=9, labelcolor=INK)
    ax.set_aspect("equal")
    return _png(f)


def contribution_bars(contrib, sym: str = "$") -> bytes:
    """Mirrors tabs.dashboard._contribution_bar."""
    d = contrib.iloc[::-1]
    values = np.asarray(d["contribution_pct"], dtype=float)
    tickers = list(d["ticker"])
    colors = [theme.GOOD if v > 0 else theme.BAD if v < 0 else MUTED
              for v in values]

    f, ax = _fig(9.0, max(2.6, 0.42 * len(tickers) + 1.2))
    ax.barh(tickers, values, color=colors, height=0.62)
    ax.axvline(0, color=MUTED, linewidth=1.1)
    ax.grid(axis="y", visible=False)
    span = float(np.nanmax(np.abs(values))) if values.size else 1.0
    ax.set_xlim(values.min() - span * 0.45, values.max() + span * 0.45)
    for y, v in enumerate(values):
        ax.text(v + (span * 0.05 if v >= 0 else -span * 0.05), y,
                f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, color=INK)
    ax.set_xlabel("Contribution to your portfolio's move (%)", color=MUTED,
                  fontsize=9)
    return _png(f)


def performance_line(perf, preset: str = theme.RANGE_HOME) -> bytes:
    """Mirrors tabs.dashboard._perf_line, windowed by the same range_bounds."""
    bounds = theme.range_bounds(perf.index, preset)
    frame = perf
    if bounds is not None:
        lo, hi = bounds
        frame = perf.loc[(perf.index >= lo) & (perf.index <= hi)]

    f, ax = _fig(9.0, 4.0)
    ax.plot(frame.index, frame["Portfolio"], color=theme.CATEGORICAL[0],
            linewidth=2.0, label="Your portfolio")
    ax.plot(frame.index, frame["SPY"], color=MUTED, linewidth=1.6,
            linestyle="--", label="S&P 500 (SPY)")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.set_ylabel("Index (start = 100)", color=MUTED, fontsize=9)
    f.autofmt_xdate(rotation=0, ha="center")
    return _png(f)


def comparison_line(frame, ticker: str, etf: str | None) -> bytes:
    """Mirrors tabs.attribution._comparison, including the two-line collapse
    for a ticker with no distinct sector."""
    f, ax = _fig(9.0, 4.0)
    ax.plot(frame.index, frame["stock"], color=theme.CATEGORICAL[0],
            linewidth=2.0, label=ticker)
    if etf and "sector" in frame:
        ax.plot(frame.index, frame["sector"], color=theme.CATEGORICAL[2],
                linewidth=1.7, label=f"{etf} (its sector)")
    ax.plot(frame.index, frame["market"], color=MUTED, linewidth=1.6,
            linestyle="--", label="SPY (the market)")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.set_ylabel("Index (start = 100)", color=MUTED, fontsize=9)
    f.autofmt_xdate(rotation=0, ha="center")
    return _png(f)


def correlation_heatmap(corr) -> bytes:
    """Mirrors tabs.dashboard._heatmap, diagonal masked the same way."""
    z = np.asarray(corr, dtype=float).copy()
    np.fill_diagonal(z, np.nan)
    names = list(corr.columns)

    f, ax = plt.subplots(figsize=(6.6, 5.6), dpi=DPI)
    f.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "rs", [theme.CATEGORICAL[0], "#E9EAEC", "#e66767"])
    cmap.set_bad(PAPER)
    im = ax.imshow(z, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(names)), names, fontsize=9, color=INK)
    ax.set_yticks(range(len(names)), names, fontsize=9, color=INK)
    ax.tick_params(colors=MUTED, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(len(names)):
        for j in range(len(names)):
            if i != j and np.isfinite(z[i, j]):
                ax.text(j, i, f"{z[i, j]:.2f}", ha="center", va="center",
                        fontsize=8, color=INK)
    cb = f.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
    cb.set_label("ρ", color=MUTED)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    cb.outline.set_visible(False)
    return _png(f)


def attribution_waterfall(market, sector, idio, total, ticker: str) -> bytes:
    """Mirrors tabs.attribution._waterfall.

    Connectors are drawn deliberately: they carry "these parts sum to the
    whole", which is the chart's entire argument. theme.py records that
    dropping them to a hairline makes it read as four unrelated floating bars.
    """
    labels = ["Market", "Sector", "Company-specific", "Total move"]
    parts = [market, sector, idio]
    f, ax = _fig(8.0, 4.0)

    bottoms, run = [], 0.0
    for v in parts:
        bottoms.append(run)
        run += float(v)
    for i, v in enumerate(parts):
        ax.bar(i, float(v), bottom=bottoms[i], width=0.56,
               color=theme.GOOD if v >= 0 else theme.BAD)
    ax.bar(3, float(total), width=0.56, color=theme.CATEGORICAL[0])

    for i in range(3):
        y = bottoms[i] + float(parts[i])
        ax.plot([i + 0.28, (i + 1) - 0.28], [y, y], color=MUTED,
                linewidth=1.0, linestyle="-")
    for i, v in enumerate(list(parts) + [total]):
        ax.text(i, (bottoms[i] + float(v)) if i < 3 else float(total),
                f"{float(v):+.2f}%", ha="center",
                va="bottom" if float(v) >= 0 else "top", fontsize=9.5,
                color=INK, fontweight="bold")
    ax.axhline(0, color=MUTED, linewidth=1.1)
    ax.set_xticks(range(4), labels, fontsize=9, color=INK)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Contribution to the move (%)", color=MUTED, fontsize=9)
    return _png(f)
