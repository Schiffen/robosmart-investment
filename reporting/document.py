"""report.py — the branded PDF export.

WHAT THIS IS BUILT ON
---------------------
    reportlab      the document itself
    svglib         the marks, as embedded VECTORS
    charts.py      the figures, via matplotlib

All three are pure Python and install everywhere. **The charts are not
conditional on the environment**, which is the whole point of the export: a
report without its figures is a spreadsheet, and "generate it locally to get
the charts" is not something you can say about a feature whose purpose is that
users save it and send it to other people.

WHY NOT KALEIDO — kept, because it is the obvious thing to reach for
-------------------------------------------------------------------
Turning a *Plotly* figure into a raster needs kaleido, and every version of it
fails somewhere that matters:

  - 0.2.1 ships NO macOS arm64 binary. It installs happily on Apple silicon and
    then dies at render with "./bin/kaleido: No such file or directory".
  - 1.x fixes that but refuses Plotly 5.24 through `fig.to_image()`; only its
    own `calc_fig_sync` works with a 5.x figure.
  - 1.x drives REAL CHROME. Streamlit Community Cloud has none, and downloading
    one per container on first request is not something to put in front of a
    live demo.

So the report does not render Plotly at all. `reporting.charts` redraws the same
DataFrames with matplotlib, which needs no browser, ships manylinux wheels, and
renders all five figures in about half a second against kaleido's seven. It is
a second RENDERER, never a second source of numbers — see reporting/charts.py.

THE COVER USES THE MIRROR
-------------------------
Specifically `mirror-print-on-light.svg`, generated from `mirror.svg`. The
original cannot be used here: svglib renders paths but **drops `<mask>`**, so
the reflection comes out as solid ink — the wordmark upside-down beneath
itself, which reads as a printing fault. LOGOS.md anticipates exactly this
("the first thing a bad reproduction loses") and says to fall back to the seal.

Rather than accept that, the fade is BAKED: the reflection is sliced into 26
horizontal bands, each clipped and given the alpha the gradient had at that
height. Both clipping and fill-opacity survive svglib, so the mark reproduces
as drawn. Regenerate with the script recorded in logos/LOGOS.md if the source
mirror ever changes.
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
        from reporting import charts  # noqa: F401
        state["charts"] = True
    except Exception as e:  # noqa: BLE001
        state["why"] = (f"Charts are excluded: the figure renderer is "
                        f"unavailable ({type(e).__name__}).")
    return state


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


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap. `textwrap` would do, but this keeps the character
    budget explicit next to the font size it was measured against."""
    import textwrap
    return textwrap.wrap(str(text), width=width)


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
    # THE MIRROR IS THE TITLE. It is the ceremonial half of the identity and
    # LOGOS.md assigns report covers to it; setting the product name in
    # Helvetica underneath would be a second, worse wordmark competing with the
    # drawn one. The print variant is used because svglib drops <mask> — see
    # the module docstring.
    cover = _mark("mirror-print-on-light", 120 * mm) or _mark("seal-on-light", 132)
    # Positions are DERIVED from the mark's rendered height, never guessed. The
    # first version put the subtitle at a fixed H-108mm, which landed inside the
    # mirror's own footprint and printed "Portfolio report" straight through
    # "DEBATE CLUB". The mark is 3:1 and its height moves with any width change,
    # so any hard-coded offset below it is one edit away from colliding again.
    mark_top = H - 46 * mm
    mark_bottom = mark_top - (cover.height if cover else 0)
    if cover:
        renderPDF.draw(cover, c, (W - cover.width) / 2, mark_bottom)

    c.setFillColor(colors.HexColor(PAGE_MUTED))
    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, mark_bottom - 14 * mm, "PORTFOLIO REPORT")

    # The book this report is ABOUT, stated as the cover's subject. A report
    # that does not name whose portfolio it is cannot be filed, forwarded or
    # told apart from another one — which is the whole failure mode of an
    # export people are meant to keep and send on.
    invested = float(np.nansum(positions["market_value"].to_numpy(dtype=float)))
    cash = float(portfolio.get("cash", 0) or 0)
    subject = profile_label or "Your uploaded portfolio"

    y = mark_bottom - 34 * mm
    c.setFillColor(colors.HexColor(RULE))
    c.rect(52 * mm, y + 13 * mm, W - 104 * mm, 0.8, stroke=0, fill=1)
    c.setFillColor(colors.HexColor(PAGE_INK))
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(W / 2, y, subject)

    c.setFont("Helvetica", 11)
    c.drawCentredString(W / 2, y - 8 * mm,
                        f"{len(positions)} holdings · "
                        f"{_money(invested + cash, currency)} total")
    c.setFillColor(colors.HexColor(PAGE_MUTED))
    c.setFont("Helvetica", 9.5)
    c.drawCentredString(W / 2, y - 15 * mm,
                        f"{_money(invested, currency)} invested · "
                        f"{_money(cash, currency)} cash")

    # Provenance, one line. Which prices, from when, on what basis — the three
    # things a reader who was never in front of the app cannot otherwise know.
    c.setFont("Helvetica", 9.5)
    prov = data_source + (f" · close of {as_of}" if as_of else "")
    c.drawCentredString(W / 2, y - 27 * mm, f"{prov} · close-to-close")
    c.drawCentredString(W / 2, y - 33 * mm,
                        f"Generated {_dt.date.today():%d %B %Y}")

    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(W / 2, 36 * mm,
                        "Produced by an educational university project. "
                        "Not investment advice.")
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
    # `figures` is (caption, PNG bytes) — already rendered by reporting.charts.
    # Passing bytes rather than a figure object keeps this module ignorant of
    # which plotting library drew them, which is what made swapping kaleido out
    # for matplotlib a change in one place.
    from reportlab.lib.utils import ImageReader
    # `requested` counts what the CALLER asked for; `usable` is what survived.
    # Counting only the survivors would make the "charts could not be rendered"
    # notice below unreachable — the empty list looks identical to "no charts
    # were wanted", which is exactly the distinction the notice exists to draw.
    # TWO FIGURES PER PAGE, EACH WITH ITS OWN EXPLANATION.
    #
    # One-per-page put a chart in the top third and left two thirds white, so a
    # six-figure report ran to eight pages of mostly nothing — and related
    # figures ("where your money is" / "what moved it today") landed on separate
    # sheets where they cannot be compared. Two-up closes the gap and puts the
    # pair a reader wants to read together in one view.
    #
    # The prose matters more than the packing. On screen a chart sits under a
    # heading, beside captions, with hover — none of which survives into a PDF
    # that gets forwarded. Without a sentence saying what the figure shows and
    # how to read it, the recipient is looking at a picture of some data.
    requested = list(figures or [])
    usable = [f for f in requested if f[1]]
    drawn = 0
    slots = 0

    for item in usable:
        caption, png = item[0], item[1]
        note = item[2] if len(item) > 2 else None

        if slots == 0:                                  # open a page
            page += 1
            c.setFillColor(colors.HexColor(PAGE_INK))
            c.setFont("Helvetica-Bold", 15)
            c.drawString(20 * mm, H - 24 * mm, "The figures")

        top = (H - 38 * mm) if slots == 0 else (H - 158 * mm)
        band = 108 * mm                                 # per-slot height budget

        c.setFillColor(colors.HexColor(PAGE_INK))
        c.setFont("Helvetica-Bold", 11.5)
        c.drawString(20 * mm, top, caption)

        y = top - 5 * mm
        if note:
            c.setFillColor(colors.HexColor(PAGE_MUTED))
            c.setFont("Helvetica", 8.5)
            for line in _wrap(note, 118):
                y -= 4.2 * mm
                c.drawString(20 * mm, y, line)
            y -= 1.5 * mm

        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        avail_h = band - (top - y) - 6 * mm
        scale = min((W - 40 * mm) / iw, avail_h / ih)
        c.drawImage(img, 20 * mm, y - 4 * mm - ih * scale,
                    width=iw * scale, height=ih * scale, mask="auto")

        drawn += 1
        slots += 1
        if slots == 2:                                  # close the page
            footer(page)
            c.showPage()
            slots = 0

    if slots:                                           # a lone trailing figure
        footer(page)
        c.showPage()

    # Say so, in the document, when charts were requested and none arrived.
    # A report that silently drops half its content is worse than one that is
    # honest about what it could not produce — the reader has no other way to
    # know the difference between "no charts here" and "charts failed".
    if requested and drawn == 0:
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
