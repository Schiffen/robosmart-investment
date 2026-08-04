"""book_source.py — where the portfolio on screen came from, said once.

A book can now arrive four ways: a shipped sample profile, an uploaded CSV, a
table typed into the builder, or a draft generated from an investor
questionnaire. Everything downstream already uses whatever is in
`st.session_state.portfolio` — that part was never the problem. The problem was
that the app could only NAME one of the four.

The identity banner fired only when a sample profile was loaded, so a user with
their own book saw nothing at all in the main area about whose data was on
screen. Worse, `reporting/panel._book_label()` returned None for anything that
was not a profile and `reporting/document.build` prints

    subject = profile_label or "Your uploaded portfolio"

on the cover — so a book that was BUILT or DRAFTED would have gone out as a PDF
titled "Your uploaded portfolio". That is not a labelling nicety; it is a report
making a false statement about its own subject, in the one artifact designed to
be sent to somebody who was never in front of the app.

So provenance is one record, written by exactly one function (`app._load`), and
read by the banner, the sidebar, the export panel, the PDF cover and the
download filename. This module is pure — no Streamlit — so `reporting/` can use
it without importing the app.

    {"kind": "profile" | "upload" | "built" | "drafted",
     "label":  str,         # what the app and the cover call this book
     "id":     str | None,  # profile id, when kind == "profile"
     "detail": str | None}  # profile `expect`, upload filename, or model note

`detail` is deliberately NOT uniform in status, and callers must not treat it as
though it were. A profile's `expect` is a claim enforced against real numbers by
tests/test_profiles.py. A drafted book's note is model prose. Rendering them
identically would dress an unchecked claim in a checked claim's clothes, so
`detail_is_checked()` exists to keep the two apart at the render site.
"""

from __future__ import annotations

KINDS = ("profile", "upload", "built", "drafted")

# Used when session state predates this module, or somehow holds nothing.
_FALLBACK = {"kind": "upload", "label": "Your portfolio", "id": None,
             "detail": None}


def profile(profile_id: str, *, label: str, expect: str | None = None) -> dict:
    """A shipped sample investor book."""
    return {"kind": "profile", "label": label or profile_id,
            "id": profile_id, "detail": expect or None}


def upload(filename: str | None = None) -> dict:
    """A CSV the user uploaded."""
    return {"kind": "upload", "label": "Your uploaded portfolio",
            "id": None, "detail": filename or None}


def built() -> dict:
    """A book typed into the builder by hand."""
    return {"kind": "built", "label": "Your portfolio, built here",
            "id": None, "detail": None}


def drafted(note: str | None = None) -> dict:
    """A book drafted from the investor questionnaire, then reviewed by the user.

    `note` is the model's "what to notice" line. Model prose — see the module
    docstring on why that is kept distinguishable from a profile's `expect`.
    """
    return {"kind": "drafted", "label": "Drafted from your investor profile",
            "id": None, "detail": note or None}


# --------------------------------------------------------------------------
# Reading one
# --------------------------------------------------------------------------

def normalise(source) -> dict:
    """Any stored value -> a usable record. Never raises, never returns None."""
    if not isinstance(source, dict) or source.get("kind") not in KINDS:
        return dict(_FALLBACK)
    out = dict(_FALLBACK)
    out.update({k: source.get(k) for k in ("kind", "label", "id", "detail")})
    if not out.get("label"):
        out["label"] = _FALLBACK["label"]
    return out


def kind_of(source) -> str:
    return normalise(source)["kind"]


def label_of(source) -> str:
    """What to call this book — on screen and on the PDF cover.

    Always a real string. `reporting/panel._book_label()` used to return None
    for three of the four kinds and let the cover fall back to a wrong default.
    """
    return normalise(source)["label"]


def profile_id(source) -> str | None:
    """The sample profile's id, or None for a book of the user's own."""
    s = normalise(source)
    return s["id"] if s["kind"] == "profile" else None


def is_users_own(source) -> bool:
    """True for anything the user brought or made — i.e. offer to remove it."""
    return kind_of(source) != "profile"


def detail_is_checked(source) -> bool:
    """Is `detail` a claim the test suite enforces, or is it model prose?

    Only a profile's `expect` is checked. This is what stops the builder's
    banner from rendering a generated sentence with the authority of one.
    """
    return kind_of(source) == "profile"


def filename_slug(source) -> str:
    """The middle of `robosmart-<slug>-report.pdf`."""
    s = normalise(source)
    if s["kind"] == "profile" and s["id"]:
        return str(s["id"]).replace("_", "-")
    return {"upload": "portfolio", "built": "built", "drafted": "drafted"}.get(
        s["kind"], "portfolio")
