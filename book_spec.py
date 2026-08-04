"""book_spec.py — the investor questionnaire, the bounds it implies, and the
tensions between what someone said and what their book actually measures.

Pure: no Streamlit, no model, no market calls. `tabs/build.py` renders it and
`agents/book_builder.py` is constrained by it, but every number here is arrived
at by arithmetic, which is what makes the generated book checkable instead of
merely plausible.

WHERE THE QUESTIONS COME FROM
-----------------------------
Researched against the Grable & Lytton risk-tolerance scale, the FCA's FG11/05
(which reviewed eleven real risk-profiling tools and found NINE flawed), and
MiFID II's suitability taxonomy. The questions are DATA, and each option carries
the bound it implies, so the mapping from answer to portfolio property is a table
you can read rather than a chain of ifs you have to trace.

Three things are deliberately absent, each for a reason FG11/05 gives:

  * No 1-10 risk slider. The risk each number stands for is undefined, so the
    user and the system do not share a meaning for the answer.
  * No neutral rung on the two risk items. A non-answer scored as a mid-range
    attitude manufactures a moderate investor who does not exist.
  * No income, net worth or dependants. Those are real capacity questions, but
    this drafts a DEMONSTRATION book; asking them would imply a suitability
    assessment that is explicitly not being made.

ONE RESEARCH CORRECTION WORTH KEEPING
-------------------------------------
The folk premise "people overstate their risk tolerance in a bull market" is not
what the evidence says. FinaMetrica's panel of 341,782 responses across 2007-2012
found measured TOLERANCE barely moved (SD 1.86% against the S&P's 17.27%); what
moves is risk PERCEPTION. So this does not try to correct for a drifting trait.
It anchors the risk questions in concrete money-and-percent magnitudes, so
perception has less room to move the answer in the first place.

HOW THE BOUNDS COMBINE
----------------------
By INTERSECTION, and that is not an implementation detail — it IS the rule that
resolves stated tolerance against stated behaviour. Q3 ("how far down could it
go") and Q4 ("what would you actually do") both write `beta_max`; taking the
tighter of the two is exactly "resolve toward the more risk-averse answer". It
falls out of the merge rather than needing a special case.
"""

from __future__ import annotations

import math

import shelf

# --------------------------------------------------------------------------
# Bound vocabulary
# --------------------------------------------------------------------------
# Every bound is one of three shapes, and each has ONE merge rule:
#   band  (lo, hi)  -> intersect: (max of los, min of his)
#   cap   float     -> the smallest wins
#   floor float     -> the largest wins
_BANDS = ("equity_weight", "cash_weight", "holdings")
_CAPS = ("beta_max", "single_stock_max", "position_max", "hhi_max")
_FLOORS = ("defensive_floor",)

# Applied when a question does not speak to a bound at all.
_DEFAULTS = {
    "equity_weight": (0.0, 1.0),
    "cash_weight": (0.0, 0.30),
    "holdings": (4, 20),
    "beta_max": 2.0,
    "single_stock_max": 1.0,
    "position_max": 1.0,
    "hhi_max": 1.0,
    "defensive_floor": 0.0,
}


QUESTIONS = (
    {
        "id": "purpose",
        "prompt": "What is this money for?",
        "help": "Sets roughly how much of the book is in shares at all.",
        "options": (
            {"key": "learning", "label": "Learning how these tools work",
             "bounds": {"equity_weight": (0.40, 0.80)}},
            {"key": "growth", "label": "Long-term growth",
             "bounds": {"equity_weight": (0.75, 0.95)}},
            {"key": "income", "label": "Steady income",
             "bounds": {"equity_weight": (0.45, 0.70)}},
            {"key": "preservation", "label": "Protecting what I have",
             "bounds": {"equity_weight": (0.20, 0.45), "beta_max": 0.75}},
        ),
    },
    {
        "id": "horizon",
        # Single-barrelled on purpose. FG11/05 calls out "when do you need the
        # money back OR start drawing income" as two questions wearing one
        # answer box.
        "prompt": "If you had to, how long could you leave this money alone?",
        "help": "Capacity, not appetite — how long the money can be left, not "
                "how bold you feel.",
        # Each of these sets an equity CEILING as well as a defensive floor.
        # With a floor alone the horizon was frequently inert: an income
        # investor sits around 57% equity, which already clears every floor, so
        # answering "under two years" versus "more than ten" produced the exact
        # same book. A floor is a minimum, and a minimum that is already met
        # changes nothing. The ceiling is also the more honest model — nobody
        # holds 90% shares against money they need in eighteen months.
        "options": (
            {"key": "under_2y", "label": "Under 2 years",
             "bounds": {"defensive_floor": 0.40, "beta_max": 0.70,
                        "equity_weight": (0.0, 0.55)}},
            {"key": "2_5y", "label": "2 to 5 years",
             "bounds": {"defensive_floor": 0.25, "beta_max": 1.00,
                        "equity_weight": (0.0, 0.75)}},
            {"key": "5_10y", "label": "5 to 10 years",
             "bounds": {"defensive_floor": 0.10,
                        "equity_weight": (0.0, 0.90)}},
            {"key": "over_10y", "label": "More than 10 years",
             "bounds": {"defensive_floor": 0.00}},
        ),
    },
    {
        "id": "loss_limit",
        # Anchored in BOTH money and percent. Gain- and loss-framed versions of
        # the same gamble reliably flip the same person's answer; concrete
        # magnitudes leave framing less room to work.
        "prompt": "Say you put in $10,000 and four months later it is worth "
                  "$7,000. How far down could it go before you could no longer "
                  "leave it alone?",
        "help": "The highest-signal question here. No middle option, "
                "deliberately.",
        "options": (
            {"key": "5", "label": "$500 — about 5%",
             "bounds": {"beta_max": 0.40, "defensive_floor": 0.45}},
            {"key": "10", "label": "$1,000 — about 10%",
             "bounds": {"beta_max": 0.60, "defensive_floor": 0.30}},
            {"key": "20", "label": "$2,000 — about 20%",
             "bounds": {"beta_max": 0.90}},
            {"key": "35", "label": "$3,500 — about 35%",
             "bounds": {"beta_max": 1.20}},
            {"key": "none", "label": "No fixed limit",
             "bounds": {"beta_max": 1.50}},
        ),
    },
    {
        "id": "behaviour",
        # Behaviour, not feeling — and paired with loss_limit so the two can
        # DISAGREE. That disagreement is the tension worth surfacing, and the
        # intersection resolves it toward the more cautious answer by itself.
        "prompt": "In that situation, what would you actually do?",
        "help": "Paired with the question above on purpose. If the two "
                "disagree, the more cautious one is used.",
        "options": (
            {"key": "sell_all", "label": "Sell everything",
             "bounds": {"beta_max": 0.50}},
            {"key": "sell_some", "label": "Sell some of it",
             "bounds": {"beta_max": 0.80}},
            {"key": "hold", "label": "Do nothing", "bounds": {}},
            {"key": "buy_more", "label": "Buy more", "bounds": {}},
        ),
    },
    {
        "id": "experience",
        "prompt": "How much investing have you done?",
        "help": "Decides whether individual company shares belong in the book "
                "at all, and how many holdings it runs.",
        "options": (
            {"key": "none", "label": "None",
             "bounds": {"single_stock_max": 0.00, "holdings": (4, 7)}},
            {"key": "fund", "label": "A savings account, or a fund someone set up",
             "bounds": {"single_stock_max": 0.25, "holdings": (5, 9)}},
            {"key": "etfs", "label": "I have picked funds or ETFs myself",
             "bounds": {"single_stock_max": 0.55, "holdings": (6, 12)}},
            {"key": "stocks", "label": "I have picked individual shares myself",
             "bounds": {"single_stock_max": 1.00, "holdings": (6, 14)}},
        ),
    },
    {
        "id": "concentration",
        "prompt": "Which book would you rather look at?",
        "help": "Independent of how much volatility you can take — some people "
                "want a few names they can follow, at any risk level.",
        "options": (
            {"key": "handful", "label": "A handful of companies I could name and follow",
             "bounds": {"hhi_max": 0.30, "position_max": 0.25, "holdings": (4, 8)}},
            {"key": "middle", "label": "Somewhere in the middle",
             "bounds": {"hhi_max": 0.15, "position_max": 0.15}},
            {"key": "broad", "label": "Broad exposure, where no single name matters much",
             "bounds": {"hhi_max": 0.08, "position_max": 0.10}},
        ),
    },
)

# Question 7 is not a radio, so it is described separately.
CATEGORY_QUESTION = {
    "id": "categories",
    "prompt": "Anything you would like in — or definitely out?",
    "help": "Leave empty for no preference. Anything you exclude will be at "
            "zero, not merely underweight.",
}

FREE_TEXT = {
    "id": "free_text",
    "prompt": "In a sentence or two, describe yourself as an investor.",
    "max_chars": 300,
}

QUESTION_IDS = tuple(q["id"] for q in QUESTIONS)


def default_answers() -> dict:
    """NOTHING pre-selected. Only the two category lists, which may stay empty.

    This deliberately does not seed each question with its first option. Two
    reasons, and the second is the one that bites:

      * The no-neutral-rung rule exists so that a non-answer cannot be scored as
        an attitude. Pre-selecting scores one anyway — it just picks the
        attitude for you, silently.
      * First-of-each is not a neutral investor, it is an incoherent one. Here
        it produced somebody who wants to preserve capital over under two years
        with a 5% loss limit AND would sell everything — a set whose merged
        bounds are so tight that changing `horizon` afterwards moved nothing at
        all. A test asserting each question actually affects the outcome caught
        it; a starting screen would have shipped it.

    `constraints({})` is well-defined and feasible, so the builder can preview
    an unanswered form without special-casing it.
    """
    return {"include_categories": [], "exclude_categories": []}


def question(qid: str) -> dict | None:
    return next((q for q in QUESTIONS if q["id"] == qid), None)


def option(qid: str, key: str) -> dict | None:
    q = question(qid)
    if not q:
        return None
    return next((o for o in q["options"] if o["key"] == key), None)


def label_for(qid: str, key: str) -> str:
    o = option(qid, key)
    return o["label"] if o else str(key)


def is_complete(answers: dict) -> bool:
    """Every radio answered. The category picker and free text may be empty."""
    return all(option(qid, (answers or {}).get(qid)) is not None
               for qid in QUESTION_IDS)


def missing(answers: dict) -> list:
    return [qid for qid in QUESTION_IDS
            if option(qid, (answers or {}).get(qid)) is None]


# --------------------------------------------------------------------------
# Bounds
# --------------------------------------------------------------------------

def constraints(answers: dict) -> dict:
    """Merge every selected option's bounds by intersection.

    An empty band (lo > hi) is NOT an error. It means the answers cannot all be
    satisfied at once — which is a tension to show the reader, not a crash. The
    band is left inverted and its name recorded in `infeasible`, so the caller
    can both see it and still generate something.
    """
    answers = answers or {}
    out = dict(_DEFAULTS)

    for qid in QUESTION_IDS:
        opt = option(qid, answers.get(qid))
        if not opt:
            continue
        for name, value in opt["bounds"].items():
            if name in _BANDS:
                lo, hi = out[name]
                nlo, nhi = value
                out[name] = (max(lo, nlo), min(hi, nhi))
            elif name in _CAPS:
                out[name] = min(out[name], value)
            elif name in _FLOORS:
                out[name] = max(out[name], value)

    include = [c for c in (answers.get("include_categories") or [])
               if c in shelf.CATEGORIES]
    exclude = [c for c in (answers.get("exclude_categories") or [])
               if c in shelf.CATEGORIES]
    # An explicit exclusion beats an inclusion: saying "definitely not energy"
    # is a stronger statement than ticking it in a list of things you like.
    include = [c for c in include if c not in exclude]

    # INCLUSION IS A TILT, NOT A WHITELIST — only exclusions narrow the shelf.
    #
    # This used to read `include or shelf.CATEGORIES`, so ticking one box in a
    # control labelled "Would like included" (help text: "Leave empty for no
    # preference") silently collapsed 41 tickers to six. That is not what the
    # label promises, and it contradicts this module's own rule that an
    # inclusion is the WEAKER signal — a whitelist is the strongest constraint
    # available.
    #
    # It was also the root cause of the worst behaviour in the generator: with
    # the shelf cut to one category there was frequently nothing left to satisfy
    # the position cap, the defensive floor or the single-share cap with, so a
    # reader two clicks in could be handed a book that was 100% one company.
    # Ticking "Technology" now means "lean this way", which is what it says.
    allowed_categories = [c for c in shelf.CATEGORIES if c not in exclude]
    out["include_categories"] = tuple(include)
    out["excluded_categories"] = tuple(exclude)
    out["allowed_categories"] = tuple(allowed_categories)
    # NOT shelf.in_categories(), which reads an empty list as "no filter, so
    # everything". Here an empty list means the reader excluded every category
    # in turn, and answering "then you may hold anything" would be the exact
    # opposite of what they said. Filtered directly so empty means empty.
    _allowed_set = set(allowed_categories)
    out["allowed"] = tuple(t for t in shelf.tickers()
                           if shelf.category_of(t) in _allowed_set)

    # An equity CEILING implies a floor on everything that is not equity, and
    # deriving it once here means the allocator, the coercion step and the
    # prompt all read one number rather than three places each remembering to
    # do the subtraction. Without it, "shares: 75% to 95%" was stated to the
    # model and then never enforced — a live draft came back 100% equity and
    # nothing caught it, because `defensive_floor` for that horizon was zero.
    eq_hi = out["equity_weight"][1]
    if eq_hi < 1.0:
        out["defensive_floor"] = max(out["defensive_floor"], 1.0 - eq_hi)

    # A defensive floor is unreachable if every defensive category is excluded.
    if out["defensive_floor"] > 0 and not any(
            shelf.role_of(t) in shelf.DEFENSIVE_ROLES for t in out["allowed"]):
        out["defensive_floor"] = 0.0

    out["infeasible"] = tuple(_infeasible(out))
    return out


def _infeasible(c: dict) -> list:
    """Names of bounds that cannot all hold at once."""
    bad = []
    for name in _BANDS:
        lo, hi = c[name]
        if lo > hi:
            bad.append(name)
    # Equity + the defensive floor cannot both be satisfied above 100%.
    if c["equity_weight"][0] + c["defensive_floor"] > 1.0 + 1e-9:
        bad.append("equity_weight_vs_defensive_floor")
    # A position cap of 10% needs at least 10 holdings to reach 100% — and they
    # have to actually EXIST. Checking only the holdings ceiling missed the case
    # where the reader narrowed the shelf to six names and then asked that none
    # exceed 15%: the band was satisfiable, the shelf was not.
    if c["position_max"] > 0:
        need = math.ceil(1.0 / c["position_max"] - 1e-9)
        available = min(c["holdings"][1], len(c["allowed"]))
        if need > available:
            bad.append("position_max_vs_holdings")
    if not c["allowed"]:
        bad.append("allowed")
    return bad


def describe_constraints(c: dict) -> str:
    """The bounds as the generator is told them. Percent, because the model
    returns percent and a mixed-unit prompt invites a mixed-unit answer."""
    eq_lo, eq_hi = c["equity_weight"]
    h_lo, h_hi = c["holdings"]
    # An inverted band is a real outcome (240 of 3840 answer sets produce one),
    # and printing it verbatim told the model "between 75% and 55%" — a bound
    # that cannot be read, let alone met. Collapse it to the cautious end, which
    # is the same direction every other merge in this module resolves toward.
    if eq_lo > eq_hi:
        eq_lo = eq_hi
    if h_lo > h_hi:
        h_lo = h_hi
    lines = [
        f"Shares (including share funds): between {eq_lo * 100:.0f}% and "
        f"{eq_hi * 100:.0f}% of the invested total.",
        f"At least {c['defensive_floor'] * 100:.0f}% in bonds or gold.",
        f"Portfolio beta must not exceed {c['beta_max']:.2f}.",
        f"Individual company shares: at most {c['single_stock_max'] * 100:.0f}% "
        f"of the invested total.",
        f"No single holding above {c['position_max'] * 100:.0f}%.",
        f"Between {h_lo} and {h_hi} holdings.",
    ]
    # Spell the arithmetic out. Told only "at most 15% each" and "4 to 7
    # holdings", a live draft came back with five holdings — which cannot sum
    # to 100 with none above 15% — and one of them at 45%.
    if c["position_max"] > 0:
        need = math.ceil(1.0 / c["position_max"] - 1e-9)
        if need > 1:
            lines.append(
                f"Note that keeping every holding under "
                f"{c['position_max'] * 100:.0f}% takes at least {need} of them, "
                f"so use at least that many.")
    if c["excluded_categories"]:
        lines.append("Must hold NOTHING from: " + ", ".join(c["excluded_categories"]) + ".")
    if c["include_categories"]:
        lines.append("The reader asked for: " + ", ".join(c["include_categories"]) + ".")
    return "\n".join(f"- {line}" for line in lines)


def describe_answers(answers: dict) -> str:
    """The answers as prose, for the prompt and for the PDF."""
    answers = answers or {}
    lines = []
    for q in QUESTIONS:
        opt = option(q["id"], answers.get(q["id"]))
        if opt:
            lines.append(f"- {q['prompt']} {opt['label']}")
    inc = answers.get("include_categories") or []
    exc = answers.get("exclude_categories") or []
    if inc:
        lines.append("- Would like included: " + ", ".join(inc))
    if exc:
        lines.append("- Wants excluded: " + ", ".join(exc))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Tensions
# --------------------------------------------------------------------------

def _pct(x) -> str:
    return f"{x * 100:.0f}%"


def answer_tensions(answers: dict) -> list:
    """Tensions visible in the ANSWERS ALONE — no book needed.

    Cheapest and most useful, because these can be shown while the reader is
    still on the form and can still change their mind.
    """
    answers = answers or {}
    out = []

    loss = answers.get("loss_limit")
    behaviour = answers.get("behaviour")
    if loss in ("20", "35", "none") and behaviour in ("sell_all", "sell_some"):
        out.append({
            "id": "tolerance_vs_behaviour",
            "severity": "note",
            "said": f"“{label_for('loss_limit', loss)}” and "
                    f"“{label_for('behaviour', behaviour)}”",
            "found": "these two point opposite ways",
            "text": "You said you could ride out a large fall, and also that you "
                    "would sell into it. Those are different answers, and the "
                    "second is the one that happens. The book below is built to "
                    "the more cautious of the two.",
        })

    horizon = answers.get("horizon")
    purpose = answers.get("purpose")
    if horizon == "under_2y" and purpose == "growth":
        out.append({
            "id": "short_horizon_growth_goal",
            "severity": "note",
            "said": "under two years, and long-term growth",
            "found": "the horizon is shorter than the goal",
            "text": "Long-term growth is usually measured over years, not "
                    "months. Over under two years the market has plenty of time "
                    "to be down and none to recover.",
        })

    if loss in ("5", "10") and purpose == "growth":
        out.append({
            "id": "loss_limit_vs_objective",
            "severity": "note",
            "said": f"“{label_for('loss_limit', loss)}” and “long-term growth”",
            "found": "growth books have historically fallen further than that",
            "text": "A book aimed at growth has usually spent some part of its "
                    "life further down than the limit you set. That is not a "
                    "reason to change either answer — it is worth knowing which "
                    "one you would abandon first.",
        })
    return out


def book_tensions(answers: dict, constraints_: dict, measured: dict) -> list:
    """Tensions between what was SAID and what the drafted book MEASURES.

    `measured` carries numbers computed by `portfolio_metrics` — hhi, beta,
    max_weight, max_drawdown — so every one of these is arithmetic the reader
    could check, not an opinion the model formed about its own output. Any
    missing key is simply skipped; nothing here fabricates a number.

    Never says which way to resolve a tension. Naming both sides is the whole
    contribution; choosing for the reader would be advice.
    """
    answers = answers or {}
    measured = measured or {}
    # Filled in rather than indexed: the rest of this function reads bounds
    # directly, and a partial dict from a caller (or from stored state written by
    # an older version) would raise KeyError out of a render.
    constraints_ = {**_DEFAULTS, **{"infeasible": ()}, **(constraints_ or {})}
    out = []

    def num(key):
        v = measured.get(key)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    # Fires for ANY concentration answer, not only "broad". Scoping it to
    # "broad" meant a reader who asked for the middle option and received a book
    # with 45% in one holding — against the 15% their answer implied — was told
    # nothing at all. The answer is named in `said`, so the wording stays true
    # whichever option was picked.
    hhi = num("hhi")
    max_weight = num("max_weight")
    concentration = answers.get("concentration")
    if concentration and (
            (hhi is not None and hhi > constraints_["hhi_max"]) or
            (max_weight is not None and max_weight > constraints_["position_max"])):
        found = []
        if max_weight is not None:
            found.append(f"its largest holding is {_pct(max_weight)}")
        if hhi is not None:
            found.append(f"its concentration score is {hhi:.2f}")
        out.append({
            "id": "diversified_but_concentrated",
            "severity": "warn",
            "said": f"“{label_for('concentration', concentration)}”, which "
                    f"implies no holding above {_pct(constraints_['position_max'])}",
            "found": " and ".join(found),
            "text": "This book leans harder on one holding than that answer "
                    "suggests. Spreading it out means owning more names you did "
                    "not choose individually.",
        })

    beta = num("beta")
    if beta is not None and answers.get("horizon") in ("under_2y", "2_5y") \
            and beta > constraints_["beta_max"] + 1e-9:
        out.append({
            "id": "short_horizon_high_beta",
            "severity": "warn",
            "said": f"“{label_for('horizon', answers['horizon'])}”",
            "found": f"this book's beta is {beta:.2f}, above the {constraints_['beta_max']:.2f} "
                     f"that horizon implies",
            "text": "Beta near 1 moves about as much as the whole market; above "
                    "it, more. Over a short horizon there is less time for a "
                    "bad stretch to come back.",
        })

    dd = num("max_drawdown")
    loss = answers.get("loss_limit")
    limits = {"5": 0.05, "10": 0.10, "20": 0.20, "35": 0.35}
    if dd is not None and loss in limits and abs(dd) > limits[loss] + 1e-9:
        out.append({
            "id": "loss_limit_vs_history",
            "severity": "warn",
            "said": f"you would stop at about {_pct(limits[loss])}",
            "found": f"this book's worst stretch in the last year was "
                     f"{_pct(abs(dd))}",
            "text": "That is what this book actually did over the recorded year, "
                    "not a forecast. It has already been further down than the "
                    "limit you set.",
        })

    if constraints_.get("infeasible"):
        out.append({
            "id": "answers_cannot_all_be_met",
            "severity": "note",
            "said": "your answers, taken together",
            "found": "they cannot all be satisfied at once",
            "text": "Some of what you asked for rules out the rest — for "
                    "instance a very low limit on any single holding needs more "
                    "holdings than you asked for. The book below meets as much "
                    "of it as it can.",
        })
    return out
