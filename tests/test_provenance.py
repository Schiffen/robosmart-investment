"""A book must be labelled as what it actually is — on screen and on the cover.

Four ways a portfolio now arrives: a shipped sample, an uploaded CSV, a table
typed into the builder, and a draft generated from a questionnaire. Before
`book_source` existed the app could only name the first, and the PDF cover ran

    subject = profile_label or "Your uploaded portfolio"

against a `_book_label()` that returned None for the other THREE. A book built
in the app or drafted from a questionnaire would therefore have been exported
under a cover saying it was uploaded — a false statement in the one artifact
designed to be sent to somebody who was never in front of the app.

Also here: editing cash must not disturb anything a sample book claims about
itself. Weights are equity-based with cash excluded (portfolio_metrics, finance
assumption 1), so it cannot — and that is asserted rather than assumed, because
it is what lets the cash control stay available on a sample without detaching it
from its identity.
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_source
import data_layer
import portfolio_metrics as pm
import profiles

ALL_KINDS = [
    ("profile", book_source.profile("balanced_growth", label="⚖️ Balanced growth",
                                    expect="trips exactly one guideline")),
    ("upload", book_source.upload("my-book.csv")),
    ("built", book_source.built()),
    ("drafted", book_source.drafted("mostly bonds, because you said two years")),
]


# --------------------------------------------------------------------------
# Every kind names itself
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_every_kind_has_a_real_label(kind, source):
    label = book_source.label_of(source)
    assert isinstance(label, str) and label.strip()
    assert book_source.kind_of(source) == kind


@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_only_an_actual_upload_is_ever_called_uploaded(kind, source):
    """The specific defect: three kinds shared one wrong label."""
    said_uploaded = "upload" in book_source.label_of(source).lower()
    assert said_uploaded == (kind == "upload"), (
        f"a {kind!r} book is labelled {book_source.label_of(source)!r}")


def test_the_four_labels_are_all_different():
    labels = {book_source.label_of(s) for _, s in ALL_KINDS}
    assert len(labels) == len(ALL_KINDS), f"labels collide: {labels}"


@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_filenames_are_distinct_and_filesystem_safe(kind, source):
    slug = book_source.filename_slug(source)
    assert slug and "_" not in slug and " " not in slug
    assert slug == slug.lower()


def test_filename_slugs_do_not_collide_across_kinds():
    slugs = {book_source.filename_slug(s) for _, s in ALL_KINDS}
    assert len(slugs) == len(ALL_KINDS), slugs


# --------------------------------------------------------------------------
# Only a profile's claim is a checked claim
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_only_a_profiles_detail_counts_as_checked(kind, source):
    """`expect` is enforced by tests/test_profiles.py. A drafted note is model
    prose. Rendering them alike would give an unchecked claim borrowed
    authority, so the render site has to be able to tell them apart."""
    assert book_source.detail_is_checked(source) == (kind == "profile")


@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_only_a_profile_yields_a_profile_id(kind, source):
    assert (book_source.profile_id(source) is not None) == (kind == "profile")
    assert book_source.is_users_own(source) == (kind != "profile")


# --------------------------------------------------------------------------
# Nothing may crash on a missing or malformed record
# --------------------------------------------------------------------------

@pytest.mark.parametrize("junk", [None, {}, "balanced_growth", 7,
                                  {"kind": "nonsense"}, {"kind": "built"}])
def test_a_missing_or_malformed_source_still_produces_a_usable_label(junk):
    for fn in (book_source.label_of, book_source.filename_slug,
               book_source.kind_of):
        out = fn(junk)
        assert isinstance(out, str) and out.strip(), f"{fn.__name__}({junk!r}) -> {out!r}"
    assert book_source.profile_id(junk) is None or isinstance(
        book_source.profile_id(junk), str)


def test_every_shipped_profile_produces_a_label_that_is_not_the_raw_id():
    for meta in profiles.list_profiles():
        src = book_source.profile(meta["id"], label=profiles.label(meta),
                                  expect=meta["expect"])
        assert book_source.label_of(src) != meta["id"]
        assert book_source.profile_id(src) == meta["id"]


# --------------------------------------------------------------------------
# The cover no longer depends on the wrong fallback
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind,source", ALL_KINDS)
def test_the_cover_subject_is_the_books_own_label(kind, source):
    """report.build does `subject = profile_label or <default>`; the label now
    arrives truthy for all four kinds, so the default decides nothing."""
    label = book_source.label_of(source)
    subject = label or "Your portfolio"
    assert subject == label
    if kind != "upload":
        assert "uploaded" not in subject.lower()


def test_the_defensive_default_in_document_is_no_longer_the_upload_string():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "reporting", "document.py")).read()
    assert 'profile_label or "Your uploaded portfolio"' not in src, (
        "the cover still falls back to calling every non-profile book uploaded")


# --------------------------------------------------------------------------
# Editing cash cannot invalidate what a sample book claims
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spy():
    return data_layer.get_benchmark_history("SPY")


@pytest.mark.parametrize("profile_id", profiles.available_ids())
def test_changing_cash_moves_total_value_and_no_weight(profile_id, spy):
    book = profiles.load_portfolio(profile_id)
    tickers = [p["ticker"] for p in book["positions"]]
    contexts = data_layer.get_context_batch(tickers)

    def measure(cash):
        b = copy.deepcopy(book)
        b["cash"] = cash
        df = pm.position_values(b, contexts)
        return (pm.portfolio_summary(df, b["cash"])["total_value"],
                {r.ticker: round(r.weight_pct, 9) for r in df.itertuples()})

    low_total, low_weights = measure(1_000.0)
    high_total, high_weights = measure(500_000.0)

    assert high_total > low_total, "cash is not reaching total value"
    assert low_weights == high_weights, (
        "a cash edit moved a weight — weights are supposed to be equity-based "
        "with cash excluded, and the sidebar control depends on that")


def test_a_cash_edit_does_not_write_back_into_the_cached_profile():
    """`load_portfolio` deep-copies. Without that, editing cash on a sample book
    would mutate the parsed profile for the rest of the run."""
    first = profiles.load_portfolio("balanced_growth")
    original = first["cash"]
    first["cash"] = original + 12_345.0
    second = profiles.load_portfolio("balanced_growth")
    assert second["cash"] == original
    assert second["positions"] is not first["positions"]


@pytest.mark.parametrize("profile_id", profiles.available_ids())
def test_a_sample_book_still_trips_its_own_asserts_after_a_cash_edit(profile_id, spy):
    """The reason a cash edit is allowed to keep the book's identity."""
    doc_asserts = None
    import json
    with open(os.path.join(profiles.PROFILE_DIR, f"{profile_id}.json")) as fh:
        doc_asserts = json.load(fh).get("asserts") or {}
    if "warnings_exactly" not in doc_asserts:
        pytest.skip(f"{profile_id} makes no warning-count claim")

    book = profiles.load_portfolio(profile_id)
    book["cash"] = 250_000.0          # an absurd, deliberate edit
    contexts = data_layer.get_context_batch([p["ticker"] for p in book["positions"]])
    df = pm.position_values(book, contexts)
    flags = pm.concentration_flags(df, pm.sector_breakdown(df, book))
    assert len(flags) == doc_asserts["warnings_exactly"], (
        f"{profile_id} stopped demonstrating its claim after a cash edit")


# --------------------------------------------------------------------------
# The PDF explains a drafted book — with the answers, not the confession
# --------------------------------------------------------------------------

import book_spec
from reporting import document as report

_HOSTILE = "P/E < 20 & falling <font color=white>hidden</font> </para><b>"


def _drafted_profile(note=None, tensions=None):
    a = {"purpose": "growth", "horizon": "over_10y", "loss_limit": "35",
         "behaviour": "hold", "experience": "etfs", "concentration": "broad",
         "include_categories": ["Bonds"], "exclude_categories": ["Energy"]}
    c = book_spec.constraints(a)
    pairs = [(q["prompt"], book_spec.option(q["id"], a[q["id"]])["label"])
             for q in book_spec.QUESTIONS]
    pairs.append(("Wants excluded", "Energy"))
    bounds = [l.lstrip("- ").strip()
              for l in book_spec.describe_constraints(c).splitlines() if l.strip()]
    return {"answers": pairs, "bounds": bounds,
            "tensions": tensions if tensions is not None
            else book_spec.answer_tensions(a),
            "note": note or "Look first at how broadly this is spread."}


def _tiny_book():
    import data_layer
    import portfolio_metrics as pm
    book = {"positions": [
        {"ticker": "VTI", "shares": 10.0, "cost_basis": 300.0, "sector": "US Equity"},
        {"ticker": "BND", "shares": 20.0, "cost_basis": 72.0, "sector": "Fixed Income"}],
        "cash": 1000.0, "currency": "USD"}
    ctx = data_layer.get_context_batch(["VTI", "BND"])
    return book, pm.position_values(book, ctx)


def test_a_drafted_book_report_carries_the_questionnaire():
    book, positions = _tiny_book()
    pdf = report.build(portfolio=book, positions=positions,
                       profile_label="Drafted from your investor profile",
                       investor_profile=_drafted_profile())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 4000


def test_the_report_is_unchanged_when_there_is_no_questionnaire():
    """A CSV or hand-built book must not sprout an explanation it never had."""
    book, positions = _tiny_book()
    without = report.build(portfolio=book, positions=positions,
                           profile_label="Your portfolio, built here")
    with_it = report.build(portfolio=book, positions=positions,
                           profile_label="Drafted from your investor profile",
                           investor_profile=_drafted_profile())
    assert len(with_it) > len(without), "the profile section added nothing"


def test_the_free_text_is_never_carried_into_the_report():
    """The whole point of this document is that it gets forwarded. Somebody
    describing themselves in their own words is not something the export should
    publish on their behalf."""
    profile = _drafted_profile()
    blob = repr(profile).lower()
    assert "free_text" not in profile
    for personal in ("i work in", "i am close to", "describe yourself"):
        assert personal not in blob


def test_the_builder_hands_the_report_answers_but_no_free_text():
    """Asserted against the function's SOURCE, because the alternative is
    calling it — and it reads st.session_state, which outside a script run is
    the real one rather than any test's, so a direct call would pass against
    anything."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tabs", "build.py")).read()
    start = src.index("def _profile_for_report")
    fn = src[start:src.index("def _render_commit", start)]
    assert "FREE_TEXT" not in fn, (
        "the report summary reaches for the free-text box — it must not")
    for key in ("answers", "bounds", "tensions", "note"):
        assert f'"{key}"' in fn, f"the report summary stopped carrying {key}"


@pytest.mark.parametrize("field", ["note", "answer", "tension"])
def test_hostile_text_cannot_kill_or_style_the_export(field):
    """reportlab's Paragraph parses a small HTML dialect: an unescaped `&` or a
    stray tag raises and kills the export, and `<font color=white>` would be
    OBEYED. Mirrors the hostile-debate test."""
    profile = _drafted_profile()
    if field == "note":
        profile["note"] = _HOSTILE
    elif field == "answer":
        profile["answers"] = [(_HOSTILE, _HOSTILE)]
    else:
        profile["tensions"] = [{"said": _HOSTILE, "found": _HOSTILE,
                                "text": _HOSTILE, "severity": "warn"}]

    book, positions = _tiny_book()
    pdf = report.build(portfolio=book, positions=positions,
                       profile_label="Drafted from your investor profile",
                       investor_profile=profile)
    assert pdf[:4] == b"%PDF"


def test_a_long_questionnaire_paginates_rather_than_truncating():
    """Model output has no length contract. Content that cannot fit must open
    another page, not silently vanish."""
    profile = _drafted_profile(note="word " * 4000)
    profile["bounds"] = [f"bound number {i}, spelled out at length " * 3
                         for i in range(60)]
    book, positions = _tiny_book()
    long_pdf = report.build(portfolio=book, positions=positions,
                            profile_label="Drafted", investor_profile=profile)
    short_pdf = report.build(portfolio=book, positions=positions,
                             profile_label="Drafted",
                             investor_profile=_drafted_profile())
    assert len(long_pdf) > len(short_pdf) * 1.2, "long content was truncated"
