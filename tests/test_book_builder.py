"""The generated example book must obey the answers, and be arithmetic.

Two properties carry this feature, and both are asserted here rather than
inspected by eye:

  * A book satisfies every numeric bound its answers imply. That is what makes
    "the model respected what you said" checkable instead of impressionistic.
  * The model supplies WEIGHTS and prose only. Shares come from
    `portfolio.from_weights` against a real settled close, so the "invested"
    column is arithmetic the app performed. A model-authored share count would
    imply a model-authored price, and that column sits directly under a computed
    book total.

Offline throughout: USE_MOCK_LLM plus no API key, the established pattern. The
same bound assertions are reused under --llm against the live model, so the mock
allocator doubles as the oracle.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_spec
import portfolio as pf
import shelf
from agents import book_builder as bb
from market_data import fixture


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def answers(**over):
    a = book_spec.default_answers()
    a.update(over)
    return a


# Deliberately spread: a cautious beginner, a bold stock picker, an income
# investor who wants breadth, and two with hard category constraints.
PROFILES = {
    "cautious_beginner": dict(purpose="preservation", horizon="under_2y",
                              loss_limit="5", behaviour="sell_all",
                              experience="none", concentration="middle"),
    "bold_stock_picker": dict(purpose="growth", horizon="over_10y",
                              loss_limit="none", behaviour="buy_more",
                              experience="stocks", concentration="handful"),
    "income_broad": dict(purpose="income", horizon="5_10y", loss_limit="20",
                         behaviour="hold", experience="etfs",
                         concentration="broad"),
    "no_technology": dict(purpose="growth", horizon="over_10y", loss_limit="35",
                          behaviour="hold", experience="stocks",
                          concentration="handful",
                          exclude_categories=["Technology"]),
    "bonds_and_gold_only": dict(purpose="preservation", horizon="under_2y",
                                loss_limit="5", behaviour="sell_all",
                                experience="none", concentration="middle",
                                include_categories=["Bonds", "Gold"]),
}


def draft(name):
    a = answers(**PROFILES[name])
    return a, book_spec.constraints(a), bb.draft_example_book(a, "", 20_000.0)


def weights(book):
    return {x["ticker"]: x["weight_pct"] / 100.0 for x in book["allocation"]}


# --------------------------------------------------------------------------
# Shape and provenance
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(PROFILES))
def test_the_offline_book_is_marked_as_rule_drafted(name):
    """Recorded output must never be able to look live (PRODUCT.md principle 4)."""
    _, _, book = draft(name)
    assert book["is_mock"] is True
    assert book["generated_by"] == "rules"
    assert book["notice"].strip()


def test_the_rule_drafted_tagline_is_templated_from_the_numbers():
    """Stronger than a label saying "recorded": output that structurally cannot
    be mistaken for model prose."""
    _, c, book = draft("cautious_beginner")
    assert "beta capped at" in book["tagline"]
    assert f"{c['beta_max']:.2f}" in book["tagline"]


@pytest.mark.parametrize("name", list(PROFILES))
def test_every_holding_carries_a_reason(name):
    _, _, book = draft(name)
    assert book["allocation"]
    assert all(x["why"].strip() for x in book["allocation"])


@pytest.mark.parametrize("name", list(PROFILES))
def test_the_book_never_returns_shares_dollars_or_prices(name):
    """The single most important constraint. Anything money-shaped here would
    have had to invent a price."""
    _, _, book = draft(name)
    for x in book["allocation"]:
        assert set(x) == {"ticker", "weight_pct", "why"}, x
    for banned in ("shares", "price", "cost_basis", "market_value", "amount"):
        assert banned not in book, banned


# --------------------------------------------------------------------------
# Bounds — the whole point
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(PROFILES))
def test_every_ticker_is_on_the_shelf_and_allowed(name):
    _, c, book = draft(name)
    for x in book["allocation"]:
        assert x["ticker"] in shelf.SHELF, x["ticker"]
        assert x["ticker"] in c["allowed"], x["ticker"]


@pytest.mark.parametrize("name", list(PROFILES))
def test_excluded_categories_are_at_zero_not_merely_underweight(name):
    _, c, book = draft(name)
    for x in book["allocation"]:
        assert shelf.category_of(x["ticker"]) not in c["excluded_categories"]


@pytest.mark.parametrize("name", list(PROFILES))
def test_weights_are_a_share_of_the_invested_money_and_sum_to_100(name):
    """Cash sits OUTSIDE the allocation, so the weights share a unit with
    portfolio_metrics — which excludes cash from every weight it computes.

    Summing weights to `100 - cash_pct` instead meant a holding capped at 15% of
    the whole book was printed by the dashboard as 17.65% of the invested money,
    and the tension rules — reading that same cash-excluded figure — flagged a
    breach against a book the app had just generated.
    """
    _, _, book = draft(name)
    total = sum(x["weight_pct"] for x in book["allocation"])
    assert total == pytest.approx(100.0, abs=0.01)
    assert all(x["weight_pct"] > 0 for x in book["allocation"])
    assert 0 <= book["cash_pct"] <= 100


@pytest.mark.parametrize("name", list(PROFILES))
def test_no_holding_exceeds_the_position_cap(name):
    _, c, book = draft(name)
    if "position_max_vs_holdings" in c["infeasible"]:
        pytest.skip("the cap is arithmetically unreachable for these answers")
    biggest = max(weights(book).values())
    assert biggest <= c["position_max"] + 1e-6, f"{biggest:.3f} > {c['position_max']}"


@pytest.mark.parametrize("name", list(PROFILES))
def test_the_holding_count_is_within_what_the_answers_imply(name):
    _, c, book = draft(name)
    lo, hi = c["holdings"]
    assert len(book["allocation"]) <= hi
    if not c["infeasible"]:
        assert len(book["allocation"]) >= min(lo, len(c["allowed"]))


@pytest.mark.parametrize("name", list(PROFILES))
def test_the_defensive_floor_is_honoured(name):
    _, c, book = draft(name)
    w = weights(book)
    defensive = sum(v for t, v in w.items()
                    if shelf.role_of(t) in shelf.DEFENSIVE_ROLES)
    assert defensive >= c["defensive_floor"] - 1e-6, (
        f"{defensive:.3f} < floor {c['defensive_floor']}")


@pytest.mark.parametrize("name", list(PROFILES))
def test_the_single_share_cap_is_honoured(name):
    _, c, book = draft(name)
    w = weights(book)
    stocks = sum(v for t, v in w.items() if shelf.is_single_stock(t))
    assert stocks <= c["single_stock_max"] + 1e-6, (
        f"{stocks:.3f} > cap {c['single_stock_max']}")


def test_a_beginner_is_given_no_individual_company_shares():
    _, _, book = draft("cautious_beginner")
    assert not any(shelf.is_single_stock(x["ticker"]) for x in book["allocation"])


# --------------------------------------------------------------------------
# The questionnaire must not be inert — the failure this design exists to avoid
# --------------------------------------------------------------------------

def test_opposite_investors_get_materially_different_books():
    """A recorded fixture would have returned the same book for both, in exactly
    the mode the deployed app and this whole suite run in."""
    _, _, cautious = draft("cautious_beginner")
    _, _, bold = draft("bold_stock_picker")

    a, b = set(weights(cautious)), set(weights(bold))
    overlap = len(a & b) / max(1, len(a | b))
    assert overlap < 0.5, f"the two books share {overlap:.0%} of their holdings"

    def defensive(book):
        return sum(v for t, v in weights(book).items()
                   if shelf.role_of(t) in shelf.DEFENSIVE_ROLES)
    assert defensive(cautious) > defensive(bold) + 0.20


@pytest.mark.parametrize("qid", ["purpose", "horizon", "loss_limit",
                                 "experience", "concentration"])
def test_changing_one_answer_changes_the_book(qid):
    """Every question must reach the output, or it is a form field for show."""
    base = dict(PROFILES["income_broad"])
    seen = set()
    for opt in book_spec.question(qid)["options"]:
        a = answers(**{**base, qid: opt["key"]})
        book = bb.draft_example_book(a, "", 20_000.0)
        seen.add(tuple(sorted((x["ticker"], round(x["weight_pct"], 1))
                              for x in book["allocation"])))
    assert len(seen) > 1, f"{qid} produced an identical book for every answer"


def test_the_same_answers_always_produce_the_same_book():
    """Deterministic, so a rerun does not reshuffle the reader's book."""
    a = answers(**PROFILES["income_broad"])
    first = bb.draft_example_book(a, "", 20_000.0)
    second = bb.draft_example_book(a, "", 20_000.0)
    assert first["allocation"] == second["allocation"]


def test_a_book_spreads_across_categories_rather_than_taking_the_first_names():
    """Shelf order alone handed every stock picker an all-Technology book."""
    _, _, book = draft("bold_stock_picker")
    cats = {shelf.category_of(x["ticker"]) for x in book["allocation"]}
    assert len(cats) >= 4, f"only {cats}"


# --------------------------------------------------------------------------
# Coercion: whatever the model returns must come out valid
# --------------------------------------------------------------------------

CONSTRAINTS = book_spec.constraints(answers(**PROFILES["income_broad"]))


def coerce(alloc, **extra):
    raw = {"name": "X", "emoji": "🧪", "tagline": "t", "notice": "n",
           "cash_pct": 0, "allocation": alloc}
    raw.update(extra)
    return bb._coerce(raw, CONSTRAINTS)


def _entry(t, w):
    return {"ticker": t, "weight_pct": w, "why": "because"}


@pytest.mark.parametrize("total", [97.0, 104.0, 61.5, 250.0])
def test_a_sum_that_is_not_100_is_renormalised(total):
    n = 5
    book = coerce([_entry(t, total / n)
                   for t in ["VTI", "VXUS", "BND", "SHY", "GLD"]])
    got = sum(x["weight_pct"] for x in book["allocation"]) + book["cash_pct"]
    assert got == pytest.approx(100.0, abs=0.01)


def test_an_off_shelf_ticker_is_dropped_and_recorded():
    book = coerce([_entry("VTI", 50), _entry("DOGECOIN", 50)])
    assert [x["ticker"] for x in book["allocation"]] == ["VTI"]
    assert any("DOGECOIN" in m for m in book["constraints_applied"])


def test_a_ticker_from_an_excluded_category_is_dropped():
    c = book_spec.constraints(answers(**PROFILES["no_technology"]))
    book = bb._coerce({"allocation": [_entry("NVDA", 50), _entry("JNJ", 50)]}, c)
    assert [x["ticker"] for x in book["allocation"]] == ["JNJ"]


def test_duplicate_tickers_are_merged_by_summing():
    book = coerce([_entry("VTI", 30), _entry("VTI", 20), _entry("BND", 50)])
    assert len(book["allocation"]) == 2
    vti = next(x for x in book["allocation"] if x["ticker"] == "VTI")
    bnd = next(x for x in book["allocation"] if x["ticker"] == "BND")
    assert vti["weight_pct"] == pytest.approx(bnd["weight_pct"], abs=0.01)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None, "lots", -5, 0])
def test_an_unusable_weight_drops_the_holding_rather_than_the_book(bad):
    book = coerce([_entry("VTI", 50), _entry("BND", bad)])
    assert [x["ticker"] for x in book["allocation"]] == ["VTI"]
    assert book["allocation"][0]["weight_pct"] == pytest.approx(100.0)


@pytest.mark.parametrize("raw", [{}, {"allocation": None}, {"allocation": []},
                                 {"allocation": ["VTI"]},
                                 {"allocation": [{"nope": 1}]}])
def test_a_malformed_response_yields_an_empty_allocation_not_an_exception(raw):
    book = bb._coerce(raw, CONSTRAINTS)
    assert book["allocation"] == []


def test_an_unusable_model_response_falls_back_to_the_allocator(monkeypatch):
    """The fallback exists so a bad response cannot hand the builder an empty
    table. Exercised by pointing the live path at junk."""
    monkeypatch.setattr(bb.llm, "use_mock", lambda: False)
    monkeypatch.setattr(bb.llm, "call_json",
                        lambda *a, **k: {"allocation": [_entry("NOTREAL", 100)]})
    a = answers(**PROFILES["income_broad"])
    book = bb.draft_example_book(a, "", 20_000.0)
    assert book["generated_by"] == "rules"
    assert book["allocation"]
    assert any("NOTREAL" in m for m in book["constraints_applied"])


def test_a_dead_model_falls_back_rather_than_raising(monkeypatch):
    monkeypatch.setattr(bb.llm, "use_mock", lambda: False)

    def boom(*a, **k):
        raise RuntimeError("no route to host")
    monkeypatch.setattr(bb.llm, "call_json", boom)
    book = bb.draft_example_book(answers(**PROFILES["income_broad"]), "", 20_000.0)
    assert book["generated_by"] == "rules" and book["allocation"]


@pytest.mark.parametrize("junk", ["", ":chart:", "not an emoji", None, "abc"])
def test_a_non_emoji_falls_back_to_the_default(junk):
    assert coerce([_entry("VTI", 100)], emoji=junk)["emoji"] == bb.DEFAULT_EMOJI


def test_cash_is_clamped_into_the_band():
    book = coerce([_entry("VTI", 100)], cash_pct=95)
    assert book["cash_pct"] <= CONSTRAINTS["cash_weight"][1] * 100 + 1e-9


# --------------------------------------------------------------------------
# Weights -> Contract A: the arithmetic the app performs itself
# --------------------------------------------------------------------------

def prices_for(book):
    return {x["ticker"]: fixture.get_context(x["ticker"])["price"]["current"]
            for x in book["allocation"]}


@pytest.mark.parametrize("name", list(PROFILES))
def test_a_drafted_book_becomes_valid_contract_a(name):
    _, _, book = draft(name)
    out = pf.from_weights(book["allocation"], prices_for(book), 20_000.0,
                          cash=1_000.0, sector_for=shelf.sector_of)
    assert set(out) == {"positions", "cash", "currency"}
    assert out["cash"] == 1_000.0
    assert pf.validate_rows(out["positions"], universe=shelf.tickers()) == []
    for p in out["positions"]:
        assert p["sector"] == shelf.sector_of(p["ticker"])
        assert p["shares"] > 0 and math.isfinite(p["shares"])


@pytest.mark.parametrize("name", list(PROFILES))
def test_cost_basis_is_the_settled_close_not_an_invented_number(name):
    """A synthetic book has no purchase history. Inventing one would print a
    fabricated P&L on the dashboard's first screen."""
    _, _, book = draft(name)
    prices = prices_for(book)
    out = pf.from_weights(book["allocation"], prices, 20_000.0,
                          sector_for=shelf.sector_of)
    for p in out["positions"]:
        assert p["cost_basis"] == pytest.approx(prices[p["ticker"]])


@pytest.mark.parametrize("name", list(PROFILES))
def test_invested_reconciles_to_shares_times_price(name):
    """The assertion the browser check repeats against the rendered page."""
    _, _, book = draft(name)
    prices = prices_for(book)
    investable = 20_000.0
    out = pf.from_weights(book["allocation"], prices, investable,
                          sector_for=shelf.sector_of)

    total = sum(p["shares"] * prices[p["ticker"]] for p in out["positions"])
    assert total == pytest.approx(investable, rel=0.02), (
        "the book's invested total drifted from what the reader put in")

    for p in out["positions"]:
        target = next(x["weight_pct"] for x in book["allocation"]
                      if x["ticker"] == p["ticker"])
        realised = 100.0 * p["shares"] * prices[p["ticker"]] / total
        assert realised == pytest.approx(target, abs=1.0), (
            f"{p['ticker']}: asked for {target:.2f}%, rounded shares give "
            f"{realised:.2f}%")


def test_an_unpriceable_holding_is_skipped_rather_than_priced_at_zero():
    alloc = [_entry("VTI", 50), _entry("BND", 50)]
    out = pf.from_weights(alloc, {"VTI": 300.0}, 10_000.0,
                          sector_for=shelf.sector_of)
    assert [p["ticker"] for p in out["positions"]] == ["VTI"]


def test_a_book_with_nothing_priceable_raises_rather_than_returning_empty():
    with pytest.raises(pf.PortfolioError):
        pf.from_weights([_entry("VTI", 100)], {}, 10_000.0)


# --------------------------------------------------------------------------
# Two defects that only a LIVE draft exposed
# --------------------------------------------------------------------------

MIDDLE = book_spec.constraints(answers(
    purpose="preservation", horizon="under_2y", loss_limit="5",
    behaviour="sell_all", experience="none", concentration="middle"))


def test_an_unreachable_position_cap_spreads_evenly_rather_than_giving_up():
    """A 15% cap cannot hold over five holdings that must sum to 100.

    The guard for that case used to `return alloc` UNTOUCHED, so a live draft of
    five holdings came back with one at 45% against a 15% cap — the clipping was
    skipped entirely. Equal weights are the allocation that minimises the
    largest holding, so they are the closest thing to the cap that exists.
    """
    book = bb._coerce({"allocation": [
        _entry("BND", 45), _entry("SHY", 20), _entry("LQD", 15),
        _entry("GLD", 10), _entry("VTI", 10)]}, MIDDLE)

    weights = [x["weight_pct"] for x in book["allocation"]]
    assert max(weights) == pytest.approx(20.0, abs=0.01), (
        f"largest holding is {max(weights):.1f}% — the cap was skipped again")
    assert sum(weights) == pytest.approx(100.0, abs=0.01)
    assert any("could not keep every holding under" in m
               for m in book["constraints_applied"])


def test_a_reachable_position_cap_still_clips_rather_than_equalising():
    """The even-spread path must not swallow the ordinary case."""
    c = book_spec.constraints(answers(**PROFILES["bold_stock_picker"]))
    book = bb._coerce({"allocation": [
        _entry("NVDA", 60), _entry("MSFT", 10), _entry("AAPL", 10),
        _entry("GOOGL", 10), _entry("AMZN", 5), _entry("BND", 5)]}, c)
    weights = sorted(x["weight_pct"] for x in book["allocation"])
    assert max(weights) <= c["position_max"] * 100 + 0.01
    assert len(set(round(w, 2) for w in weights)) > 1, "everything was equalised"


def test_an_equity_ceiling_creates_a_defensive_floor_the_model_must_meet():
    """"Shares: 75% to 95%" was stated to the model and never enforced, because
    `defensive_floor` for a long horizon is zero. A live draft came back 100%
    equity and nothing caught it."""
    c = book_spec.constraints(answers(**PROFILES["bold_stock_picker"]))
    assert c["defensive_floor"] >= 1.0 - c["equity_weight"][1] - 1e-9
    assert c["defensive_floor"] > 0


def test_the_defensive_floor_is_raised_by_rescaling_what_is_there():
    c = book_spec.constraints(answers(**PROFILES["bold_stock_picker"]))
    book = bb._coerce({"allocation": [
        _entry("NVDA", 24), _entry("MSFT", 24), _entry("AAPL", 24),
        _entry("GOOGL", 24), _entry("BND", 4)]}, c)
    w = weights(book)
    defensive = sum(v for t, v in w.items()
                    if shelf.role_of(t) in shelf.DEFENSIVE_ROLES)
    assert defensive >= c["defensive_floor"] - 1e-6
    assert sum(w.values()) == pytest.approx(1.0, abs=0.001)
    # Nothing is ANNOUNCED as done. Success is silent; only shortfalls are named.
    assert not any("could only reach" in m for m in book["constraints_applied"])


def test_a_missing_defensive_sleeve_is_reported_not_invented():
    """Every holding carries a `why` naming something the reader said. A ticker
    added here to satisfy an arithmetic floor would have nothing to put there."""
    c = book_spec.constraints(answers(**PROFILES["bold_stock_picker"]))
    book = bb._coerce({"allocation": [
        _entry("NVDA", 50), _entry("MSFT", 50)]}, c)
    assert {x["ticker"] for x in book["allocation"]} == {"NVDA", "MSFT"}
    assert any("could only reach" in m for m in book["constraints_applied"]), (
        f"the shortfall went unreported: {book['constraints_applied']}")


def test_the_prompt_tells_the_model_how_many_holdings_the_cap_needs():
    """Told only "at most 15% each" and "4 to 7 holdings", a live draft returned
    five — which cannot sum to 100 with none above 15%."""
    block = book_spec.describe_constraints(MIDDLE)
    assert "at least" in block.lower()
    assert "7" in block


def test_a_concentration_breach_is_surfaced_whatever_answer_was_given():
    """Scoped to "broad", this told a "middle" reader nothing about a 45%
    holding against the 15% their answer implied."""
    for choice in ("handful", "middle", "broad"):
        a = answers(concentration=choice)
        c = book_spec.constraints(a)
        over = c["position_max"] + 0.30
        t = book_spec.book_tensions(a, c, {"max_weight": over, "hhi": 0.5})
        assert any(x["id"] == "diversified_but_concentrated" for x in t), choice


# --------------------------------------------------------------------------
# The honesty property: no message may claim what the book contradicts
# --------------------------------------------------------------------------
#
# The enforcement chain used to be a sequence of one-shot fixups, each of which
# appended a message and then had its work undone by the next. Two of those were
# APP-AUTHORED claims about arithmetic that had not happened:
#
#   * "reduced the single-share portion to what your experience answer allows"
#     over a book that was 100% one company share, because the rescale was
#     followed immediately by a renormalise that scaled it straight back.
#   * "raised bonds and gold to the N% your answers imply" over a book at a
#     third of that, because the floor step ended by calling the position cap.
#
# This codebase draws a hard line between a claim the tests enforce and prose
# nobody checked. Those put unchecked claims on the checked side of it — which
# is worse than the model doing it, because the app controls this text.

def _measure(book):
    w = weights(book)
    return {
        "biggest": max(w.values()) if w else 0.0,
        "defensive": sum(v for t, v in w.items()
                         if shelf.role_of(t) in shelf.DEFENSIVE_ROLES),
        "stocks": sum(v for t, v in w.items() if shelf.is_single_stock(t)),
        "n": len(w),
    }


ANSWER_SPACE = [
    dict(zip(("purpose", "horizon", "loss_limit", "behaviour", "experience",
              "concentration"), combo))
    for combo in [
        ("preservation", "under_2y", "5", "sell_all", "none", "middle"),
        ("preservation", "under_2y", "5", "sell_all", "none", "broad"),
        ("growth", "over_10y", "none", "buy_more", "stocks", "handful"),
        ("growth", "over_10y", "none", "hold", "fund", "middle"),
        ("income", "5_10y", "20", "hold", "etfs", "broad"),
        ("income", "2_5y", "10", "sell_some", "fund", "handful"),
        ("learning", "5_10y", "20", "hold", "none", "handful"),
        ("learning", "over_10y", "35", "buy_more", "etfs", "middle"),
    ]
]


@pytest.mark.parametrize("combo", ANSWER_SPACE)
@pytest.mark.parametrize("cats", [{}, {"include_categories": ["Technology"]},
                                  {"exclude_categories": ["Technology", "Bonds"]},
                                  {"include_categories": ["Bonds", "Gold"]}])
def test_no_shortfall_is_reported_that_the_book_does_not_actually_have(combo, cats):
    a = answers(**combo, **cats)
    c = book_spec.constraints(a)
    book = bb.draft_example_book(a, "", 20_000.0)
    if not book["allocation"]:
        return
    m = _measure(book)
    said = " ".join(book["constraints_applied"])

    if "could not keep every holding under" in said:
        assert m["biggest"] > c["position_max"] + 0.0001, (
            f"claimed the cap was unreachable, but the largest holding is "
            f"{m['biggest']:.3f} <= {c['position_max']}")
    if "could only reach" in said:
        assert m["defensive"] < c["defensive_floor"] - 0.0001
    if "individual company shares are" in said:
        assert m["stocks"] > c["single_stock_max"] + 0.0001


@pytest.mark.parametrize("combo", ANSWER_SPACE)
@pytest.mark.parametrize("cats", [{}, {"include_categories": ["Technology"]},
                                  {"exclude_categories": ["Technology", "Bonds"]}])
def test_every_bound_it_misses_is_named(combo, cats):
    """The other direction: a book may fall short, but never silently."""
    a = answers(**combo, **cats)
    c = book_spec.constraints(a)
    book = bb.draft_example_book(a, "", 20_000.0)
    if not book["allocation"]:
        return
    m = _measure(book)
    said = " ".join(book["constraints_applied"])

    if m["biggest"] > c["position_max"] + 0.01:
        assert "could not keep every holding under" in said, said
    if m["defensive"] < c["defensive_floor"] - 0.01:
        assert "could only reach" in said, said
    if m["stocks"] > c["single_stock_max"] + 0.01:
        assert "individual company shares are" in said, said


@pytest.mark.parametrize("combo", ANSWER_SPACE)
def test_a_reader_who_ticks_one_category_still_gets_a_usable_book(combo):
    """Ticking "Technology" used to cut the shelf to six names, leaving nothing
    to satisfy the caps with — a cautious reader two clicks in got 100% NVDA."""
    a = answers(**combo, include_categories=["Technology"])
    c = book_spec.constraints(a)
    book = bb.draft_example_book(a, "", 20_000.0)
    m = _measure(book)
    assert m["n"] >= min(c["holdings"][0], 4), (
        f"only {m['n']} holdings from a one-category preference")
    assert m["stocks"] <= c["single_stock_max"] + 0.01, (
        f"single-share cap breached: {m['stocks']:.2f} > {c['single_stock_max']}")


def test_weights_always_sum_to_100_whatever_the_model_returns():
    import random
    rnd = random.Random(20260804)
    c = book_spec.constraints(answers(**PROFILES["income_broad"]))
    pool = shelf.tickers() + ["FAKE", "", None]
    for _ in range(300):
        alloc = [{"ticker": rnd.choice(pool),
                  "weight_pct": rnd.choice([rnd.uniform(-5, 90), float("nan"),
                                            float("inf"), 0, "x"]),
                  "why": "w"}
                 for _ in range(rnd.randint(0, 12))]
        book = bb._coerce({"allocation": alloc,
                           "cash_pct": rnd.choice([0, 5, 150, -3, "x"])}, c)
        if book["allocation"]:
            total = sum(x["weight_pct"] for x in book["allocation"])
            assert total == pytest.approx(100.0, abs=0.01), total
            assert all(x["ticker"] in c["allowed"] for x in book["allocation"])
