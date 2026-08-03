"""reporting — the branded PDF export.

Three modules that only make sense together, so they live together rather than
as three loose files at the repo root:

    document.py   the PDF itself: cover, tables, the debate, the figures
    charts.py     those figures, drawn with matplotlib (no browser required)
    panel.py      the Streamlit dialog that drives it from the header

The split is along a real seam. `charts` knows how to DRAW and nothing else —
a test asserts it imports no analytics module, so the report can never become a
second source of numbers. `document` knows how to lay out a PDF and never
touches Streamlit. `panel` is the only one that knows there is a UI at all,
which is why the other two are testable without one.
"""

from reporting.document import (  # noqa: F401
    ReportUnavailable, availability, build, pdf_safe,
)

__all__ = ["ReportUnavailable", "availability", "build", "pdf_safe"]
