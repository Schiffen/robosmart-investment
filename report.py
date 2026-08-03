"""report.py — the branded PDF export.

WHAT THIS IS BUILT ON, AND WHY EACH PIECE
-----------------------------------------
    reportlab   the document itself.        REQUIRED.
    svglib      the marks, as VECTORS.      REQUIRED. Pure Python.
    kaleido     Plotly charts, as PNG.      OPTIONAL — see below.

**The PDF is generated even when kaleido is missing.** That is the single most
important design decision in this file, and it is a direct response to how the
dependency behaves in the wild:

  - kaleido 0.2.1 ships NO macOS arm64 binary. On an Apple-silicon Mac it
    installs happily and then fails at render with "./bin/kaleido: No such file
    or directory".
  - kaleido 1.x fixes that, but is incompatible with Plotly 5.24's
    `fig.to_image()` — it warns and refuses. Its DIRECT api (`calc_fig_sync`)
    does work with Plotly 5.x, which is the route taken here.
  - kaleido 1.x drives REAL CHROME. Streamlit Community Cloud does not have
    Chrome, and downloading one per container on first request is not something
    to put in the path of a live demo.

So the charts are an ENHANCEMENT, not the product. Tables, figures, branding
and every number render from pure Python; if the chart engine is unavailable
the report says so in one line and is otherwise complete. An all-or-nothing
design would have meant "works on my machine, 500s on the deployed app", which
is the worst of both.

WHY THE SEAL ON THE COVER AND NOT THE MIRROR
--------------------------------------------
LOGOS.md assigns report covers to `mirror-on-light.svg`. It also says the
mirror's reflection "is the first thing a bad reproduction loses ... if the
output is one-bit or a fax, use the seal instead."

svglib is exactly that kind of lossy reproduction: it renders paths but drops
`<mask>`, so the mirror's reflection comes out as SOLID INK instead of fading
to nothing — the wordmark upside-down underneath itself, which reads as a
printing fault rather than as a reflection. Verified by rendering it.

So the cover takes the seal, on the identity's own instruction. This is not a
downgrade; it is the rule the identity wrote for precisely this case.
"""

from __future__ import annotations

import datetime as _dt
import io

import numpy as np

import brand

PAGE_INK = "#10151A"        # the -on-light ink; 16.12:1 on paper
PAGE_MUTED = "#5B6068"      # secondary on white — 6.4:1, comfortably AA
RULE = "#C9CCD1"
PAPER = "#FFFFFF"


class ReportUnavailable(RuntimeError):
    """reportlab or svglib is missing — no PDF can be produced at all."""


def availability() -> dict:
    """What this module can actually do right now, without raising.

    Called by the UI before offering the button, so a missing dependency
    becomes an explanation rather than a traceback.
    """
    state = {"pdf": False, "charts": False, "why": ""}
    try:
        import reportlab  # noqa: F401
        from svglib.svglib import svg2rlg  # noqa: F401
        state["pdf"] = True
    except Exception as e:  # noqa: BLE001
        state["why"] = f"PDF engine unavailable ({type(e).__name__}: {e})."
        return state
    try:
        _import_kaleido()
        state["charts"] = True
    except Exception:  # noqa: BLE001
        state["why"] = ("Charts are excluded: the static-image engine "
                        "(kaleido) is not available here.")
    return state


def _import_kaleido():
    """Import kaleido with its version banner silenced.

    kaleido 1.x emits a multi-line UserWarning on import whenever Plotly is
    below 6.1, telling you `fig.to_image()` will not work. That is true and
    irrelevant: this module never calls `to_image`, it calls kaleido's own
    `calc_fig_sync`, which the same warning explicitly says does work with a
    5.x figure. Left unsuppressed the banner prints on every availability check
    — into the Streamlit server log, and into pytest's warning summary.
    """
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import kaleido
    return kaleido


# --------------------------------------------------------------------------
# Charts -> PNG
# --------------------------------------------------------------------------

def _for_print(fig):
    """Re-style a dark app figure for white paper.

    theme.style_fig paints for a #0d0d0d page: transparent backgrounds and
    INK_2 (#c3c2b7) type. Dropped onto white, that type measures about 1.9:1 —
    effectively invisible. The figure's colours live in the figure JSON, not in
    CSS, so there is no stylesheet that can fix this; it has to be restyled
    before export.

    Series colours are deliberately left alone: theme.CATEGORICAL, GOOD and BAD
    were chosen for luminance AND chroma parity and they hold up on white. Only
    the chrome — type, axes, gridlines, paper — is flipped.
    """
    import copy
    f = copy.deepcopy(fig)
    f.update_layout(
        paper_bgcolor=PAPER, plot_bgcolor=PAPER,
        font=dict(color=PAGE_INK, size=12),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=PAGE_INK)),
    )
    f.update_xaxes(gridcolor=RULE, zerolinecolor="#9AA0A6", linecolor="#9AA0A6",
                   tickfont=dict(color=PAGE_MUTED),
                   title=dict(font=dict(color=PAGE_MUTED)))
    f.update_yaxes(gridcolor=RULE, zerolinecolor="#9AA0A6", linecolor="#9AA0A6",
                   tickfont=dict(color=PAGE_MUTED),
                   title=dict(font=dict(color=PAGE_MUTED)))
    # Annotations (the donut's centre total) carry their own colour.
    for ann in (f.layout.annotations or []):
        ann.font.color = PAGE_INK
    return f


def _png(fig, width: int = 1000, height: int = 460) -> bytes | None:
    """Render a figure to PNG, or None if the engine cannot.

    Uses kaleido's DIRECT api rather than `fig.to_image()`: kaleido 1.x refuses
    to serve Plotly 5.24 through Plotly's own path, but its own entry point
    works fine with a 5.x figure.
    """
    try:
        kaleido = _import_kaleido()
        out = kaleido.calc_fig_sync(
            _for_print(fig),
            opts={"format": "png", "width": width, "height": height, "scale": 2},
        )
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)
        if isinstance(out, list) and out:
            return bytes(out[0])
    except Exception:  # noqa: BLE001 — a chart is never worth failing the report
        return None
    return None


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------

def _mark(name: str, width_pt: float):
    """A logo as a reportlab Drawing, scaled to `width_pt`, or None."""
    try:
        from svglib.svglib import svg2rlg
        d = svg2rlg(str(brand.LOGO_DIR / f"{name}.svg"))
        if d is None or not d.width:
            return None
        s = width_pt / d.width
        d.scale(s, s)
        d.width *= s
        d.height *= s
        return d
    except Exception:  # noqa: BLE001
        return None


def pdf_safe(text) -> str:
    """Escape model-authored text for reportlab.

    THIS IS `theme.safe` FOR A NEW OUTPUT MEDIUM, and it exists for the same
    reason invariant #10 does. reportlab's Paragraph does not draw a plain
    string — it parses a small HTML dialect (`<b>`, `<i>`, `<br/>`, `<font>`).
    So a judge verdict containing "P/E < 20 & falling" raises a parse error and
    takes out the whole export, and one containing "<font color=white>" would
    be OBEYED. Every string in this file that came from a model goes through
    here.

    The app's own theme.safe is not reusable: it emits `&#36;` for `$`, which
    is right for Streamlit's LaTeX parser and wrong here — reportlab has no
    LaTeX parser and would print the entity literally.
    """
    import xml.sax.saxutils as _x
    return _x.escape("" if text is None else str(text))


def _money(v, sym="$") -> str:
    return "N/A" if v is None or not np.isfinite(v) else f"{sym}{v:,.2f}"


def _pct(v) -> str:
    return "N/A" if v is None or not np.isfinite(v) else f"{v:+.2f}%"


def build(*, portfolio: dict, positions, sector_df=None, figures=None,
          profile_label: str | None = None, as_of: str | None = None,
          data_source: str = "market data", currency: str = "$",
          debate: dict | None = None, attribution: dict | None = None) -> bytes:
    """Produce the report as PDF bytes.

    `figures` is an ordered list of (caption, plotly figure). Any that cannot
    be rendered are skipped individually rather than failing the document.

    `debate` and `attribution` carry the ANALYSIS, and they are the reason this
    export is worth having. A holdings table is something a spreadsheet can
    produce; two AI analysts arguing over a stock with a judge naming the
    weakest claim on each side is not, and it is the part someone would
    actually send to another person. Both are optional — the report covers
    whatever the app currently knows and says nothing about what it does not.
    """
    try:
        from reportlab.graphics import renderPDF
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.platypus import Table, TableStyle
    except Exception as e:  # noqa: BLE001
        raise ReportUnavailable(str(e)) from e

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    c.setTitle(f"{brand.PRODUCT} — portfolio report")
    c.setAuthor(brand.PRODUCT)
    c.setSubject("Educational university project. Not investment advice.")

    stamp = _mark("seal-on-light", 34)

    def footer(page_no: int) -> None:
        """Every page carries the mark, the date and the disclaimer.

        A page of this that gets separated from the rest must still say what it
        is and that it is not advice.
        """
        c.setFillColor(colors.HexColor(RULE))
        c.rect(20 * mm, 18 * mm, W - 40 * mm, 0.6, stroke=0, fill=1)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor(PAGE_MUTED))
        c.drawString(20 * mm, 12.5 * mm,
                     f"{brand.PRODUCT} — educational university project. "
                     f"Not investment advice.")
        c.drawRightString(W - 20 * mm, 12.5 * mm, f"{page_no}")
        if stamp:
            renderPDF.draw(stamp, c, W - 20 * mm - stamp.width, 22 * mm)

    # ---- Cover -----------------------------------------------------------
    cover = _mark("seal-on-light", 132)
    if cover:
        renderPDF.draw(cover, c, (W - cover.width) / 2, H - 92 * mm)
    c.setFillColor(colors.HexColor(PAGE_INK))
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(W / 2, H - 108 * mm, brand.PRODUCT)
    c.setFont("Helvetica", 13)
    c.setFillColor(colors.HexColor(PAGE_MUTED))
    c.drawCentredString(W / 2, H - 118 * mm, "Portfolio report")

    y = H - 140 * mm
    c.setFillColor(colors.HexColor(RULE))
    c.rect(55 * mm, y + 8 * mm, W - 110 * mm, 0.8, stroke=0, fill=1)
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor(PAGE_INK))
    for line in [l for l in (
            f"Book: {profile_label}" if profile_label else None,
            f"Prices: {data_source}" + (f", close of {as_of}" if as_of else ""),
            "All figures close-to-close.",
            f"Generated {_dt.date.today():%d %b %Y}.") if l]:
        c.drawCentredString(W / 2, y, line)
        y -= 6.5 * mm

    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.HexColor(PAGE_MUTED))
    c.drawCentredString(W / 2, 36 * mm,
                        "This document is produced by an educational university "
                        "project and is not investment advice.")
    footer(1)
    c.showPage()

    # ---- Holdings --------------------------------------------------------
    page = 2
    c.setFillColor(colors.HexColor(PAGE_INK))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(20 * mm, H - 28 * mm, "Holdings")

    head = ["Ticker", "Shares", "Cost", "Price", "Value", "P&L", "P&L %", "Wt %"]
    rows = [head]
    for r in positions.itertuples():
        rows.append([
            str(r.ticker), f"{r.shares:,.0f}", _money(r.cost_basis, currency),
            _money(r.current_price, currency), _money(r.market_value, currency),
            _money(r.pnl_abs, currency), _pct(r.pnl_pct),
            "N/A" if not np.isfinite(r.weight_pct) else f"{r.weight_pct:.1f}%",
        ])
    tbl = Table(rows, hAlign="LEFT", colWidths=[22 * mm] + [21 * mm] * 7)
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(PAGE_INK)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(PAGE_INK)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F5F6F7")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    tw, th = tbl.wrapOn(c, W - 40 * mm, H)
    tbl.drawOn(c, 20 * mm, H - 40 * mm - th)

    cash = float(portfolio.get("cash", 0) or 0)
    invested = float(np.nansum(positions["market_value"].to_numpy(dtype=float)))
    c.setFont("Helvetica", 9.5)
    c.setFillColor(colors.HexColor(PAGE_MUTED))
    # NOTE: one string, two currency symbols. In the APP this would need
    # theme.fmt_money_md — Streamlit's markdown parser eats the span between
    # two dollar signs. reportlab has no such parser, so it is safe here, and
    # this comment exists so nobody "fixes" it back into the app's idiom.
    c.drawString(20 * mm, H - 48 * mm - th,
                 f"{_money(invested + cash, currency)} total = "
                 f"{_money(invested, currency)} invested + "
                 f"{_money(cash, currency)} cash.")
    footer(page)
    c.showPage()

    # ---- Analysis: the debate, and the day's decomposition ---------------
    # Flowed through a Frame rather than drawString: model output has no length
    # contract, and drawString neither wraps nor paginates — a long verdict
    # would simply run off the right edge and off the bottom of the page.
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Frame, Paragraph, Spacer

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5,
                          leading=13.5, textColor=colors.HexColor(PAGE_INK))
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=12,
                           textColor=colors.HexColor(PAGE_MUTED))
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13,
                        leading=17, spaceAfter=4,
                        textColor=colors.HexColor(PAGE_INK))
    h3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5,
                        leading=14, spaceBefore=8, spaceAfter=2,
                        textColor=colors.HexColor(PAGE_INK))

    def flow(items):
        """Lay `items` out, opening as many pages as they need."""
        nonlocal page
        remaining = list(items)
        while remaining:
            page += 1
            f = Frame(20 * mm, 26 * mm, W - 40 * mm, H - 52 * mm,
                      leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0, showBoundary=0)
            before = len(remaining)
            f.addFromList(remaining, c)     # mutates: consumes what fitted
            footer(page)
            c.showPage()
            if len(remaining) == before:    # nothing fitted — refuse to loop
                break

    if attribution:
        tkr = pdf_safe(attribution.get("ticker") or "")
        d = attribution.get("decomposition") or {}
        items = [Paragraph(f"What happened to {tkr} that day", h2)]

        def _fmt(v):
            return "N/A" if v is None or not np.isfinite(v) else f"{v:+.2f}%"
        rows = [["Total move", _fmt(d.get("total_move_pct"))],
                ["…the whole market", _fmt(d.get("market_component_pct"))],
                ["…its sector", _fmt(d.get("sector_component_pct"))],
                ["…specific to the company", _fmt(d.get("idiosyncratic_pct"))]]
        t = Table(rows, colWidths=[70 * mm, 30 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(PAGE_INK)),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(RULE)),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        items += [t, Spacer(1, 8)]
        if d.get("interpretation"):
            items.append(Paragraph(pdf_safe(d["interpretation"]), body))
        mq = d.get("model_quality") or {}
        if mq.get("r_squared") is not None and np.isfinite(mq.get("r_squared", np.nan)):
            items.append(Paragraph(
                f"Ordinary least squares on {mq.get('n_obs', 0)} days of daily "
                f"returns; model fit R² = {float(mq['r_squared']):.0%}. The "
                f"sector is residualised against the market so the two do not "
                f"double-count.", small))
        expl = attribution.get("explanation") or {}
        if expl.get("no_cause_found"):
            items += [Paragraph("Company-specific move", h3),
                      Paragraph(pdf_safe(expl.get("caveat")
                                         or "No clear cause found."), body)]
        for e in (expl.get("explanations") or []):
            items += [Paragraph(pdf_safe(e.get("cause") or ""), h3)]
            if e.get("evidence_headline"):
                items.append(Paragraph(pdf_safe(e["evidence_headline"]), small))
        flow(items)

    if debate:
        tkr = pdf_safe(debate.get("ticker") or "")
        items = [Paragraph(f"Bull vs Bear — {tkr}", h2),
                 Paragraph("Two analysts argue the same stock from opposite "
                           "sides; a third judges them. Generated by a language "
                           "model. The disagreement is the point.", small),
                 Spacer(1, 6)]
        for side, label in (("bull", "The bull case"), ("bear", "The bear case")):
            block = debate.get(side) or {}
            opening = block.get("opening") or {}
            items.append(Paragraph(label, h3))
            if opening.get("thesis"):
                items.append(Paragraph(pdf_safe(opening["thesis"]), body))
            for claim in (opening.get("claims") or []):
                items.append(Paragraph(
                    f"• {pdf_safe(claim.get('claim'))} "
                    f"<font size=8 color='{PAGE_MUTED}'>"
                    f"({pdf_safe(claim.get('strength'))})</font>", body))
                if claim.get("evidence"):
                    items.append(Paragraph(
                        f"&nbsp;&nbsp;&nbsp;{pdf_safe(claim['evidence'])}", small))
        judge = debate.get("judge") or {}
        if judge:
            items += [Spacer(1, 6), Paragraph("The judge's verdict", h3)]
            conf = judge.get("confidence")
            if judge.get("verdict"):
                items.append(Paragraph(
                    f"<b>{pdf_safe(judge['verdict'])}</b>"
                    + (f" — confidence {int(conf)}%" if isinstance(conf, (int, float))
                       else ""), body))
            for key, lab in (("reasoning", None),
                             ("weakest_bull_claim", "Weakest bull claim"),
                             ("weakest_bear_claim", "Weakest bear claim"),
                             ("key_uncertainty", "Key uncertainty")):
                if judge.get(key):
                    prefix = f"<b>{lab}.</b> " if lab else ""
                    items.append(Paragraph(prefix + pdf_safe(judge[key]), body))
            fals = [f for f in (judge.get("falsifiers") or []) if f]
            if fals:
                items.append(Paragraph("What would change the verdict", h3))
                for f_ in fals:
                    items.append(Paragraph(f"• {pdf_safe(f_)}", body))
        flow(items)

    # ---- Charts ----------------------------------------------------------
    from reportlab.lib.utils import ImageReader
    wanted = list(figures or [])
    drawn = 0
    for caption, fig in wanted:
        png = _png(fig)
        if png is None:
            continue          # this chart only; never the document
        page += 1
        drawn += 1
        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        scale = min((W - 40 * mm) / iw, (H - 90 * mm) / ih)
        c.setFillColor(colors.HexColor(PAGE_INK))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, H - 28 * mm, caption)
        c.drawImage(img, 20 * mm, H - 40 * mm - ih * scale,
                    width=iw * scale, height=ih * scale, mask="auto")
        footer(page)
        c.showPage()

    # Say so, in the document, when charts were requested and none arrived.
    # A report that silently drops half its content is worse than one that is
    # honest about what it could not produce — the reader has no other way to
    # know the difference between "no charts here" and "charts failed".
    if wanted and drawn == 0:
        page += 1
        c.setFillColor(colors.HexColor(PAGE_INK))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, H - 28 * mm, "Charts")
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor(PAGE_MUTED))
        c.drawString(20 * mm, H - 38 * mm,
                     "Charts could not be rendered in this environment: the "
                     "static-image engine is unavailable.")
        c.drawString(20 * mm, H - 44 * mm,
                     "Every figure above is unaffected — the tables are "
                     "computed independently of the chart engine.")
        footer(page)
        c.showPage()

    c.save()
    return buf.getvalue()
