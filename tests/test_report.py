"""The PDF export — and specifically, that it degrades instead of breaking.

The chart engine here is genuinely fragile, in ways that are invisible until
they are not:

  - kaleido 0.2.1 ships NO macOS arm64 binary. It installs cleanly and then
    fails at render with "./bin/kaleido: No such file or directory".
  - kaleido 1.x is incompatible with Plotly 5.24's `fig.to_image()`; only its
    own direct API works with a 5.x figure.
  - kaleido 1.x drives REAL CHROME, which Streamlit Community Cloud has not
    got.

So the contract this file pins is: **the document is produced from pure Python,
and charts are an enhancement.** Everything below runs WITHOUT Chrome. The
tests that need it carry `@pytest.mark.pdf` and live in test_chart_interaction.
"""

import json
import os

import pytest

import brand
import portfolio_metrics as pm
import profiles
import report

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


def test_report_builds_when_the_chart_engine_is_unavailable(book, monkeypatch):
    """THE load-bearing test. Simulate kaleido being absent or broken — exactly
    what happens on Community Cloud, and on any Apple-silicon machine that got
    kaleido 0.2.1 — and require a complete document anyway."""
    monkeypatch.setattr(report, "_png", lambda *a, **k: None)
    import tabs.dashboard as dash
    p, df, sect = book
    figures = [("Where your money is", dash._donut(sect, "$"))]
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        figures=figures, profile_label="Balanced growth")
    assert data[:5] == b"%PDF-"
    text = " ".join(pg.extract_text() for pg in pypdf.PdfReader.__call__(
        __import__("io").BytesIO(data)).pages)
    assert "Holdings" in text, "the tables must survive a dead chart engine"
    assert "could not be rendered" in text, \
        "a report that silently drops its charts is worse than one that says so"


def test_a_single_broken_figure_does_not_lose_the_others(book, monkeypatch):
    calls = {"n": 0}

    def flaky(fig, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return None
    monkeypatch.setattr(report, "_png", flaky)
    p, df, sect = book
    import tabs.dashboard as dash
    # _png swallows its own exceptions, so a raise here proves isolation.
    with pytest.raises(RuntimeError):
        flaky(None)
    data = report.build(portfolio=p, positions=df, sector_df=sect,
                        figures=[("a", dash._donut(sect, "$"))])
    assert data[:5] == b"%PDF-"


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

def test_print_restyle_makes_type_dark_on_white(book):
    """theme.style_fig paints INK_2 (#c3c2b7) type for a dark page. Dropped
    onto white that measures about 1.9:1 — effectively invisible. Chart colours
    live in the figure JSON, not CSS, so no stylesheet can fix this."""
    import tabs.dashboard as dash
    p, df, sect = book
    printed = report._for_print(dash._donut(sect, "$"))
    assert printed.layout.paper_bgcolor == report.PAPER
    assert printed.layout.font.color == report.PAGE_INK
    assert printed.layout.font.color.lower() != "#c3c2b7"


def test_print_restyle_does_not_touch_series_colours(book):
    """GOOD/BAD and CATEGORICAL were matched on luminance AND chroma and hold
    up on white. Only the chrome flips."""
    import tabs.dashboard as dash
    p, df, sect = book
    original = dash._donut(sect, "$")
    printed = report._for_print(original)
    assert list(printed.data[0].marker.colors) == list(original.data[0].marker.colors)


def test_restyle_does_not_mutate_the_on_screen_figure(book):
    """The app keeps rendering after an export. Restyling in place would leave
    the live dashboard painted for paper."""
    import tabs.dashboard as dash
    p, df, sect = book
    fig = dash._donut(sect, "$")
    before = fig.layout.paper_bgcolor
    report._for_print(fig)
    assert fig.layout.paper_bgcolor == before


# --------------------------------------------------------------------------
# Availability reporting
# --------------------------------------------------------------------------

def test_availability_never_raises_and_always_explains():
    state = report.availability()
    assert set(state) == {"pdf", "charts", "why"}
    assert isinstance(state["pdf"], bool) and isinstance(state["charts"], bool)
    if not state["charts"]:
        assert state["why"], "an unavailable engine must come with a reason"


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
