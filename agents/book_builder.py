"""
agents/book_builder.py — draft an EXAMPLE book from an investor questionnaire.
==============================================================================
Third shape of AI in this app, alongside the fixed five-call debate chain and
the tool-using analyst. Here a model is given a curated shelf and a set of hard
numeric bounds derived from what the reader said, and asked to arrange one
against the other.

WHAT THE MODEL IS TRUSTED WITH, AND WHAT IT IS NOT
--------------------------------------------------
It returns WEIGHTS and prose. It never returns shares, dollars, prices or a cost
basis — and it is not merely asked not to, it is not given prices in the first
place, so it has nothing to compute one from. `portfolio.from_weights` derives
shares from the real settled close.

This is the single most important line in the feature. "Invested" on screen is
`shares x cost per share`. If a model had authored the share count it would have
had to invent a price, and that column — sitting directly beneath a computed book
total — would be fiction wearing the same typeface as arithmetic.

`_coerce` then normalises rather than trusts, in the manner of
`explainer._coerce`: off-shelf tickers dropped, excluded categories forced to
zero, duplicates merged, weights renormalised. The model will return sums of 99.7
and 101.3; that is not a failure, it is what models do with percentages.

WHY THE MOCK PATH IS AN ALLOCATOR AND NOT A RECORDED FILE
----------------------------------------------------------
`mock_debate.json` is a fixture because a debate is PROSE about one ticker: five
turns of grounded argument cannot be synthesised in Python, and its
NVDA-specificity is declared honestly through `recorded_for`.

An example book is the opposite. It is a FUNCTION OF THE ANSWERS. A single
recorded file would hand back the same book to somebody preserving capital over
two years as to somebody chasing growth over twenty — which makes the
questionnaire visibly inert, in exactly the mode the deployed app and the entire
test suite run in. That is a worse failure than a duller book.

So the offline path is a small deterministic allocator that reads the same
bounds. It earns its keep twice: it is also the repair fallback when a live
response cannot be rescued, and it gives the tests a free oracle — the same
bound assertions run against the mock book and, under --llm, against the real one.

Public API:
    def draft_example_book(answers, free_text, investable, *, prices) -> dict
"""

from __future__ import annotations

import math
import os

import book_spec
import shelf
from agents import llm

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                            "prompts", "book_builder.txt")

# Clip-and-renormalise can chase its own tail when a cap is arithmetically
# unreachable (a 10% cap over 5 holdings can never sum to 100). Bounded, and the
# fact recorded, rather than looped.
_MAX_CLIP_PASSES = 3

DEFAULT_EMOJI = "🧭"


def _load_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------

def draft_example_book(answers: dict, free_text: str, investable: float,
                       *, prices: dict | None = None) -> dict:
    """Draft an example book. Returns weights and prose — never Contract A.

    The caller passes `allocation` through `portfolio.from_weights`, so a
    generated book enters session state through the same validator as an
    uploaded CSV and a hand-typed table.

    Keys: name, emoji, tagline, notice, allocation[{ticker, weight_pct, why}],
    cash_pct, generated_by, is_mock, constraints_applied[].

    `allocation` weights are a share of the INVESTED money and sum to 100.
    `cash_pct` is a share of the whole book and sits outside them, so the caller
    invests `investable * (1 - cash_pct/100)` and holds the rest as cash.
    """
    constraints = book_spec.constraints(answers)
    free_text = (free_text or "").strip()

    if llm.use_mock():
        return _rule_based(answers, constraints, reason="no_api_key")

    prompt = _load_prompt().format(
        shelf_block=shelf.describe_for_prompt(constraints["allowed"]),
        answers_block=book_spec.describe_answers(answers),
        free_text=free_text or "(they did not add anything)",
        constraints_block=book_spec.describe_constraints(constraints),
        investable=f"${float(investable or 0):,.0f}",
    )
    system = (
        "You arrange a DEMONSTRATION portfolio from a fixed shelf so a learner "
        "has a book of their own to explore an analysis app with. You are not "
        "advising anyone and never describe the result as suitable, recommended "
        "or right for the reader. You return percentage weights only — never "
        "shares, dollars or prices, which you have not been given. Respond with "
        "JSON only."
    )

    try:
        # 4096, matching llm.call_json's own default rather than trimming it.
        # The prompt carries the whole shelf plus every bound, and a reply that
        # runs out of room mid-object parses as nothing at all.
        # 8000, for the reason agents/analyst.py uses 8000: max_tokens caps
        # THINKING AND TEXT TOGETHER, so reasoning eats the budget and the reply
        # is cut off mid-object. Diagnosed rather than guessed — a truncated
        # draft came back at 1571 characters ending in
        # `"why": "brings in smaller US companies to wid`, which parses as
        # nothing and dropped the whole book to the rule allocator. At 2500 and
        # again at 4096 roughly one live call in three was lost this way; a book
        # for a "broad exposure" reader is thirteen holdings each carrying a
        # reason, which is simply a long reply.
        #
        # retries=2 rather than call_json's default 1 for the same reason: a
        # fallback throws away the model's judgement over a formatting slip.
        raw = llm.call_json(system, prompt, max_tokens=8000, retries=2)
    except Exception:  # noqa: BLE001 — a dead model must not dead-end the builder
        return _rule_based(answers, constraints, reason="model_unavailable")

    book = _coerce(raw, constraints)
    if not book["allocation"]:
        # Nothing survived coercion — every ticker off-shelf, or the shape was
        # wrong. Fall back rather than hand the builder an empty table.
        fallback = _rule_based(answers, constraints, reason="model_output_unusable")
        fallback["constraints_applied"] = (
            list(book["constraints_applied"]) + fallback["constraints_applied"])
        return fallback
    return book


# --------------------------------------------------------------------------
# Coercion — normalise, never trust
# --------------------------------------------------------------------------

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clean_text(v, fallback: str = "") -> str:
    if v is None:
        return fallback
    s = str(v).strip()
    return s or fallback


def _coerce(raw: dict, constraints: dict) -> dict:
    """Take whatever came back and make it satisfy the bounds, or say it could not."""
    raw = raw if isinstance(raw, dict) else {}
    applied: list[str] = []

    allowed = set(constraints["allowed"])
    merged: dict[str, dict] = {}

    entries = raw.get("allocation")
    if not isinstance(entries, list):
        entries = []
        applied.append("no allocation list returned")

    for item in entries:
        if not isinstance(item, dict):
            continue
        tk = _clean_text(item.get("ticker")).upper()
        if not tk:
            continue
        if tk not in allowed:
            # Covers both an invented ticker and one from an excluded category.
            applied.append(f"dropped {tk}, not available here")
            continue
        w = _num(item.get("weight_pct"))
        if w is None or w <= 0:
            applied.append(f"dropped {tk}, no usable weight")
            continue
        if tk in merged:
            merged[tk]["weight_pct"] += w
            applied.append(f"merged a duplicate {tk}")
        else:
            merged[tk] = {"ticker": tk, "weight_pct": w,
                          "why": _clean_text(item.get("why"))}

    cash_pct = _num(raw.get("cash_pct"))
    lo, hi = constraints["cash_weight"]
    if cash_pct is None:
        cash_pct = lo * 100.0
    cash_pct = min(max(cash_pct, lo * 100.0), hi * 100.0)

    # WEIGHTS ARE A SHARE OF THE INVESTED MONEY, SUMMING TO 100 — cash sits
    # outside them. This is not a presentational choice: `portfolio_metrics`
    # computes every weight with cash EXCLUDED (finance assumption 1), so a
    # generator that capped a holding at 15% of the whole book while holding 15%
    # cash produced a holding the dashboard then printed as 17.65%. Worse, the
    # tension rules compare that same cash-excluded figure against
    # `position_max`, so the app flagged a tension against a book it had just
    # generated itself. One unit, everywhere.
    alloc = _trim_holdings(list(merged.values()), constraints)
    alloc = _settle(alloc, constraints, applied)
    alloc.sort(key=lambda a: -a["weight_pct"])

    return {
        "name": _clean_text(raw.get("name"), "Your example book"),
        "emoji": _emoji(raw.get("emoji")),
        "tagline": _clean_text(raw.get("tagline")),
        "notice": _clean_text(raw.get("notice")),
        "cash_pct": round(cash_pct, 2),
        "allocation": alloc,
        "generated_by": "model",
        "is_mock": False,
        "constraints_applied": applied,
    }


def _emoji(v) -> str:
    s = _clean_text(v)
    # One grapheme, and not ASCII — a model that returns ":chart:" or a word
    # would otherwise put that literal string into the book's name.
    if len(s) == 1 and not s.isascii():
        return s
    if 1 < len(s) <= 3 and not s.isascii():
        return s
    return DEFAULT_EMOJI


def _normalise(alloc: list, target: float) -> list:
    """Scale weights to sum to `target`. Never trust the model's arithmetic."""
    total = sum(a["weight_pct"] for a in alloc)
    if total <= 0 or not alloc:
        return alloc
    factor = target / total
    for a in alloc:
        a["weight_pct"] = a["weight_pct"] * factor
    return alloc


def _trim_holdings(alloc: list, constraints: dict) -> list:
    """Trim to the holdings ceiling. NEVER invents holdings to reach the floor.

    Every position carries a `why` pointing at something the reader said, and a
    ticker added here to satisfy an arithmetic floor would have nothing honest
    to put there. Being under the floor is reported by `_settle` instead.
    """
    _, hi = constraints["holdings"]
    if hi and len(alloc) > hi:
        alloc = sorted(alloc, key=lambda a: -a["weight_pct"])[:hi]
    return alloc


def _clip_positions(alloc: list, constraints: dict) -> list:
    """Pull anything over the position cap down, and redistribute the spare.

    When the cap is arithmetically unreachable — a 15% cap cannot hold over five
    holdings summing to 100 — spread evenly, which is the allocation that
    minimises the largest holding and so the closest thing to the cap that
    exists.
    """
    cap = constraints["position_max"] * 100.0
    if cap <= 0 or not alloc:
        return alloc
    if len(alloc) * cap < 100.0 - 1e-6:
        even = 100.0 / len(alloc)
        for a in alloc:
            a["weight_pct"] = even
        return alloc

    for _ in range(_MAX_CLIP_PASSES):
        over = [a for a in alloc if a["weight_pct"] > cap + 1e-9]
        if not over:
            break
        spare = sum(a["weight_pct"] - cap for a in over)
        for a in over:
            a["weight_pct"] = cap
        room = [a for a in alloc if a["weight_pct"] < cap - 1e-9]
        headroom = sum(cap - a["weight_pct"] for a in room)
        if headroom <= 0:
            break
        for a in room:
            a["weight_pct"] += spare * (cap - a["weight_pct"]) / headroom
    return alloc


def _shift_between(alloc: list, pick, target_pct: float) -> list:
    """Move weight until the `pick` group holds exactly `target_pct` of 100.

    Scales the group up (or down) and the remainder the opposite way. Does
    nothing when either side is empty — there is nothing to move it between.
    """
    group = [a for a in alloc if pick(a["ticker"])]
    rest = [a for a in alloc if not pick(a["ticker"])]
    if not group or not rest:
        return alloc
    have = sum(a["weight_pct"] for a in group)
    other = sum(a["weight_pct"] for a in rest)
    if have <= 0 or other <= 0:
        return alloc
    for a in group:
        a["weight_pct"] *= target_pct / have
    for a in rest:
        a["weight_pct"] *= (100.0 - target_pct) / other
    return alloc


def _raise_defensive(alloc: list, constraints: dict) -> list:
    floor = constraints["defensive_floor"] * 100.0
    if floor <= 0:
        return alloc
    have = sum(a["weight_pct"] for a in alloc
               if shelf.role_of(a["ticker"]) in shelf.DEFENSIVE_ROLES)
    if have >= floor - 1e-9:
        return alloc
    return _shift_between(
        alloc, lambda t: shelf.role_of(t) in shelf.DEFENSIVE_ROLES, floor)


def _cap_single_stocks(alloc: list, constraints: dict) -> list:
    cap = constraints["single_stock_max"] * 100.0
    if cap >= 100.0:
        return alloc
    have = sum(a["weight_pct"] for a in alloc if shelf.is_single_stock(a["ticker"]))
    if have <= cap + 1e-9:
        return alloc
    if cap <= 0:
        # Nothing may be held in individual company shares at all. Dropping them
        # is the only way to honour that, and it is what the answer asked for.
        keep = [a for a in alloc if not shelf.is_single_stock(a["ticker"])]
        return keep if keep else alloc
    return _shift_between(alloc, shelf.is_single_stock, cap)


def _settle(alloc: list, constraints: dict, applied: list) -> list:
    """Adjust until the bounds hold, then SAY WHAT IS ACTUALLY TRUE.

    The previous shape was a chain of one-shot fixups, each of which appended a
    message and then had its work undone by the next one. Two of those messages
    were app-authored claims about arithmetic that had not happened:

      * "reduced the single-share portion to what your experience answer allows"
        sat over a book that was 100% one company share, because the rescale was
        immediately followed by a renormalise that scaled it straight back.
      * "raised bonds and gold to the N% your answers imply" sat over a book at
        a third of that, because the floor step ended by calling the position
        cap, which clipped what it had just raised.

    This codebase draws a hard line between a claim the tests enforce and prose
    nobody checked; those two put unchecked claims on the checked side of it.

    So: adjust in a loop, because the constraints genuinely interact, and then
    MEASURE THE FINAL BOOK and report only the bounds it misses. Nothing is
    announced as done. What could not be done is named.
    """
    if not alloc:
        return alloc
    for _ in range(4):
        alloc = _normalise(alloc, 100.0)
        alloc = _clip_positions(alloc, constraints)
        alloc = _raise_defensive(alloc, constraints)
        alloc = _cap_single_stocks(alloc, constraints)
    alloc = _normalise(alloc, 100.0)

    w = {a["ticker"]: a["weight_pct"] for a in alloc}
    biggest = max(w.values()) if w else 0.0
    defensive = sum(v for t, v in w.items()
                    if shelf.role_of(t) in shelf.DEFENSIVE_ROLES)
    stocks = sum(v for t, v in w.items() if shelf.is_single_stock(t))
    lo, _ = constraints["holdings"]

    if biggest > constraints["position_max"] * 100.0 + 0.01:
        applied.append(
            f"could not keep every holding under "
            f"{constraints['position_max'] * 100:.0f}% with only {len(w)} of "
            f"them — the largest is {biggest:.0f}%")
    if defensive < constraints["defensive_floor"] * 100.0 - 0.01:
        applied.append(
            f"wanted {constraints['defensive_floor'] * 100:.0f}% in bonds or "
            f"gold and could only reach {defensive:.0f}%")
    if stocks > constraints["single_stock_max"] * 100.0 + 0.01:
        applied.append(
            f"individual company shares are {stocks:.0f}% of this book, above "
            f"the {constraints['single_stock_max'] * 100:.0f}% your experience "
            f"answer implies")
    if lo and len(w) < lo:
        applied.append(
            f"only {len(w)} holdings, fewer than the {lo} your answers imply")
    return alloc


# --------------------------------------------------------------------------
# The rule-based allocator — offline path AND repair fallback
# --------------------------------------------------------------------------

# These say WHY, never WHO — the render site already names the allocator, and
# repeating it produced "Drafted by a rule-based allocator. Drafted by a
# rule-based allocator rather than by the model, because...".
_REASON_TEXT = {
    "no_api_key": "No API key is configured. The allocation still follows every "
                  "answer you gave.",
    # Covers BOTH a dead connection and a reply that carried no JSON at all —
    # measured, the latter happens intermittently, and `call_json` raises the
    # same way for both. Saying "could not be reached" would have been a guess,
    # and a wrong one whenever the model answered and simply answered in prose.
    "model_unavailable": "The model did not return a usable draft. The "
                         "allocation follows every answer you gave.",
    "model_output_unusable": "The model's draft could not be used. This "
                             "allocation follows every answer you gave.",
}


def _rule_based(answers: dict, constraints: dict, *, reason: str) -> dict:
    """A deterministic book that satisfies the same bounds the model is given.

    Roughly: hit the middle of the equity band, honour the defensive floor with
    bonds and gold, spread within each role across whatever the reader allowed,
    and keep every holding under the position cap.
    """
    allowed = list(constraints["allowed"])
    applied: list[str] = []

    equity = [t for t in allowed if shelf.role_of(t) == "equity"]
    defensive = [t for t in allowed if shelf.role_of(t) in shelf.DEFENSIVE_ROLES]

    eq_lo, eq_hi = constraints["equity_weight"]
    eq_target = max(0.0, min(1.0, (eq_lo + eq_hi) / 2.0)) if eq_hi >= eq_lo else eq_lo
    floor = constraints["defensive_floor"]
    if eq_target > 1.0 - floor:
        eq_target = max(0.0, 1.0 - floor)
    def_target = 1.0 - eq_target

    if not defensive:
        eq_target, def_target = 1.0, 0.0
    if not equity:
        eq_target, def_target = 0.0, 1.0

    # Holding count is DERIVED from the position cap rather than picked, so the
    # concentration answer actually changes the shape of the book: a 25% cap
    # needs four holdings, a 10% cap needs ten. Choosing a fixed 8 made "a
    # handful I could follow" and "broad exposure" produce the same eight names
    # with slightly different weights.
    lo_n, hi_n = constraints["holdings"]
    need_for_cap = (math.ceil(1.0 / constraints["position_max"] - 1e-9)
                    if constraints["position_max"] > 0 else lo_n)
    # +2, and the slack is load-bearing rather than cosmetic. At EXACTLY the
    # minimum, n holdings under a 1/n cap have only one arithmetic solution:
    # every holding at the cap. The book then cannot express its equity/bonds
    # split at all, and `horizon` and `loss_limit` stop changing the output —
    # measured, all five loss-limit answers produced ten identical 10% holdings.
    # Two spare slots give the split somewhere to live.
    n_total = max(lo_n, min(hi_n, need_for_cap + 2))

    single_cap = constraints["single_stock_max"]
    if single_cap <= 0:
        # Filtered BEFORE the emptiness check, not after: the earlier order
        # tested `if not equity` first, so a shelf narrowed to single stocks
        # emptied the sleeve here and produced a book of nothing — reported,
        # backwards, as "only funds are allowed" when only stocks were.
        equity = [t for t in equity if not shelf.is_single_stock(t)]
        if not equity:
            equity = [t for t in allowed if not shelf.is_single_stock(t)]
        if not equity:
            applied.append(
                "your experience answer rules out individual company shares, "
                "and the categories you chose contain nothing else")

    n_def = 0
    if def_target > 0 and defensive:
        n_def = max(1, min(len(defensive), round(n_total * def_target)))
    n_eq = max(0, n_total - n_def)
    if equity and n_eq == 0:
        n_eq = 1
        n_def = max(0, n_total - 1)

    # Somebody who says they pick individual shares should not be handed six
    # index funds. Which way this leans is decided by the experience answer,
    # because that is the answer that is actually about it — the first version
    # always preferred funds and produced a near-identical equity sleeve for a
    # complete beginner and for a stock picker.
    order = _order_by_kind(prefer_stocks=single_cap >= 0.5)

    # Cap the NUMBER of single names, rather than picking freely and rescaling
    # afterwards. Rescaling did not hold: the position cap runs last and
    # redistributes spare weight into whatever is under it, which is mostly the
    # single names — so a 55% share cap came back out at 60%. A holding can
    # never exceed `position_max`, so at most `single_cap / position_max` of
    # them can fit under the share cap, and choosing that many up front makes it
    # true by construction instead of by correction.
    # The reader's "would like included" is a TILT: those categories come first
    # in the round-robin, so they are the ones that survive the holdings ceiling,
    # without the shelf having been narrowed to them.
    equity_names = _round_robin(equity, order,
                                prefer=constraints.get("include_categories"))
    if 0 < single_cap < 1.0 and constraints["position_max"] > 0:
        max_stocks = int(single_cap / constraints["position_max"] + 1e-9)
        equity_names = _limit_single_stocks(equity_names, max_stocks)

    picks: list[dict] = []
    picks += _spread(equity_names[:n_eq], eq_target * 100.0,
                     "the shares side of the mix you asked for")
    picks += _spread(_round_robin(defensive, order,
                                 prefer=constraints.get("include_categories"))[:n_def],
                     def_target * 100.0,
                     "ballast, because of the horizon and limit you gave")

    cash_lo, _ = constraints["cash_weight"]
    cash_pct = cash_lo * 100.0
    # The SAME settle loop the model path uses, rather than a private sequence of
    # fixups. The private version rescaled single stocks down and then
    # renormalised everything straight back up one line later, so the correction
    # was undone and its message left standing over a 100%-one-share book.
    picks = _settle(picks, constraints, applied)
    picks.sort(key=lambda a: -a["weight_pct"])

    # Templated FROM THE NUMBERS, deliberately. Recorded output that structurally
    # cannot be mistaken for model prose beats a label claiming it is recorded.
    tagline = (f"{eq_target * 100:.0f}% shares, "
               f"{def_target * 100:.0f}% bonds and gold, "
               f"{len(picks)} holdings, beta capped at {constraints['beta_max']:.2f}")

    return {
        "name": "Rule-drafted example book",
        "emoji": DEFAULT_EMOJI,
        "tagline": tagline,
        "notice": _REASON_TEXT.get(reason, _REASON_TEXT["no_api_key"]),
        "cash_pct": round(cash_pct, 2),
        "allocation": picks,
        "generated_by": "rules",
        "is_mock": True,
        "constraints_applied": applied,
    }


def _order_by_kind(*, prefer_stocks: bool):
    """Deterministic pick order — single names first, or funds first.

    Deterministic on purpose: `Math.random`-style variation would make the same
    answers produce a different book on every rerun, and the one property this
    allocator has to have is that the questionnaire visibly drives the output.
    Shelf order breaks ties.
    """
    index = {t: i for i, t in enumerate(shelf.tickers())}

    def order(tickers: list) -> list:
        return sorted(tickers, key=lambda t: (
            (not shelf.is_single_stock(t)) if prefer_stocks
            else shelf.is_single_stock(t),
            index.get(t, 999)))
    return order


def _round_robin(tickers: list, order, prefer=None) -> list:
    """One from each category in turn, rather than the first N in shelf order.

    Taking shelf order directly handed every stock-picker the same five
    Technology names — a book whose sector donut is 85% one colour, offered to
    somebody who never said they wanted that. Rotating through categories makes
    the equity sleeve look like a portfolio instead of the top of a list, and it
    is what lets the category preferences actually show up in the result.
    """
    buckets: dict[str, list] = {}
    preferred = set(prefer or ())
    # Preferred categories seeded first, so they lead the rotation and survive
    # the holdings ceiling. This is how "would like included" reaches the book
    # now that it no longer narrows the shelf.
    for t in order(tickers):
        cat = shelf.category_of(t) or "?"
        if cat in preferred:
            buckets.setdefault(cat, []).append(t)
    for t in order(tickers):
        cat = shelf.category_of(t) or "?"
        if cat not in preferred:
            buckets.setdefault(cat, []).append(t)
    out: list = []
    while any(buckets.values()):
        for cat in list(buckets):
            if buckets[cat]:
                out.append(buckets[cat].pop(0))
    return out


def _limit_single_stocks(tickers: list, max_stocks: int) -> list:
    """Keep order, but let at most `max_stocks` individual company shares through."""
    out, used = [], 0
    for t in tickers:
        if shelf.is_single_stock(t):
            if used >= max_stocks:
                continue
            used += 1
        out.append(t)
    return out


def _spread(tickers: list, total_pct: float, why: str) -> list:
    if not tickers or total_pct <= 0:
        return []
    each = total_pct / len(tickers)
    return [{"ticker": t, "weight_pct": each, "why": why} for t in tickers]


