"""brand.py — the identity layer: marks, wordmark, favicon.

ONE place reads the SVGs in logos/ and turns them into something a Streamlit
page can hold. Nothing else in the app touches those files.

WHY BASE64 AND NOT A FILE PATH
------------------------------
Every mark is inlined as a `data:` URI, read server-side at render time. Never
a URL, never a relative path in an <img src>. Streamlit Community Cloud does
not reliably serve arbitrary repo files, and a mark that 404s on a cold start
is a broken image in the first second of a defence. Inlining also means a PDF
export or a saved page keeps the mark, and there is no second network round
trip on first paint.

The read is cached: the four files are a few KB each, but they would otherwise
be re-read and re-encoded on EVERY rerun, and this app reruns on every sidebar
interaction.

WHICH MARK GOES WHERE — and the one contradiction in LOGOS.md
-------------------------------------------------------------
LOGOS.md is the source of truth for placement, with one internal conflict worth
resolving explicitly rather than silently picking a side:

  - its placement table says "Application masthead / sidebar header 40-56px"
  - its rules say "Minimum 72px ... At 48px the ring type becomes decorative
    texture - acceptable as an avatar, never as the only statement of the name"

Those read as contradictory but are not, and the resolution is in the second
one's own final clause. The 72px floor protects the seal when it is carrying
the NAME by itself. In the masthead it is not: it sits immediately beside the
wordmark set in type. The ring lettering is free to become texture there,
because the name is already being stated in a typeface that is legible at
14px. So 44px in the masthead is correct, and it is correct *because* the
wordmark is next to it.

SEAL_MIN_ALONE encodes exactly that distinction, and a test asserts no call
site puts a bare seal under it.
"""

from __future__ import annotations

import base64
import functools
from pathlib import Path

# The product name, in one place. It appears in the page title, the masthead,
# the marks' own alt text and the footer, and those must not be able to drift.
PRODUCT = "RoboSmart Debate Club"

LOGO_DIR = Path(__file__).parent / "logos"

MARKS = ("seal", "mirror", "rose")

# Floors from LOGOS.md. `mirror` is a HEIGHT, not a width: the mark is 3:1, and
# below ~150px tall its reflection stops resolving and reads as a printing
# fault rather than as part of the drawing.
SEAL_MIN_ALONE = 72     # a seal carrying the name by itself
MIRROR_MIN = 150        # the reflection stops reading below this


class BrandAssetError(RuntimeError):
    """A mark is missing or unreadable. Raised early and loudly: a silently
    absent logo is a blank rectangle nobody notices until the demo."""


@functools.lru_cache(maxsize=None)
def _svg(which: str, ink: str) -> str:
    if which not in MARKS:
        raise BrandAssetError(f"Unknown mark {which!r}; expected one of {MARKS}.")
    if ink not in ("dark", "light"):
        raise BrandAssetError(f"ink must be 'dark' or 'light', got {ink!r}.")
    # "-on-light" means INK FOR A LIGHT BACKGROUND, i.e. dark ink. The naming
    # describes the surface, not the ink, and reading it the other way round is
    # the easy mistake — hence this comment rather than a cleverer API.
    suffix = "-on-light" if ink == "light" else ""
    path = LOGO_DIR / f"{which}{suffix}.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise BrandAssetError(f"Cannot read brand asset {path}: {e}") from e


@functools.lru_cache(maxsize=None)
def data_uri(which: str = "seal", ink: str = "dark") -> str:
    """The mark as a `data:image/svg+xml;base64,...` URI."""
    b64 = base64.b64encode(_svg(which, ink).encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def logo(which: str = "seal", height: int = 48, ink: str = "dark",
         *, alt: str | None = None, extra_style: str = "") -> str:
    """An <img> tag for a mark, sized by HEIGHT and inlined.

    Height rather than width because two of the three marks are wildly
    different aspect ratios (seal 1:1, mirror 3:1) and height is what has to
    agree with the type beside it.

    `alt` defaults to the product name. Pass alt="" for a mark that is purely
    decorative — a watermark behind text is not content, and announcing it
    twice is worse than not announcing it.
    """
    label = PRODUCT if alt is None else alt
    # aria-hidden on the decorative case as well: alt="" alone still leaves the
    # image in the accessibility tree in some screen-reader/browser pairs.
    hidden = " aria-hidden='true'" if label == "" else ""
    return (f'<img src="{data_uri(which, ink)}" alt="{label}"{hidden} '
            f'style="display:block;height:{height}px;width:auto;{extra_style}" />')


def masthead(height: int = 44) -> str:
    """The sidebar lockup: seal beside the wordmark.

    NOT an <h1>. The page has exactly one h1 and it belongs to the document's
    main heading; this is a brand lockup, so it takes no heading semantics it
    has not earned. The seal is aria-hidden because the wordmark immediately
    after it says the same thing in text — a screen reader announcing
    "RoboSmart Debate Club RoboSmart Debate Club" is the classic cost of
    labelling a logo that sits next to its own name.
    """
    return (
        f'<div class="rs-masthead" style="display:flex;align-items:center;'
        f'gap:12px;margin:.2rem 0 1rem">'
        f'{logo("seal", height, alt="")}'
        f'<span style="font-weight:700;font-size:1.05rem;letter-spacing:-.015em;'
        f'line-height:1.15">{PRODUCT}</span>'
        f'</div>'
    )


def page_title(width: int = 420) -> str:
    """The page's <h1>, set as the drawn mirror rather than as type.

    LOGOS.md gives the mirror splash screens, title pages and report covers,
    and explicitly BANS it from a masthead — "in a horizontal bar it either
    gets cropped or forces the bar to three times its natural height. That
    position belongs to the seal." That ban is about the SIDEBAR bar, which is
    300px wide and holds the seal already. This is the page's title area, which
    is ~900px wide at desktop and was carrying an <h1> plus a band of empty
    ground above it; the mark fits there without cropping and without forcing
    anything.

    Sized by WIDTH here, unlike every other placement, because the mirror's
    constraint is a width one: below ~450px the reflection stops resolving and
    reads as a printing fault. 420px is marginally under that floor and is the
    considered trade — the alternative is 150px of vertical chrome on top of
    every view, which is the cost LOGOS.md is warning about in the first place.
    Do not go smaller.

    A REAL <h1> carrying real alt text, not a decorative image beside a hidden
    heading. The document keeps exactly one h1, a screen reader announces the
    product name from it, and the outline stays h1 -> h2 -> h3.
    """
    return (
        f'<h1 class="rs-wordmark">'
        f'<img src="{data_uri("mirror")}" alt="{PRODUCT}" '
        f'style="display:block;width:{width}px;max-width:100%;height:auto" />'
        f'</h1>'
    )


def favicon_tag() -> str:
    """A <link rel="icon"> carrying the seal inline.

    st.set_page_config(page_icon=...) is not a reliable route for SVG, so the
    title is set there and the icon is injected here instead. The seal is the
    right mark for this by construction: it is the only one that is 1:1 and
    survives being rendered at 32px.
    """
    return (f'<link rel="icon" type="image/svg+xml" href="{data_uri("seal")}">')
