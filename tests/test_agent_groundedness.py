"""Do the agents cite things that actually exist in their input?

The debate and explainer prompts don't ask the model to be smart — they ask it to
be *traceable*. Every claim must rest on a number or headline from the CONTEXT,
and "no clear cause found" is an explicitly permitted answer. Those are checkable
promises, so they're checked here rather than eyeballed.

Two tiers:
  - default: deterministic, no API. Covers the recorded/mock paths and the
    schema the UI reads.
  - `--llm`: the same assertions against the REAL model, on frozen fixture data
    so any variation is the model's and not the market's.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_layer
from agents import debate as debate_mod
from agents import explainer as explainer_mod
from factor_model import decompose_move

VALID_LIKELIHOOD = {"high", "medium", "low"}
VALID_ASSESSMENT = {"noise", "notable", "significant"}
VALID_VERDICT = {"bull", "bear", "inconclusive"}
VALID_STRENGTH = {"high", "medium", "low"}


def _context_and_decomposition(ticker):
    ctx = data_layer.get_context(ticker)
    dec = decompose_move(ctx, benchmark_fetcher=data_layer.get_benchmark_history)
    return ctx, dec


# Publishers emit typographic punctuation; models routinely normalise it when
# quoting a headline back. Comparing raw strings treats that as fabrication:
#   given  "...from China’s AI loophole"   (U+2019)
#   cited  "...from China's AI loophole"   (U+0027)
# That is a faithful citation, and a check that calls it a hallucination is worse
# than no check at all — it trains you to ignore it. Normalise punctuation and
# whitespace, then still require an EXACT match, so a paraphrase or an invented
# headline is caught just as before.
_PUNCT = str.maketrans({
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "…": "...",
})


def _norm(text) -> str:
    return " ".join(str(text or "").translate(_PUNCT).split()).casefold()


def _input_titles(ctx):
    return {_norm(n.get("title")) for n in (ctx.get("news") or []) if n.get("title")}


def _input_links(ctx):
    return {(n.get("link") or "").strip() for n in (ctx.get("news") or []) if n.get("link")}


def _assert_explainer_contract(result, ctx, dec):
    """The output shape tabs/attribution.py reads, plus the no-fabrication rule."""
    assert isinstance(result, dict)
    assert set(result) >= {"explanations", "no_cause_found", "residual_assessment", "caveat"}
    assert isinstance(result["explanations"], list)
    assert isinstance(result["no_cause_found"], bool)
    assert result["residual_assessment"] in VALID_ASSESSMENT

    # Empty list and "no cause found" must agree — the UI branches on this, and a
    # disagreement would render a "most likely explanations" header above nothing.
    assert bool(result["explanations"]) != result["no_cause_found"]

    titles, links = _input_titles(ctx), _input_links(ctx)
    for e in result["explanations"]:
        assert e["likelihood"] in VALID_LIKELIHOOD
        assert e["cause"].strip()
        headline = (e.get("evidence_headline") or "").strip()
        assert headline, "an explanation with no headline violates the prompt's core rule"
        # THE hallucination check: the cited headline must be one it was given.
        assert _norm(headline) in titles, (
            f"fabricated headline {headline!r} — not among the {len(titles)} supplied")
        link = (e.get("source_link") or "").strip()
        if link:
            assert link in links, f"fabricated link {link!r}"


# --------------------------------------------------------------------------
# Deterministic (no API)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ticker", ["NVDA", "MSFT", "AAPL", "JNJ", "JPM", "XOM", "GLD"])
def test_recorded_explainer_never_cites_a_headline_it_was_not_given(ticker, monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx, dec = _context_and_decomposition(ticker)
    _assert_explainer_contract(explainer_mod.explain_idiosyncratic(ctx, dec), ctx, dec)


def test_typographic_punctuation_is_not_mistaken_for_fabrication():
    """Regression on a false positive this check itself produced.

    The real model cited "...from China's AI loophole" for a supplied headline
    reading "...from China’s AI loophole". That is a faithful citation; the
    original exact-match assertion called it a hallucination.
    """
    ctx = {"news": [{"title": "Nvidia stock faces new risk from China’s AI loophole",
                     "link": "https://example.test/1"}]}
    assert _norm("Nvidia stock faces new risk from China's AI loophole") in _input_titles(ctx)
    assert _norm("Apple   announces  —  results…") == _norm("Apple announces - results...")
    # ...but a genuinely different headline must still fail.
    assert _norm("Nvidia stock soars on earnings beat") not in _input_titles(ctx)


def test_recorded_explainer_declines_rather_than_inventing_a_cause(monkeypatch):
    """With no usable headlines the only honest answer is 'no clear cause found'.
    This is the behaviour the tab renders as an answer, not an error."""
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx, dec = _context_and_decomposition("NVDA")
    ctx["news"] = []
    result = explainer_mod.explain_idiosyncratic(ctx, dec)
    assert result["no_cause_found"] is True
    assert result["explanations"] == []
    assert result["caveat"].strip()


def test_explainer_will_not_attribute_a_move_to_another_company(monkeypatch):
    """The regression `_mentions_company` exists for: NVDA's move was once
    attributed to a Teva headline purely because Yahoo attached it to NVDA."""
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx, dec = _context_and_decomposition("NVDA")
    ctx["news"] = [{"title": "Teva announces generic drug settlement",
                    "publisher": "Reuters", "published": "", "link": "https://x/1"}]
    result = explainer_mod.explain_idiosyncratic(ctx, dec)
    assert result["no_cause_found"] is True, "attributed NVDA's move to a Teva headline"


def test_sub_noise_residual_short_circuits_before_any_model_call(monkeypatch):
    """Below 0.3pp the tab must answer without consulting a model at all —
    verified by making any call raise."""
    def _explode(*a, **k):
        raise AssertionError("called the model for a residual inside daily noise")
    monkeypatch.setattr(explainer_mod.llm, "call_json", _explode)

    ctx, _ = _context_and_decomposition("NVDA")
    result = explainer_mod.explain_idiosyncratic(ctx, {"idiosyncratic_pct": 0.05})
    assert result["residual_assessment"] == "noise"
    assert result["no_cause_found"] is True


def test_recorded_debate_declares_which_ticker_it_was_recorded_for(monkeypatch):
    """The recorded debate is NVDA-specific. Served under another ticker without
    provenance it is indistinguishable from the model fabricating."""
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = debate_mod.run_debate(data_layer.get_context("JNJ"))
    assert result["is_mock"] is True
    assert result["recorded_for"] == "NVDA"
    assert result["ticker"] == "JNJ"


# --------------------------------------------------------------------------
# Against the real model — `pytest --llm`
# --------------------------------------------------------------------------

@pytest.fixture
def _needs_key():
    from dotenv import load_dotenv
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY")


@pytest.mark.llm
@pytest.mark.parametrize("ticker", ["NVDA", "XOM"])
def test_live_explainer_is_grounded_in_its_input(ticker, monkeypatch, _needs_key):
    """Same contract as the recorded path, against the real model.

    NVDA carries a -4.16pp residual (significant) with 7 headlines; XOM has only
    2 headlines, so it is the case where declining is the right answer.
    """
    monkeypatch.setenv("USE_MOCK_LLM", "0")
    ctx, dec = _context_and_decomposition(ticker)
    _assert_explainer_contract(explainer_mod.explain_idiosyncratic(ctx, dec), ctx, dec)


@pytest.mark.llm
def test_live_explainer_assessment_matches_the_residual_it_was_given(monkeypatch, _needs_key):
    monkeypatch.setenv("USE_MOCK_LLM", "0")
    ctx, dec = _context_and_decomposition("NVDA")
    result = explainer_mod.explain_idiosyncratic(ctx, dec)
    resid = abs(dec["idiosyncratic_pct"])
    expected = "noise" if resid < 0.3 else ("notable" if resid < 2.0 else "significant")
    assert result["residual_assessment"] == expected, (
        f"residual {resid:.2f}pp should be '{expected}'")


@pytest.fixture(scope="module")
def live_debate():
    """One real debate, shared by every assertion below.

    A debate is five chained model calls; running it per-test would quadruple the
    bill to re-derive the same object. Module-scoped, so it sets os.environ
    directly rather than via the function-scoped monkeypatch.
    """
    from dotenv import load_dotenv
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY")

    previous = os.environ.get("USE_MOCK_LLM")
    os.environ["USE_MOCK_LLM"] = "0"
    os.environ["USE_MOCK_DATA"] = "1"
    try:
        ctx = data_layer.get_context("NVDA")
        yield ctx, debate_mod.run_debate(ctx)
    finally:
        if previous is None:
            os.environ.pop("USE_MOCK_LLM", None)
        else:
            os.environ["USE_MOCK_LLM"] = previous


@pytest.mark.llm
def test_live_debate_obeys_its_declared_schema(live_debate):
    """Asserts only what the prompts explicitly promise — exactly 3 claims a
    side, exactly 3 falsifiers, a bounded confidence."""
    _, result = live_debate

    assert not result.get("is_mock"), "expected a live debate"
    for side in ("bull", "bear"):
        claims = result[side]["opening"]["claims"]
        assert len(claims) == 3, f"{side} returned {len(claims)} claims, prompt demands 3"
        for c in claims:
            assert c["claim"].strip() and c["evidence"].strip()
            assert str(c["strength"]).lower() in VALID_STRENGTH
        assert result[side]["rebuttal"]["points"]

    judge = result["judge"]
    assert str(judge["verdict"]).lower() in VALID_VERDICT
    assert isinstance(judge["confidence"], int) and 0 <= judge["confidence"] <= 100
    assert len(judge["falsifiers"]) == 3, "prompt demands EXACTLY 3 falsifiers"
    assert judge["reasoning"].strip()
    assert judge["key_uncertainty"].strip()


@pytest.mark.llm
def test_live_debate_claims_cite_numbers_that_exist_in_the_context(live_debate):
    """Every claim must cite a number or headline FROM the context.

    Checked as a ratio, not per-claim: a model may legitimately cite a headline
    instead of a number, or restate a market cap as "4.79T" where the context
    holds 4790000000000. A majority of evidence strings failing to contain any
    context number is the signal worth catching.
    """
    ctx, result = live_debate

    block = debate_mod._context_block(ctx)
    titles = _input_titles(ctx)

    grounded = total = 0
    for side in ("bull", "bear"):
        for claim in result[side]["opening"]["claims"]:
            evidence = claim["evidence"]
            total += 1
            numbers = re.findall(r"\d+\.?\d*", evidence)
            cites_number = any(n in block for n in numbers if len(n) >= 3)
            # Compare normalised on both sides, for the same reason as _norm above.
            evidence_norm = _norm(evidence)
            cites_headline = any(t and t[:40] in evidence_norm for t in titles)
            if cites_number or cites_headline:
                grounded += 1

    assert total == 6
    assert grounded >= 4, (
        f"only {grounded}/{total} claims cite a figure or headline traceable to "
        f"the context — the prompts make that mandatory")
