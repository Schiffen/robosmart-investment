"""Model-authored text must never reach the page as markup or as markdown.

The live app rendered a judge verdict whose "weakest bear claim" read:

    $5B data-center investment represents 'incremental leverage risk' against
    debt-to-equity of 6.555 is unsupported speculation ...

with the span between the two dollar signs eaten by Streamlit's LaTeX parser
and painted as a green monospace code block, mid-sentence, on the screen a
technical evaluator grades hardest.

That was the cosmetic half. The other half was that every one of those strings
was interpolated into an f-string rendered with `unsafe_allow_html=True`, so a
model emitting markup got that markup executed in the page.

These tests pin both halves.
"""

import os
import re

import pytest

import theme
from tabs.attribution import _safe_link

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "app.py")


# --------------------------------------------------------------------------
# The escaping boundary
# --------------------------------------------------------------------------

def test_safe_escapes_html():
    out = theme.safe("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_safe_escapes_attribute_breakouts():
    """badge() and the verdict card interpolate into style='...' attributes."""
    out = theme.safe("' onmouseover='alert(1)")
    assert "'" not in out or "&#x27;" in out
    assert "onmouseover='alert" not in out


def test_safe_md_neutralises_the_dollar_span_that_broke_the_judge_card():
    """The exact reported failure: two dollar signs in one sentence."""
    claim = ("$5B data-center investment represents 'incremental leverage risk' "
             "against debt-to-equity of 6.555 is unsupported speculation")
    out = theme.safe_md(claim)
    # Neither dollar sign may survive unescaped, or Streamlit reads the span
    # between them as inline LaTeX and swallows the sentence.
    assert "\\$" in out
    assert not [i for i, ch in enumerate(out)
                if ch == "$" and (i == 0 or out[i - 1] != "\\")], \
        "an unescaped $ survived — the LaTeX span can still trigger"


def test_safe_md_neutralises_backticks_and_emphasis():
    out = theme.safe_md("use `code` and *emphasis* and _underscores_")
    for ch in ("`", "*", "_"):
        assert f"\\{ch}" in out


def test_safe_handles_non_strings_and_none():
    """A malformed model response must never take a tab down."""
    assert theme.safe(None) == ""
    assert theme.safe(42) == "42"
    assert theme.safe(["a"]) == "[&#x27;a&#x27;]"


def test_badge_escapes_its_own_label():
    """badge() is fed model-authored verdict/strength/likelihood values."""
    out = theme.badge("<b>BULL</b>", "bull")
    assert "<b>BULL</b>" not in out
    assert "&lt;b&gt;" in out


# --------------------------------------------------------------------------
# Model-authored URLs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "",
    None,
])
def test_unsafe_schemes_are_dropped(bad):
    """`source_link` is model-authored and lands in a markdown link target."""
    assert _safe_link(bad) is None


@pytest.mark.parametrize("good", [
    "https://www.reuters.com/technology/some-story",
    "http://example.com/a?b=c&d=e",
])
def test_http_links_survive(good):
    assert _safe_link(good) == good


def test_parens_in_a_link_cannot_terminate_the_markdown_target():
    out = _safe_link("https://en.wikipedia.org/wiki/Foo_(bar)")
    assert out is not None
    assert "(" not in out and ")" not in out


# --------------------------------------------------------------------------
# End to end, through the real render path
# --------------------------------------------------------------------------

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

_POISON = "<img src=x onerror=alert(1)> $5B and $9B"


def test_a_hostile_debate_renders_without_emitting_markup(monkeypatch):
    """Render a debate whose every model field is hostile, through the real
    Bull vs Bear view, and assert nothing executable reaches the output."""
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")

    # app.py auto-loads the default book when session_state.portfolio is unset,
    # and _load() overwrites active_ticker with that book's first holding — so
    # the debate cache has to be keyed on the ticker the app will actually land
    # on, not on one picked here.
    import profiles
    book = profiles.load_portfolio("balanced_growth")
    ticker = book["positions"][0]["ticker"]

    poisoned = {
        "ticker": ticker,
        "bull": {
            "opening": {"thesis": _POISON,
                        "claims": [{"claim": _POISON, "evidence": _POISON,
                                    "strength": _POISON}]},
            "rebuttal": {"points": [{"attacks": _POISON, "counter": _POISON,
                                     "evidence": _POISON}]},
        },
        "bear": {
            "opening": {"thesis": _POISON,
                        "claims": [{"claim": _POISON, "evidence": _POISON,
                                    "strength": "high"}]},
            "rebuttal": {"points": [{"attacks": _POISON, "counter": _POISON,
                                     "evidence": _POISON}]},
        },
        "judge": {
            "verdict": _POISON, "confidence": 58, "reasoning": _POISON,
            "weakest_bull_claim": _POISON, "weakest_bear_claim": _POISON,
            "falsifiers": [_POISON, _POISON], "key_uncertainty": _POISON,
        },
    }

    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["view"] = "Bull vs Bear"
    at.session_state["portfolio"] = book
    at.session_state["loaded_profile"] = "balanced_growth"
    at.session_state["active_ticker"] = ticker
    at.session_state["debate_results"] = {ticker: poisoned}
    at.run()

    assert not at.exception, f"hostile debate crashed the view: {at.exception}"
    assert len(at.error) == 0

    body = "\n".join(m.value for m in at.markdown if isinstance(m.value, str))

    # The app now emits <img> of its OWN — the brand marks in the sidebar
    # masthead, inlined as base64 data: URIs by brand.py. Those are
    # app-authored, read from local files, and are exactly the trusted markup
    # this test was never about.
    #
    # So strip them FIRST and then sweep for tags. The pattern is deliberately
    # narrow: it matches only an <img> whose src is an inline SVG data URI,
    # which is a shape no model-authored string can reach — the payload here is
    # `<img src=x onerror=alert(1)>`, and `src=x` cannot satisfy it. Widening
    # this to a bare `<img[^>]*>` would gut the assertion, because that is the
    # exact tag the attack emits.
    trusted_mark = r'<img src="data:image/svg\+xml;base64,[A-Za-z0-9+/=]+"[^>]*>'
    assert re.search(trusted_mark, body), \
        "the app's own brand marks did not render — strip pattern is stale"
    swept = re.sub(trusted_mark, "", body)

    # What matters is whether a TAG survives, not whether the characters do.
    # "onerror=alert(1)" as escaped text content is inert; the danger is the
    # angle bracket that would open an element around it.
    assert "<img" not in swept, "raw <img> tag reached the page"
    assert "<script" not in swept, "raw <script> tag reached the page"

    # The payload IS present, escaped — so we know it rendered rather than
    # being silently dropped, which would make this test pass for the wrong
    # reason.
    assert "&lt;img src=x onerror=alert(1)&gt;" in body, \
        "the hostile text never rendered at all"

    # And the dollar-span that broke the judge card is escaped everywhere it
    # appears in prose that Streamlit will parse as markdown.
    assert "$5B and $9B" not in body, "an unescaped $…$ span survived in prose"
