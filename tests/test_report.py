"""The PDF export — and specifically, that it degrades instead of breaking.

The chart engine here is genuinely fragile, in ways that are invisible until
they are not:

  - kaleido 0.2.1 ships NO macOS arm64 binary. It installs cleanly and then
    fails at render with "./bin/kaleido: No such file or directory".
  - kaleido 1.x is incompatible with Plotly 5.24's `fig.to_image()`; only its
    own direct API works with a 5.x figure.
  - kaleido 1.x drives REAL CHROME, which Streamlit Community Cloud has not
    got.

None of that applies any more: `reporting.charts` draws with matplotlib, which
needs no browser. What this file pins is that the whole document — cover,
tables, analysis AND figures — is produced from pure Python on any platform,
and that a figure which fails costs that figure and nothing else.
"""

import json
import os

import pytest

import brand
import portfolio_metrics as pm
import profiles
import reporting.document as report

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pypdf = pytest.importorskip("pypdf")


@pytest.fixture(scope="module")
def book():
    import data_layer
    p = profiles.load_portfolio("balanced_growth")
    ctx = data_layer.get_context_batch([x["ticker"] for x in p["positions"]])
    df = pm.position_values(p, ctx)
    return p, df, pm.sector_breakdown(df, p)


def _pdf(**kw):
    p, df, sect = kw.pop("book")
    return report.build(portfolio=p, positions=df, sector_df=sect, **kw)


# --------------------------------------------------------------------------
# It builds with no chart engine at all
# --------------------------------------------------------------------------

def test_report_builds_with_no_figures(book):
    data = _pdf(book=book, profile_label="Balanced growth", as_of="31 Jul 2026")
    assert data[:5] == b"%PDF-", "not a PDF"
    assert len(data) > 2000


def test_report_says_so_when_no_charts_arrive(book):
    """A report that silently drops its figures is worse than one that admits
    it — the reader has no other way to tell "no charts here" from "charts
    failed". Passing figures that are all None is the shape of that failure."""
    import io
    p, df, sect = book
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        figures=[("Where your money is", None)],
                        profile_label="Balanced growth")
    assert data[:5] == b"%PDF-"
    text = " ".join(pg.extract_text() for pg in
                    pypdf.PdfReader(io.BytesIO(data)).pages)
    assert "Holdings" in text, "the tables must survive a dead chart renderer"
    assert "could not be rendered" in text


def test_a_single_broken_figure_does_not_lose_the_others(book):
    """One figure failing must cost that figure and nothing else."""
    import io
    from reporting import charts as rc
    p, df, sect = book
    good = rc.sector_donut(sect, "$")
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        figures=[("broken", None), ("Where your money is", good)])
    r = pypdf.PdfReader(io.BytesIO(data))
    text = " ".join(pg.extract_text() for pg in r.pages)
    assert "Where your money is" in text
    assert "broken" not in text


# --------------------------------------------------------------------------
# What the document must say
# --------------------------------------------------------------------------

def _text(data):
    import io
    return " ".join(pg.extract_text() for pg in
                    pypdf.PdfReader(io.BytesIO(data)).pages)


def test_every_page_carries_the_disclaimer(book):
    """A page separated from the rest must still say what it is."""
    import io
    data = _pdf(book=book, profile_label="Balanced growth")
    for i, page in enumerate(pypdf.PdfReader(io.BytesIO(data)).pages, 1):
        assert "not investment advice" in page.extract_text().lower(), \
            f"page {i} carries no disclaimer"


def test_cover_names_the_product_and_the_price_date(book):
    data = _pdf(book=book, profile_label="Balanced growth",
                as_of="31 Jul 2026", data_source="recorded snapshot")
    text = _text(data)
    assert brand.PRODUCT in text
    assert "31 Jul 2026" in text
    assert "recorded snapshot" in text, \
        "recorded data must never be able to look live — even on paper"
    assert "close-to-close" in text


def test_holdings_table_carries_every_position(book):
    p, df, _ = book
    text = _text(_pdf(book=book))
    for t in df["ticker"]:
        assert str(t) in text, f"{t} missing from the holdings table"


def test_pdf_metadata_is_set(book):
    import io
    r = pypdf.PdfReader(io.BytesIO(_pdf(book=book)))
    assert brand.PRODUCT in (r.metadata.title or "")
    assert "not investment advice" in (r.metadata.subject or "").lower()


# --------------------------------------------------------------------------
# Print styling — charts are authored for #0d0d0d, the page is white
# --------------------------------------------------------------------------

def test_every_chart_renders_without_a_browser(book):
    """The point of the whole renderer swap.

    Plotly needed kaleido, which drives a real Chrome that Community Cloud has
    not got — so the deployed export had tables and no figures. matplotlib
    renders in-process on any platform. If this ever needs a browser again, the
    export is broken everywhere it matters and nowhere it is tested.
    """
    from reporting import charts as rc
    import portfolio_metrics as pm
    p, df, sect = book
    pngs = [
        rc.sector_donut(sect, "$"),
        rc.contribution_bars(pm.day_move_contributions(df, p.get("cash", 0.0)), "$"),
        rc.attribution_waterfall(1.36, -1.19, 2.76, 2.93, "NVDA"),
    ]
    for i, png in enumerate(pngs):
        assert png and png[:8] == b"\x89PNG\r\n\x1a\n", f"figure {i} is not a PNG"
        assert len(png) > 3000, f"figure {i} looks empty"


def test_report_charts_use_matplotlibs_headless_backend():
    """Agg must be selected BEFORE pyplot is imported: matplotlib otherwise
    probes for a GUI backend, which on a headless container is at best a wasted
    import and at worst a hang."""
    import matplotlib
    from reporting import charts  # noqa: F401
    assert matplotlib.get_backend().lower() == "agg"


def test_report_charts_draw_from_the_shared_palette():
    """A second renderer must not become a second palette. Colour comes from
    theme, so the PDF and the screen cannot drift."""
    import inspect
    from reporting import charts as rc
    src = inspect.getsource(rc)
    assert "theme.CATEGORICAL" in src and "theme.GOOD" in src and "theme.BAD" in src


def test_report_charts_compute_nothing(book):
    """The report is a second RENDERER, never a second source of numbers.

    Every figure takes a DataFrame already produced by portfolio_metrics or
    factor_model. If a chart here started deriving its own values, the PDF
    could disagree with the screen and there would be no test that noticed.
    """
    import ast
    import inspect
    from reporting import charts as rc

    # Parse the IMPORTS rather than grepping the source: the module docstring
    # legitimately names portfolio_metrics while explaining this very rule, and
    # a substring check fails on its own documentation.
    tree = ast.parse(inspect.getsource(rc))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("portfolio_metrics", "factor_model", "data_layer",
                   "yfinance", "streamlit"):
        assert banned not in imported, \
            f"report_charts imports {banned}; it must only DRAW what it is given"


# --------------------------------------------------------------------------
# Availability reporting
# --------------------------------------------------------------------------

def test_availability_never_raises_and_always_explains():
    state = report.availability()
    assert set(state) == {"pdf", "charts", "why"}
    assert isinstance(state["pdf"], bool) and isinstance(state["charts"], bool)
    if not state["charts"]:
        assert state["why"], "an unavailable engine must come with a reason"


def test_availability_reports_charts_as_WORKING_here():
    """The positive case, which nothing else asserted — and it regressed.

    `availability()` probes the renderer inside a try/except that turns any
    ImportError into `charts: False` plus a polite message. When the modules
    moved into the `reporting` package, a stale `import report_charts` left
    behind meant every install reported "charts are excluded" and the export
    panel said so, on a machine where charts render perfectly. The whole suite
    stayed green, because every other test asserted only the DEGRADED path.

    A guard that swallows exceptions needs a test that the guard is not firing.
    """
    state = report.availability()
    assert state["pdf"] is True
    assert state["charts"] is True, (
        f"charts reported unavailable in an environment that has the "
        f"renderer: {state['why']}")
    assert state["why"] == ""


# --------------------------------------------------------------------------
# Model-authored text in a PDF — invariant #10, new medium
# --------------------------------------------------------------------------

_POISON = ("<font color='white' size=40>INVISIBLE</font> & "
           "P/E < 20 > 10 <br/><b>bold</b> \"quoted\" 'single'")


def test_pdf_safe_escapes_reportlab_markup():
    """reportlab's Paragraph parses a small HTML dialect, so an unescaped
    model string is both a crash risk and an injection vector."""
    out = report.pdf_safe(_POISON)
    assert "<font" not in out and "<b>" not in out and "<br/>" not in out
    assert "&lt;font" in out and "&amp;" in out
    assert report.pdf_safe(None) == ""


def test_pdf_safe_does_not_borrow_the_apps_dollar_escaping():
    """theme.safe emits &#36; for $, which is right for Streamlit's LaTeX
    parser and wrong here — reportlab would print the entity literally."""
    assert report.pdf_safe("$5B and $9B") == "$5B and $9B"


def test_a_hostile_debate_renders_without_breaking_or_injecting(book):
    """The PDF equivalent of tests/test_model_output_safety.py.

    A report is the artifact users send to other people, so a model that emits
    markup must not be able to reach into it — nor take the export down, which
    would be the more likely outcome: reportlab raises on malformed tags.
    """
    p, df, sect = book
    claim = {"claim": _POISON, "evidence": _POISON, "strength": _POISON}
    hostile = {
        "ticker": _POISON,
        "bull": {"opening": {"thesis": _POISON, "claims": [claim]}},
        "bear": {"opening": {"thesis": _POISON, "claims": [claim]}},
        "judge": {"verdict": _POISON, "confidence": 58, "reasoning": _POISON,
                  "weakest_bull_claim": _POISON, "weakest_bear_claim": _POISON,
                  "key_uncertainty": _POISON, "falsifiers": [_POISON]},
    }
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        debate=hostile)
    assert data[:5] == b"%PDF-"
    text = _text(data)
    # It rendered rather than being silently dropped...
    assert "INVISIBLE" in text
    # ...and the payload is inert text, not obeyed markup.
    assert "<font" in text or "&lt;font" in text


def test_hostile_attribution_text_also_survives(book):
    p, df, sect = book
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        attribution={"ticker": _POISON,
                                     "decomposition": {"interpretation": _POISON,
                                                       "total_move_pct": 1.0},
                                     "explanation": {"no_cause_found": True,
                                                     "caveat": _POISON}})
    assert data[:5] == b"%PDF-"


# --------------------------------------------------------------------------
# The analysis sections
# --------------------------------------------------------------------------

def test_debate_section_carries_the_verdict_and_both_sides(book):
    import json
    p, df, sect = book
    deb = json.load(open(os.path.join(BASE, "mock_debate.json")))
    deb["ticker"] = "NVDA"
    text = _text(report.build(portfolio=p, positions=df, sector_df=sect,
                              debate=deb))
    assert "Bull vs Bear" in text and "NVDA" in text
    assert "The bull case" in text and "The bear case" in text
    assert "judge" in text.lower()
    assert "confidence" in text.lower()
    # The weakest-claim-on-both-sides pair is the honest part of the verdict.
    assert "Weakest bull claim" in text and "Weakest bear claim" in text


def test_debate_section_says_the_text_is_model_generated(book):
    """Someone receiving this PDF was never in front of the app and has no
    other way to know which parts a model wrote."""
    import json
    p, df, sect = book
    deb = json.load(open(os.path.join(BASE, "mock_debate.json")))
    text = _text(report.build(portfolio=p, positions=df, sector_df=sect,
                              debate=deb))
    assert "language model" in text.lower()


def test_attribution_section_carries_the_three_components(book):
    p, df, sect = book
    text = _text(report.build(
        portfolio=p, positions=df, sector_df=sect,
        attribution={"ticker": "NVDA",
                     "decomposition": {"total_move_pct": 2.93,
                                       "market_component_pct": 1.36,
                                       "sector_component_pct": -1.19,
                                       "idiosyncratic_pct": 2.76,
                                       "model_quality": {}}}))
    assert "whole market" in text and "sector" in text
    assert "+2.93%" in text and "+1.36%" in text and "-1.19%" in text


def test_a_long_verdict_paginates_instead_of_running_off_the_page(book):
    """Model output has no length contract. drawString would neither wrap nor
    paginate — a long verdict would vanish off the bottom edge."""
    import io
    p, df, sect = book

    def pages(reps):
        judge = {"verdict": "inconclusive",
                 "falsifiers": [f"Falsifier number {i}. " * 12
                                for i in range(reps)]}
        data = report.build(portfolio=p, positions=df, sector_df=sect,
                            debate={"ticker": "X", "judge": judge})
        return len(pypdf.PdfReader(io.BytesIO(data)).pages), _text(data)

    short_n, _ = pages(1)
    long_n, long_text = pages(60)
    assert long_n > short_n, (
        f"content that cannot fit one page did not open another "
        f"({short_n} -> {long_n})")
    # And nothing was silently dropped on the way.
    assert "Falsifier number" in long_text


def test_marks_resolve_as_vectors_not_raster():
    """svglib renders the marks as PDF vector drawings. If this returns None
    the cover silently loses its logo."""
    for name in ("seal-on-light", "rose-on-light"):
        d = report._mark(name, 100)
        assert d is not None, f"{name} did not resolve"
        assert abs(d.width - 100) < 0.5
