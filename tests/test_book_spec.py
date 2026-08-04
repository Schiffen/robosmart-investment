"""The questionnaire's bounds, and the tensions between what was said and what
the book measures.

These are the tests that make a generated book CHECKABLE. Every questionnaire
answer maps to a numeric bound, so "did the model respect the answers" is an
assertion rather than an impression — and every tension is arithmetic against
`portfolio_metrics` output, so it is a fact the reader could verify rather than
a claim the model made about its own work.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_spec
import shelf


def answers(**over):
    """A blank base plus whatever is under test — so each question's effect is
    visible in isolation rather than buried under five other answers."""
    a = book_spec.default_answers()
    a.update(over)
    return a


# A complete, internally COHERENT investor. Not "first option of everything":
# that combination wants capital preservation over under two years with a 5%
# loss limit and would also sell everything, which is contradictory enough that
# changing any one answer moved nothing.
COHERENT = {"purpose": "growth", "horizon": "over_10y", "loss_limit": "35",
            "behaviour": "hold", "experience": "etfs", "concentration": "middle"}


def complete(**over):
    a = answers(**COHERENT)
    a.update(over)
    return a


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------

def test_the_instrument_is_short():
    """FG11/05's complaint about real tools is length and vagueness, not rigour."""
    assert 5 <= len(book_spec.QUESTIONS) <= 8


def test_every_question_has_distinct_keyed_options_with_bounds():
    for q in book_spec.QUESTIONS:
        keys = [o["key"] for o in q["options"]]
        assert len(keys) == len(set(keys)), q["id"]
        assert len(keys) >= 2
        for o in q["options"]:
            assert o["label"].strip()
            assert isinstance(o["bounds"], dict)
            for name in o["bounds"]:
                assert name in book_spec._DEFAULTS, f"{q['id']}.{o['key']}: {name}"


def test_the_two_risk_questions_have_no_neutral_rung():
    """A non-answer scored as a mid-range attitude invents a moderate investor."""
    for qid in ("loss_limit", "behaviour"):
        labels = [o["label"].lower() for o in book_spec.question(qid)["options"]]
        for weasel in ("neither", "not sure", "no opinion", "somewhat", "moderate"):
            assert not any(weasel in l for l in labels), f"{qid}: {weasel}"


def test_no_question_asks_for_income_or_net_worth():
    """Real capacity questions, but this drafts a demo book — asking them would
    imply a suitability assessment that is explicitly not being made."""
    blob = " ".join(q["prompt"].lower() for q in book_spec.QUESTIONS)
    for banned in ("income you earn", "net worth", "salary", "dependants",
                   "how much do you earn"):
        assert banned not in blob


def test_nothing_is_pre_selected():
    """A pre-selected answer is an answer the reader did not give. The whole
    point of having no neutral rung is defeated if the form supplies one."""
    a = book_spec.default_answers()
    assert not book_spec.is_complete(a)
    assert set(book_spec.missing(a)) == set(book_spec.QUESTION_IDS)


def test_an_unanswered_form_still_yields_usable_feasible_constraints():
    """So the builder can render a preview before anything is answered."""
    c = book_spec.constraints(book_spec.default_answers())
    assert not c["infeasible"]
    assert c["allowed"]


def test_a_fully_answered_form_is_complete():
    assert book_spec.is_complete(complete())
    assert book_spec.missing(complete()) == []


def test_an_unanswered_question_is_reported_not_guessed():
    a = complete()
    del a["loss_limit"]
    assert not book_spec.is_complete(a)
    assert book_spec.missing(a) == ["loss_limit"]


# --------------------------------------------------------------------------
# The intersection IS the stated-tolerance-vs-stated-behaviour rule
# --------------------------------------------------------------------------

def test_behaviour_overrides_a_bolder_loss_limit_downward():
    bold = book_spec.constraints(answers(loss_limit="none", behaviour="hold"))
    conflicted = book_spec.constraints(answers(loss_limit="none", behaviour="sell_all"))
    assert conflicted["beta_max"] < bold["beta_max"], (
        "saying you would sell must pull the book toward caution, whatever you "
        "said you could withstand")
    assert conflicted["beta_max"] == pytest.approx(0.50)


def test_the_tighter_of_two_caps_always_wins():
    c = book_spec.constraints(answers(purpose="preservation", loss_limit="none"))
    assert c["beta_max"] == pytest.approx(0.75)


def test_bands_intersect_rather_than_overwrite():
    c = book_spec.constraints(answers(purpose="growth", experience="none",
                                      concentration="handful"))
    lo, hi = c["holdings"]
    assert (lo, hi) == (4, 7), "holdings did not intersect (4,7) with (4,8)"


def test_floors_take_the_largest():
    c = book_spec.constraints(answers(horizon="under_2y", loss_limit="5"))
    assert c["defensive_floor"] == pytest.approx(0.45)


@pytest.mark.parametrize("qid", book_spec.QUESTION_IDS)
def test_every_question_actually_changes_something(qid):
    """A question that moves no bound is decoration."""
    q = book_spec.question(qid)
    seen = set()
    for o in q["options"]:
        c = book_spec.constraints(answers(**{qid: o["key"]}))
        seen.add(tuple(sorted(
            (k, v) for k, v in c.items()
            if k in book_spec._DEFAULTS)))
    assert len(seen) > 1, f"{qid} produces the same constraints for every answer"


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------

def test_excluding_a_category_removes_its_tickers_entirely():
    c = book_spec.constraints(answers(exclude_categories=["Technology"]))
    assert "Technology" not in c["allowed_categories"]
    assert all(shelf.category_of(t) != "Technology" for t in c["allowed"])
    assert "NVDA" not in c["allowed"]


def test_including_categories_is_a_tilt_and_does_not_narrow_the_shelf():
    """The control says "Would like included", and its help says "Leave empty
    for no preference". Both promise a preference.

    It used to be a whitelist: ticking one box cut 41 tickers to six. That broke
    the promise AND was the root cause of the generator's worst output — with
    one category left there was often nothing to satisfy the position cap, the
    defensive floor or the single-share cap with, so a reader two clicks in
    could be handed a book that was 100% one company.
    """
    c = book_spec.constraints(answers(include_categories=["Bonds", "Gold"]))
    assert set(c["allowed_categories"]) == set(shelf.CATEGORIES)
    assert set(c["allowed"]) == set(shelf.tickers())
    # ...but the preference is carried, for the allocator and the prompt.
    assert set(c["include_categories"]) == {"Bonds", "Gold"}


def test_only_exclusions_narrow_the_shelf():
    c = book_spec.constraints(answers(include_categories=["Bonds"],
                                      exclude_categories=["Technology"]))
    assert "Technology" not in c["allowed_categories"]
    assert "NVDA" not in c["allowed"]
    assert "Healthcare" in c["allowed_categories"], "an unrelated category was cut"


def test_an_explicit_exclusion_beats_an_inclusion():
    """Saying "definitely not energy" is a stronger statement than ticking it."""
    c = book_spec.constraints(answers(include_categories=["Energy", "Bonds"],
                                      exclude_categories=["Energy"]))
    assert "Energy" not in c["allowed_categories"]
    assert "Bonds" in c["allowed_categories"]


def test_no_preference_means_the_whole_shelf():
    c = book_spec.constraints(answers())
    assert set(c["allowed"]) == set(shelf.tickers())


def test_unknown_categories_are_ignored_rather_than_crashing():
    c = book_spec.constraints(answers(include_categories=["Crypto", "Bonds"],
                                      exclude_categories=["Crypto", "Energy"]))
    assert set(c["include_categories"]) == {"Bonds"}
    assert set(c["excluded_categories"]) == {"Energy"}
    assert "Energy" not in c["allowed_categories"]


def test_a_defensive_floor_is_dropped_when_nothing_defensive_is_allowed():
    """Otherwise the generator is handed a bound it cannot possibly satisfy."""
    # Excluding everything defensive, since an INCLUSION no longer narrows.
    c = book_spec.constraints(answers(
        horizon="under_2y", exclude_categories=["Bonds", "Gold"]))
    assert c["defensive_floor"] == 0.0


# --------------------------------------------------------------------------
# Irreconcilable answers are surfaced, never raised
# --------------------------------------------------------------------------

def test_impossible_answers_populate_infeasible_rather_than_raising():
    c = book_spec.constraints(answers(experience="none", concentration="broad"))
    # 10% position cap needs >= 10 holdings; "none" caps holdings at 7.
    assert "position_max_vs_holdings" in c["infeasible"]


def test_an_empty_allowed_set_is_recorded_as_infeasible():
    c = book_spec.constraints(answers(exclude_categories=list(shelf.CATEGORIES)))
    assert c["allowed"] == ()
    assert "allowed" in c["infeasible"]


def test_ordinary_answers_are_feasible():
    for combo in ({}, {"purpose": "growth", "horizon": "over_10y"},
                  {"purpose": "preservation", "horizon": "under_2y",
                   "loss_limit": "5", "behaviour": "sell_all"}):
        c = book_spec.constraints(answers(**combo))
        assert not c["infeasible"], f"{combo} -> {c['infeasible']}"


# --------------------------------------------------------------------------
# Tensions visible in the answers alone
# --------------------------------------------------------------------------

def test_stated_tolerance_versus_stated_behaviour_fires():
    t = book_spec.answer_tensions(answers(loss_limit="35", behaviour="sell_all"))
    assert any(x["id"] == "tolerance_vs_behaviour" for x in t)


def test_it_stays_silent_when_the_two_agree():
    t = book_spec.answer_tensions(answers(loss_limit="35", behaviour="hold"))
    assert not any(x["id"] == "tolerance_vs_behaviour" for x in t)
    t = book_spec.answer_tensions(answers(loss_limit="5", behaviour="sell_all"))
    assert not any(x["id"] == "tolerance_vs_behaviour" for x in t)


def test_a_short_horizon_against_a_growth_goal_fires():
    t = book_spec.answer_tensions(answers(horizon="under_2y", purpose="growth"))
    assert any(x["id"] == "short_horizon_growth_goal" for x in t)


def test_a_consistent_set_of_answers_produces_no_tensions_at_all():
    assert book_spec.answer_tensions(
        answers(purpose="growth", horizon="over_10y", loss_limit="35",
                behaviour="hold")) == []


@pytest.mark.parametrize("t", book_spec.answer_tensions(
    answers(loss_limit="35", behaviour="sell_all", horizon="under_2y",
            purpose="growth")))
def test_every_tension_names_both_sides(t):
    assert t["said"].strip() and t["found"].strip() and t["text"].strip()
    assert t["severity"] in ("note", "warn")


# --------------------------------------------------------------------------
# Tensions between the answers and the measured book
# --------------------------------------------------------------------------

CONSISTENT = {"hhi": 0.05, "max_weight": 0.09, "beta": 0.55, "max_drawdown": -0.04}


def test_broad_exposure_against_a_concentrated_book_fires():
    t = book_spec.book_tensions(
        answers(concentration="broad"),
        book_spec.constraints(answers(concentration="broad")),
        {"hhi": 0.31, "max_weight": 0.42})
    hit = next(x for x in t if x["id"] == "diversified_but_concentrated")
    assert "42%" in hit["found"] and "0.31" in hit["found"]


def test_a_short_horizon_against_a_high_beta_book_fires():
    a = answers(horizon="under_2y")
    t = book_spec.book_tensions(a, book_spec.constraints(a), {"beta": 1.35})
    assert any(x["id"] == "short_horizon_high_beta" for x in t)


def test_a_loss_limit_against_what_the_book_actually_did_fires():
    a = answers(loss_limit="10")
    t = book_spec.book_tensions(a, book_spec.constraints(a), {"max_drawdown": -0.18})
    hit = next(x for x in t if x["id"] == "loss_limit_vs_history")
    assert "18%" in hit["found"]


def test_a_consistent_book_trips_nothing():
    a = answers(concentration="broad", horizon="over_10y", loss_limit="35")
    assert book_spec.book_tensions(a, book_spec.constraints(a), CONSISTENT) == []


@pytest.mark.parametrize("measured", [{}, {"hhi": None}, {"beta": float("nan")},
                                      {"max_drawdown": "n/a"}])
def test_missing_or_unusable_numbers_are_skipped_never_fabricated(measured):
    a = answers(concentration="broad", horizon="under_2y", loss_limit="5")
    out = book_spec.book_tensions(a, book_spec.constraints(a), measured)
    assert all(x["id"] != "loss_limit_vs_history" for x in out) or measured.get("max_drawdown")


def test_infeasible_answers_surface_as_a_tension_on_the_book():
    a = answers(experience="none", concentration="broad")
    t = book_spec.book_tensions(a, book_spec.constraints(a), CONSISTENT)
    assert any(x["id"] == "answers_cannot_all_be_met" for x in t)


def test_no_tension_ever_tells_the_reader_what_to_do():
    """Naming both sides is the contribution. Choosing would be advice."""
    a = answers(loss_limit="35", behaviour="sell_all", horizon="under_2y",
                purpose="growth", concentration="broad")
    every = (book_spec.answer_tensions(a)
             + book_spec.book_tensions(a, book_spec.constraints(a),
                                       {"hhi": 0.4, "max_weight": 0.5,
                                        "beta": 1.9, "max_drawdown": -0.5}))
    assert every, "expected this deliberately contradictory set to trip something"
    banned = ("you should", "we recommend", "you ought", "the right choice",
              "is suitable", "we suggest you", "better to buy", "you must sell")
    for x in every:
        blob = f"{x['said']} {x['found']} {x['text']}".lower()
        for phrase in banned:
            assert phrase not in blob, f"{x['id']} gives advice: {phrase!r}"


# --------------------------------------------------------------------------
# Prompt blocks
# --------------------------------------------------------------------------

def test_the_constraint_block_states_every_bound_the_model_must_meet():
    c = book_spec.constraints(answers(exclude_categories=["Energy"]))
    block = book_spec.describe_constraints(c)
    for token in ("beta", "holding", "Shares", "bonds or gold"):
        assert token in block
    assert "Energy" in block


def test_the_answer_block_reads_back_every_answer():
    a = complete(purpose="income", include_categories=["Bonds"])
    block = book_spec.describe_answers(a)
    assert "Steady income" in block and "Bonds" in block
    assert block.count("\n") + 1 >= len(book_spec.QUESTIONS)


def test_no_prompt_block_contains_a_brace():
    """Prompts are assembled with str.format; a stray brace raises."""
    c = book_spec.constraints(answers())
    for block in (book_spec.describe_constraints(c),
                  book_spec.describe_answers(answers())):
        assert "{" not in block and "}" not in block
