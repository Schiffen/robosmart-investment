"""The identity layer and the About dialog.

Two things are guarded here that are easy to break silently:

1. THE MARKS ARE STANDALONE. Their whole value is that they render identically
   in the app, in a browser tab, in a PDF and on a slide. That property dies
   the moment one of them picks up a <text> element, a font reference, an
   external href or a CSS variable — and it dies invisibly, because the file
   still renders correctly on the machine that broke it.

2. THE PRODUCT NAME IS IN ONE PLACE. It appears in the page title, the
   masthead, the marks' alt text and the footer. Four hard-coded copies is
   three chances to disagree.
"""

import os
import re
import xml.etree.ElementTree as ET

import pytest

import about
import brand

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_FILES = ["seal", "seal-on-light", "mirror", "mirror-on-light",
             "rose", "rose-on-light"]

DARK_INK = "#E6EDF3"
LIGHT_INK = "#10151A"


# --------------------------------------------------------------------------
# The assets
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ALL_FILES)
def test_every_mark_is_wellformed_svg_with_a_viewbox(name):
    path = brand.LOGO_DIR / f"{name}.svg"
    assert path.exists(), f"{path} is missing"
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    assert root.get("viewBox"), "no viewBox: the mark will not scale"


@pytest.mark.parametrize("name", ALL_FILES)
def test_every_mark_is_self_contained(name):
    """No fonts, no external references, no CSS variables.

    A <text> element renders in whatever font the viewing machine happens to
    have, so the lettering would differ between the app and a PDF. An external
    href simply fails to load anywhere the file is not served from.
    """
    svg = (brand.LOGO_DIR / f"{name}.svg").read_text(encoding="utf-8")
    assert "<text" not in svg, "lettering must be outline paths, not <text>"
    assert "font-family" not in svg and "@font-face" not in svg
    assert "currentColor" not in svg, "ink must be explicit, not inherited"
    assert "var(--" not in svg, "no CSS variables: a PDF has no cascade"
    assert not re.search(r'href\s*=\s*"(?!#)', svg), "no external references"
    assert "xmlns" in svg, "must be namespace-complete to render standalone"


def _normalise_ids(svg: str) -> str:
    """Strip the d/l suffix from internal ids so twins can be compared.

    See test_light_twin_differs_only_in_ink_and_internal_ids for why the ids
    are allowed — indeed required — to differ.
    """
    return re.sub(r'\b(mg|mm)[dl]\b', r'\1', svg)


@pytest.mark.parametrize("stem", ["seal", "mirror", "rose"])
def test_light_twin_differs_only_in_ink_and_internal_ids(stem):
    """LOGOS.md says "the only permitted difference ... is the ink value".

    THAT IS TOO STRONG, and the mirror proves it. Its twins also differ in
    their internal gradient/mask ids (mgd/mmd vs mgl/mml), and they HAVE to:
    brand.py inlines every mark as base64 into the same document, SVG ids
    share one global namespace per document, and two elements with id="mgd"
    would collide — the first mask registered would silently apply to both
    marks, so a light-on-dark mirror would take the light one's reflection.

    So the real invariant is: identical drawing, ink swapped, ids namespaced.
    Asserted both ways — the geometry must match AND the ids must NOT.
    """
    dark = (brand.LOGO_DIR / f"{stem}.svg").read_text(encoding="utf-8")
    light = (brand.LOGO_DIR / f"{stem}-on-light.svg").read_text(encoding="utf-8")
    assert dark != light
    assert _normalise_ids(dark).replace(DARK_INK, LIGHT_INK) == _normalise_ids(light), \
        f"{stem}-on-light.svg differs from its twin by more than ink and ids"


def test_mirror_twins_do_not_share_internal_ids():
    """Both files can be inlined into one page; colliding ids would make one
    reflection mask win for both."""
    dark = (brand.LOGO_DIR / "mirror.svg").read_text(encoding="utf-8")
    light = (brand.LOGO_DIR / "mirror-on-light.svg").read_text(encoding="utf-8")
    ids = lambda s: set(re.findall(r'id="([^"]+)"', s))
    assert ids(dark) and ids(light)
    assert not (ids(dark) & ids(light)), \
        f"mirror twins share ids {ids(dark) & ids(light)} — masks will collide"


def test_rose_paths_are_identical_to_the_seals_centre_mark():
    """The rose was EXTRACTED from the seal, not redrawn.

    If it is ever redrawn by hand the two marks drift, and the drift shows up
    only when someone puts them side by side. Pinning the paths makes that
    impossible.
    """
    seal = (brand.LOGO_DIR / "seal.svg").read_text(encoding="utf-8")
    rose = (brand.LOGO_DIR / "rose.svg").read_text(encoding="utf-8")
    group = re.search(
        r'<g transform="translate\(-45\.6 -45\.6\) scale\(3\.8\)">(.*?)</g>',
        seal, re.S)
    assert group, "the seal's centre-mark group moved; re-extract the rose"
    for path in re.findall(r'<path d="([^"]+)"', group.group(1)):
        assert path in rose, f"rose is missing the seal's spoke {path!r}"
    assert rose.count("<path") == group.group(1).count("<path")


def test_rose_is_optically_centred_not_bbox_cropped():
    """The vertical spoke is longer than the other eleven, so a tight bbox
    would render the mark visibly off-centre in a square slot."""
    vb = [float(v) for v in
          ET.parse(brand.LOGO_DIR / "rose.svg").getroot().get("viewBox").split()]
    x, y, w, h = vb
    assert abs(w - h) < 0.01, "viewBox must be square"
    assert abs((x + w / 2) - 12.0) < 0.01 and abs((y + h / 2) - 12.0) < 0.01, \
        "viewBox must be centred on the rose's own centre (12, 12)"


# --------------------------------------------------------------------------
# The helpers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("which", brand.MARKS)
@pytest.mark.parametrize("ink", ["dark", "light"])
def test_marks_inline_as_base64_data_uris(which, ink):
    """Never a file path in an <img src>. Community Cloud does not reliably
    serve arbitrary repo files, and a mark that 404s is a broken image in the
    first second of a defence."""
    uri = brand.data_uri(which, ink)
    assert uri.startswith("data:image/svg+xml;base64,")
    assert len(uri) > 500


def test_unknown_mark_or_ink_raises_rather_than_rendering_nothing():
    with pytest.raises(brand.BrandAssetError):
        brand.data_uri("bogus", "dark")
    with pytest.raises(brand.BrandAssetError):
        brand.data_uri("seal", "chartreuse")


def test_masthead_claims_no_heading_semantics():
    """The page has exactly one <h1> and it is the document heading."""
    assert "<h1" not in brand.masthead()
    assert brand.PRODUCT in brand.masthead()


def test_masthead_seal_is_hidden_from_screen_readers():
    """The wordmark sits immediately beside it in text. Labelling both makes a
    screen reader announce the product name twice in a row."""
    html = brand.masthead()
    assert "aria-hidden='true'" in html
    assert f'alt="{brand.PRODUCT}"' not in html


def test_decorative_placements_can_opt_out_of_alt_text():
    assert "aria-hidden='true'" in brand.logo("rose", 28, alt="")
    assert "aria-hidden" not in brand.logo("seal", 80)


def test_favicon_carries_the_seal_inline():
    tag = brand.favicon_tag()
    assert tag.startswith('<link rel="icon"')
    assert "data:image/svg+xml;base64," in tag


# --------------------------------------------------------------------------
# The name lives in one place
# --------------------------------------------------------------------------

def test_the_app_takes_its_name_from_brand_not_a_literal():
    """Four hard-coded copies would be three chances to disagree."""
    src = open(os.path.join(BASE, "app.py"), encoding="utf-8").read()
    assert "brand.PRODUCT" in src
    assert '"RoboSmart Investment"' not in src, "stale product name in app.py"


def test_no_stale_product_name_in_user_facing_copy():
    for rel in ("app.py", "about.py", "brand.py"):
        src = open(os.path.join(BASE, rel), encoding="utf-8").read()
        assert "RoboSmart Investment" not in src, f"stale name in {rel}"


# --------------------------------------------------------------------------
# The About dialog
# --------------------------------------------------------------------------

def test_about_documents_every_router_view():
    """A view added to the router without an entry here leaves a reader with
    an unexplained button."""
    app_src = open(os.path.join(BASE, "app.py"), encoding="utf-8").read()
    router = re.search(r"^VIEWS = \[(.*?)\]", app_src, re.S | re.M)
    assert router, "could not find the router's VIEWS list in app.py"
    names = re.findall(r'"([^"]+)"', router.group(1))
    documented = {name for _, name, _ in about.VIEWS}
    assert set(names) == documented, (
        f"router and About disagree: router={set(names)}, about={documented}")


def test_about_entries_are_substantive():
    for _, name, what in about.VIEWS:
        assert len(what) > 120, f"{name}'s description is too thin to help"


def test_about_states_the_not_advice_disclaimer():
    src = open(os.path.join(BASE, "about.py"), encoding="utf-8").read()
    assert "not investment advice" in src.lower()


def test_about_dismissal_clears_the_flag():
    """st.dialog's on_dismiss defaults to "ignore", which closes client-side
    with NO rerun — leaving the flag set, so the dialog reappears on the next
    rerun and reads as a modal that will not stay shut."""
    import streamlit as st
    st.session_state[about._FLAG] = True
    about._dismiss()
    assert st.session_state[about._FLAG] is False


def test_the_header_cannot_take_the_whole_app_down(monkeypatch):
    """Reproduces a real outage, exactly as it happened in production.

    Streamlit Community Cloud re-runs app.py on a push but can keep an
    already-imported module in sys.modules. A deploy that added a NEW function
    to brand.py landed new app.py against OLD brand: `masthead()` resolved,
    `page_title()` raised AttributeError at module scope, and the whole app was
    replaced by a traceback — sidebar rendered, everything else gone.

    Deleting the attribute is a faithful simulation of that state. The app must
    fall back to a typeset title: losing the drawn mark is cosmetic, losing the
    portfolio is not.
    """
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.chdir(BASE)
    monkeypatch.setenv("USE_MOCK", "1")
    monkeypatch.delattr(brand, "page_title")

    at = AppTest.from_file(os.path.join(BASE, "app.py"),
                           default_timeout=90).run()
    assert not at.exception, (
        f"a missing brand.page_title took the whole app down: {at.exception}")
    # And the product name still reaches the page some other way.
    seen = " ".join([t.value for t in at.title if isinstance(t.value, str)]
                    + [m.value for m in at.markdown if isinstance(m.value, str)])
    assert brand.PRODUCT in seen


def test_about_is_gated_on_session_state_not_the_button_branch():
    """A dialog exists only for the run that calls it, and this app reruns on
    every sidebar interaction."""
    src = open(os.path.join(BASE, "about.py"), encoding="utf-8").read()
    assert "def maybe_render" in src
    assert "session_state" in src
    app_src = open(os.path.join(BASE, "app.py"), encoding="utf-8").read()
    assert "about.maybe_render()" in app_src


# --------------------------------------------------------------------------
# The Guide must not describe an app that no longer exists
# --------------------------------------------------------------------------
#
# It is the app's own account of itself, so a stale line there is not merely
# incomplete — it is the product telling the reader something false. The stock
# selector moved out of the sidebar; the sentence that said otherwise was still
# sitting in step 4 and read perfectly well.

def _about_source():
    import os
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "about.py"), encoding="utf-8").read()


def _about_text():
    """about.py's copy as a reader sees it, near enough to search.

    Scanning the raw source does not work: the Guide's copy is built from
    adjacent Python string literals wrapped in markup, so "Build a portfolio"
    is really `"<b>Build a "` + `"portfolio</b>"` across a line break and never
    appears contiguously. Joining adjacent literals and dropping tags first is
    what makes a phrase check mean what it looks like it means.
    """
    import re
    src = _about_source()
    src = re.sub(r'"\s*\n\s*f?"', "", src)      # join split string literals
    src = re.sub(r"<[^>]+>", "", src)             # drop markup
    return re.sub(r"\s+", " ", src).lower()


def test_the_guide_does_not_claim_the_stock_selector_is_in_the_sidebar():
    src = _about_text()
    for stale in ("the sidebar selector drives",
                  "sidebar selector",
                  "selector in the sidebar"):
        assert stale not in src, f"the Guide still says {stale!r}"


def test_the_guide_names_all_three_ways_to_bring_a_portfolio():
    """Upload, build by hand, or have one drafted — the Guide is the only place
    a reader finds out the last two exist at all."""
    src = _about_text()
    assert "csv" in src
    assert "build a portfolio" in src
    assert "drafted" in src


def test_the_guide_explains_that_the_selector_only_appears_on_two_views():
    src = _about_text()
    assert "bull vs bear" in src and "what happened today" in src
    assert "under the view buttons" in src or "under the router" in src


def test_the_guide_covers_editable_cash_and_says_it_is_not_in_the_weights():
    src = _about_text()
    assert "cash" in src
    assert "weight" in src


def test_the_guide_never_calls_a_drafted_book_a_recommendation():
    src = _about_text()
    assert "demonstration" in src
    for phrase in ("we recommend", "recommended for you", "suitable for you"):
        assert phrase not in src, f"the Guide says {phrase!r}"


def test_the_view_grid_is_still_four_cards():
    """The builder is a mode, not a view. A fifth card would contradict the
    router the grid is a map of."""
    import about
    assert len(about.VIEWS) == 4
