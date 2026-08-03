"""export.py — the PDF export, as a global action in the header.

WHY IT MOVED OUT OF THE DASHBOARD
---------------------------------
It used to sit at the very bottom of the Dashboard view. Two things were wrong
with that. The export carries the WHOLE app — holdings, figures, and any Bull
vs Bear debate that has been run — so scoping it to one view misrepresented it;
and it was below a full page of charts, which is the one place a reader will
not look for an action. It now sits beside the product name, visible from every
view, which is also where a reader expects "do something with this page".

THE TWO-STEP IS DELIBERATE
--------------------------
`st.download_button` needs its bytes UP FRONT. Wiring the report straight into
one would rebuild the entire PDF on every rerun — and this app reruns whenever
the sidebar is touched — making a feature most readers press once into a
permanent tax on everyone. So the first press builds and parks the bytes in
session state, and the download appears once there is something to download.
"""

from __future__ import annotations

import streamlit as st

import brand
import run_mode

_FLAG = "show_export"
_BYTES = "pdf_bytes"


def open_button(*, key: str = "export_btn") -> None:
    """The header trigger. Icon plus a short label — an icon alone would be a
    guess, and this is the one action that produces a file."""
    if st.button(":material/ios_share: Export", key=key,
                 use_container_width=True,
                 help="Save this analysis as a branded PDF you can keep, "
                      "print or send to someone."):
        st.session_state[_FLAG] = True


def _dismiss() -> None:
    st.session_state[_FLAG] = False


def maybe_render(portfolio: dict | None) -> None:
    """Re-assert the dialog while the flag is set. See about.py note 1: a
    dialog exists only for the run that calls it."""
    if st.session_state.get(_FLAG):
        _dialog(portfolio)


@st.dialog("Export this analysis", width="medium", on_dismiss=_dismiss)
def _dialog(portfolio: dict | None) -> None:
    import report

    if not portfolio or not portfolio.get("positions"):
        st.info("Load a portfolio first — there is nothing to export yet.")
        return

    state = report.availability()
    if not state["pdf"]:
        st.error(state["why"])
        return

    ticker = st.session_state.get("active_ticker")
    debate = (st.session_state.get("debate_results") or {}).get(ticker)

    st.markdown(
        "A **branded PDF** of everything this app currently knows about your "
        "portfolio — the cover carries the mark, and every page carries the "
        "date and the disclaimer, so a page that gets separated from the rest "
        "still says what it is."
    )

    # State the contents BEFORE generating. The debate is the part worth
    # sending to someone and it is only present if one has been run — better to
    # say so while the reader can still go and run one than after they have
    # opened a PDF that lacks it.
    st.markdown("**This report will contain**")
    st.markdown(
        "- Your holdings, priced, with cost basis, P&L and weights\n"
        "- Where your money sits by sector, and what moved it today\n"
        "- How correlated your holdings are, and a one-year backtest\n"
        + (f"- The **{ticker}** Bull vs Bear debate, both cases and the "
           f"judge's verdict\n" if debate else "")
    )
    if not debate:
        st.caption(":material/info: Run a **Bull vs Bear** debate and it will "
                   "be included — it is the part most worth sending to "
                   "someone else.")

    if st.button(":material/picture_as_pdf: Build the report", type="primary",
                 use_container_width=True):
        with st.spinner("Rendering…"):
            try:
                from tabs.dashboard import collect_report_data
                data = collect_report_data(portfolio)
                st.session_state[_BYTES] = report.build(
                    portfolio=portfolio,
                    positions=data["positions"],
                    sector_df=data["sector_df"],
                    figures=data["charts"],
                    currency=data["currency"],
                    debate=dict(debate, ticker=ticker) if debate else None,
                    profile_label=_book_label(),
                    data_source=("Live market data"
                                 if run_mode.describe()["data"] == "live"
                                 else "Recorded snapshot"))
            except Exception as e:  # noqa: BLE001 — never take the app down
                st.session_state.pop(_BYTES, None)
                st.error(f"Couldn't build the report: {e}")

    if st.session_state.get(_BYTES):
        st.download_button(
            ":material/download: Download PDF",
            st.session_state[_BYTES],
            file_name=_filename(), mime="application/pdf",
            use_container_width=True)
        st.caption(f"{len(st.session_state[_BYTES]) / 1024:,.0f} KB · "
                   f"{brand.PRODUCT}")


def _book_label() -> str | None:
    """The name of the book being reported on, or None for an upload.

    None is meaningful downstream: report.build prints "Your uploaded
    portfolio" for it, so a user's own CSV is named as theirs rather than
    silently borrowing a sample investor's title.
    """
    import profiles
    pid = st.session_state.get("loaded_profile")
    if not pid:
        return None
    meta = next((p for p in profiles.list_profiles() if p["id"] == pid), None)
    return profiles.label(meta) if meta else pid


def _filename() -> str:
    book = (st.session_state.get("loaded_profile") or "portfolio")
    return f"robosmart-{book}-report.pdf".replace("_", "-")
