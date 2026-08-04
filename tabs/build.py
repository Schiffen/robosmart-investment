"""tabs/build.py — make a portfolio without a CSV.

Two ways in, one review table. Type the holdings yourself, or answer a short
questionnaire and let a model draft an example book — either way the result
lands in the SAME editable table, and nothing becomes your portfolio until you
press the button that says so. That human step is not decoration: it is what
keeps a generated book a demonstration rather than a recommendation.

A FULL-PAGE TAKEOVER, NOT A DIALOG AND NOT A FIFTH VIEW
-------------------------------------------------------
Not a dialog: measured, `st.dialog(width="large")` is 1280px and this app runs
`layout="wide"`, so a dialog would have given the builder LESS room than the page
it covers — and dialog widgets go stale on any full rerun that does not re-call
the dialog function, which a half-filled questionnaire cannot afford.

Not a fifth router pill: about.py already litigated the 390px two-row wrap, and a
portfolio SOURCE is not a VIEW. The four views analyse the current book; this one
makes one. Hiding the router while it is up is the signal that this is a mode.

FOUR THINGS ABOUT st.data_editor THAT ARE NOT OBVIOUS
------------------------------------------------------
All four verified against the installed Streamlit 1.60, because each fails
silently rather than loudly.

1. NO `format=` ON ANY COLUMN. `st.data_editor` is the same canvas grid as
   `st.dataframe`, and its accessibility tree reads the cell's `.data`, never its
   `.displayData`. So `format="dollar"` PAINTS "$513.84" and ANNOUNCES
   "513.8399999999999" — precisely the divergence that made this codebase reject
   `st.dataframe` for the holdings table (tabs/dashboard.py, theme.py rule on the
   same). `column_config` cannot fix it; it only touches the paint. With no
   `format=`, the painted and announced strings are the same string, and the
   defect does not exist.

2. THE FRAME MUST NOT CHANGE WHILE THE EDITOR IS MOUNTED. Only
   `num_rows="fixed"` derives the element id from a schema signature; every other
   mode hashes the SERIALIZED FRAME. A frame that changes value gets a new id,
   the old id is not in `active_widget_ids`, and Streamlit drops the pending
   edits with no error at all. So `ss.builder_draft` is written only by explicit
   actions — generate, add a row, reset — and NEVER from the editor's own return
   value on an ordinary rerun. That last part is the "double-input anti-pattern"
   the version-matched Streamlit skill names by name.

3. `st.session_state[key]` FOR A data_editor IS AN EDIT-DELTA DICT
   (`edited_rows` / `added_rows` / `deleted_rows`), keyed by row POSITION rather
   than index label. It is not the table's contents. The RETURN VALUE is.

4. A COMPUTED COLUMN INSIDE THE EDITOR IS ALWAYS ONE RERUN STALE, because the
   proto is enqueued before the edits are applied. So "Invested" is not a column
   here. It is computed from the return value and rendered beneath as the
   semantic table this app already builds — which is both live and reachable by a
   screen reader.

No `st.form`, deliberately — but not for the reason first written here. `st.stop()`
truncates the script, it does not shorten it: everything ABOVE the takeover still
re-executes on every cell edit, including the whole sidebar. Measured on the
fixture that is ~25-50ms a keystroke, which is a fair price for live per-row
validation on a screen whose entire job is catching a bad row. In live mode the
cached market fetches hide it until a TTL rolls over mid-edit, which is the real
cost and the reason to revisit this if it ever bites.

AppTest cannot see or drive a `data_editor` at all, so `ss.builder_draft` being
app-owned is also the only reason this flow is testable.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import book_source
import book_spec
import portfolio as pf
import shelf
import theme

_FLAG = "show_builder"
DRAFT = "builder_draft"
CASH = "builder_cash"
ANSWERS = "builder_answers"
FREE_TEXT = "builder_free_text"
INVESTABLE = "builder_investable"
GENERATED = "builder_generated"
EDITOR_KEY = "builder_editor"

COLUMNS = ("ticker", "shares", "cost_basis")

STARTER_ROWS = 3


# --------------------------------------------------------------------------
# Open / close
# --------------------------------------------------------------------------

def is_open() -> bool:
    return bool(st.session_state.get(_FLAG))


def open_button(*, key: str = "build_btn") -> None:
    if st.button(":material/add_chart: Build a portfolio", key=key,
                 use_container_width=True,
                 help="Type your holdings in, or answer a few questions and "
                      "have an example book drafted for you."):
        st.session_state[_FLAG] = True
        _reset()
        st.rerun()


def close() -> None:
    st.session_state[_FLAG] = False


def _defaults() -> dict:
    return {
        DRAFT: [{"ticker": None, "shares": None, "cost_basis": None}
                for _ in range(STARTER_ROWS)],
        CASH: 0.0,
        ANSWERS: book_spec.default_answers(),
        FREE_TEXT: "",
        INVESTABLE: 20_000.0,
        GENERATED: None,
    }


# Every widget key this surface owns. Streamlit lets a surviving widget key beat
# the `value=`/`index=`/`default=` argument (`key_as_main_identity=True`), so a
# reset that clears only the mirrors clears nothing a reader can see.
_WIDGET_KEYS = ("bq_include", "bq_exclude", "bq_free", "bq_investable",
                "builder_cash_input", EDITOR_KEY)


def _reset() -> None:
    """Start over — and actually start over.

    This used to `ss.update(_defaults())` and pop the editor key alone, which
    reset the table and NOTHING ELSE. Reproduced end to end: after "Start over"
    all six radios were still selected, cash was still 777, the free text was
    still there, and — because the answers dict is repopulated from the
    surviving widgets on the very next line of the render — "Draft a book" was
    still enabled. It even LOOKED right, since clearing `GENERATED` springs the
    questionnaire expander back open over a form that is still full.

    The "open the builder" path only appeared to work: with the builder closed
    those widgets are not rendered, so Streamlit garbage-collects them itself.
    """
    ss = st.session_state
    ss.update(_defaults())
    for key in _WIDGET_KEYS:
        ss.pop(key, None)
    for q in book_spec.QUESTIONS:
        ss.pop(f"bq_{q['id']}", None)


def _seed_if_missing() -> None:
    """Seed each key INDEPENDENTLY, not all-or-nothing on one of them.

    The first version keyed the whole reset off `builder_draft` alone. Anything
    that set only some of the state — a test seeding a draft, or a future entry
    point that opens the builder with rows already in it — then reached the
    questionnaire with `builder_answers` absent and took the page down with a
    KeyError. Per-key seeding makes any subset of state valid to arrive with.
    """
    ss = st.session_state
    for key, value in _defaults().items():
        if key not in ss:
            ss[key] = value


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def render(on_commit) -> None:
    """The whole builder. `on_commit(portfolio, source)` installs the result."""
    ss = st.session_state
    _seed_if_missing()

    back, _ = st.columns([1, 5])
    with back:
        if st.button(":material/arrow_back: Back", use_container_width=True):
            close()
            st.rerun()

    theme.section("Build a portfolio")
    st.caption("Type your holdings in below, or answer a few questions and have "
               "an example book drafted for you. Nothing becomes your portfolio "
               "until you say so.")

    _render_questionnaire()
    _render_tensions_before_generation()

    generated = ss.get(GENERATED)
    # Reserved ABOVE the table but filled AFTER it, so the tensions describe the
    # rows as edited rather than as drafted. They used to measure `builder_draft`
    # — which is deliberately never written from the editor — so deleting the
    # bond sleeve and committing shipped a PDF asserting "this book's beta is
    # 1.42" about a book that no longer existed. Those numbers are the feature's
    # central claim to be arithmetic the reader can check; attached to the wrong
    # book they are worse than no numbers at all.
    notice_slot = st.container()

    edited = _render_table()
    rows = _rows_from(edited)
    issues = pf.validate_rows(rows, universe=shelf.tickers())

    if generated:
        with notice_slot:
            _render_generated_notice(generated, rows)

    _render_totals(rows, issues)
    _render_commit(rows, issues, on_commit)


# --------------------------------------------------------------------------
# The questionnaire
# --------------------------------------------------------------------------

def _md(text) -> str:
    """Escape `$` for Streamlit's markdown, the way `theme.fmt_money_md` does.

    A bare `$` opens a LaTeX span, so a string containing TWO of them silently
    swallows everything between. Caught by rendering it: the loss-limit question
    reached the page as

        Say you put in 10,000 and four months later it is worth 7,000

    — both amounts gone, and the question that carries the most signal in the
    instrument reduced to nonsense. It reads perfectly well in the source.

    The escaping belongs HERE and not in `book_spec`, because the same strings
    also go into the PDF, where reportlab has no LaTeX parser and a `\\$` would
    print the backslash. One string, two media, two boundaries — the same split
    `theme.safe` and `report.pdf_safe` already keep.
    """
    return str(text or "").replace("$", "\\$")


def _render_questionnaire() -> None:
    ss = st.session_state
    answers = ss[ANSWERS]

    with st.expander("Describe yourself as an investor, and have a book drafted",
                     expanded=not ss.get(GENERATED)):
        st.caption("Every book drafted here is a **demonstration** put together "
                   "from a fixed shelf of holdings, so you have something of "
                   "your own to explore the app with. It is not a "
                   "recommendation, and you can change every row of it below "
                   "before using it.")

        # Split in HALVES, not alternating. `st.columns` emits column-major
        # order, so `i % 2` put the questions on screen and in the a11y tree as
        # purpose, loss_limit, experience, horizon, behaviour, concentration —
        # which separates the loss-limit and behaviour items that are designed
        # as a pair and read as one question followed by its follow-up.
        left, right = st.columns(2)
        _half = (len(book_spec.QUESTIONS) + 1) // 2
        for i, q in enumerate(book_spec.QUESTIONS):
            with (left if i < _half else right):
                labels = [_md(o["label"]) for o in q["options"]]
                keys = [o["key"] for o in q["options"]]
                current = answers.get(q["id"])
                # index=None so nothing is pre-selected. A pre-selected answer
                # is an answer the reader did not give, which is the same defect
                # the missing "neither agree nor disagree" rung avoids.
                idx = keys.index(current) if current in keys else None
                picked = st.radio(_md(q["prompt"]), labels, index=idx,
                                  key=f"bq_{q['id']}", help=_md(q.get("help")))
                answers[q["id"]] = keys[labels.index(picked)] if picked else None

        c1, c2 = st.columns(2)
        with c1:
            answers["include_categories"] = st.multiselect(
                "Would like included", list(shelf.CATEGORIES),
                default=answers.get("include_categories") or [],
                key="bq_include",
                help="Leave empty for no preference.")
        with c2:
            answers["exclude_categories"] = st.multiselect(
                "Definitely out", list(shelf.CATEGORIES),
                default=answers.get("exclude_categories") or [],
                key="bq_exclude",
                help="Anything here will be at zero, not merely underweight.")

        ss[FREE_TEXT] = st.text_area(
            book_spec.FREE_TEXT["prompt"], value=ss.get(FREE_TEXT, ""),
            max_chars=book_spec.FREE_TEXT["max_chars"], key="bq_free",
            placeholder="For example: I work in software and already have a lot "
                        "riding on technology, so I would rather not add more.")

        ss[INVESTABLE] = float(st.number_input(
            "How much to put to work", min_value=100.0, step=500.0,
            value=float(ss.get(INVESTABLE, 20_000.0)), key="bq_investable",
            help="Used to turn the drafted weights into a number of shares at "
                 "today's closing prices."))

        ss[ANSWERS] = answers
        left_missing = book_spec.missing(answers)
        if left_missing:
            st.caption(f":material/info: {len(left_missing)} question"
                       f"{'s' if len(left_missing) != 1 else ''} still to answer.")

        if st.button(":material/auto_awesome: Draft a book from this",
                     type="primary", disabled=bool(left_missing),
                     use_container_width=True):
            _generate()
            st.rerun()


def _generate() -> None:
    """Draft a book and put it IN THE TABLE, not into the portfolio."""
    ss = st.session_state
    from agents import book_builder
    import data_layer

    answers = ss[ANSWERS]
    # Spinner, like reporting/panel.py's "Rendering…". This is an 8000-token
    # model call with two retries plus a price lookup per holding; on a cold
    # Cloud start that is tens of seconds behind nothing but the top-right
    # running indicator.
    try:
        with st.spinner("Drafting a book from your answers…"):
            book = book_builder.draft_example_book(
                answers, ss.get(FREE_TEXT, ""),
                float(ss.get(INVESTABLE, 20_000.0)))
    except Exception as e:  # noqa: BLE001 — never take the builder down
        st.error(f"Couldn't draft a book: {e}")
        return

    # get_context_batch, not a loop of get_context: in live mode a thirteen
    # holding book was thirteen sequential yfinance round trips inside a button
    # handler. `_measure` already batches.
    prices = {}
    try:
        ctx = data_layer.get_context_batch([i["ticker"] for i in book["allocation"]])
        for tk, c in (ctx or {}).items():
            price = ((c or {}).get("price") or {}).get("current")
            if price:
                prices[tk] = price
    except Exception:  # noqa: BLE001 — an unpriceable name is simply dropped
        pass

    # Allocation weights are a share of the INVESTED money and sum to 100; cash
    # is a share of the whole book and sits outside them. So the amount actually
    # put to work is the total less the cash.
    total = float(ss.get(INVESTABLE, 20_000.0))
    cash = round(total * float(book.get("cash_pct") or 0.0) / 100.0, 2)
    try:
        drafted = pf.from_weights(book["allocation"], prices, total - cash,
                                  sector_for=shelf.sector_of)
    except pf.PortfolioError as e:
        st.error(str(e))
        return

    # Only here does the frame under the editor change — an explicit action,
    # never an incidental rerun. See note 2 in the module docstring.
    ss[DRAFT] = [{"ticker": p["ticker"], "shares": p["shares"],
                  "cost_basis": p["cost_basis"]} for p in drafted["positions"]]
    ss[CASH] = cash
    ss[GENERATED] = book
    ss.pop(EDITOR_KEY, None)


def _render_tensions_before_generation() -> None:
    """Answer-vs-answer tensions, shown while the reader can still change one."""
    answers = st.session_state.get(ANSWERS) or {}
    if book_spec.missing(answers):
        return
    for t in book_spec.answer_tensions(answers):
        _render_tension(t)


def _render_tension(t: dict) -> None:
    theme.notice(
        f"<b>You said</b> {theme.safe(t['said'])} · "
        f"<b>and</b> {theme.safe(t['found'])}.<br>{theme.safe(t['text'])}",
        kind="info" if t.get("severity") == "note" else "warn")


def _render_generated_notice(book: dict, rows: list) -> None:
    ss = st.session_state
    label = "a rule-based allocator" if book.get("is_mock") else "the model"
    theme.notice(
        f"<b>Drafted by {label}.</b> {theme.safe(book.get('notice') or '')}<br>"
        f"This is a demonstration book, not a recommendation. Edit any row "
        f"below before using it.", kind="info")
    if book.get("tagline"):
        st.caption(f":material/insights: {theme.safe_md(book['tagline'])}")

    # Book-vs-answers tensions: computed here in Python against the real
    # metrics, never asserted by the model about its own output.
    measured = _measure(rows)
    if measured:
        for t in book_spec.book_tensions(
                ss.get(ANSWERS) or {},
                book_spec.constraints(ss.get(ANSWERS) or {}), measured):
            _render_tension(t)

    if book.get("constraints_applied"):
        with st.expander("What had to be adjusted"):
            for line in book["constraints_applied"]:
                st.caption(f"· {theme.safe_md(line)}")


def _measure(rows: list) -> dict:
    """hhi / max_weight / beta / max_drawdown for the drafted rows.

    Every one of these comes from `portfolio_metrics`, so a tension names a
    number the reader could go and check on the Dashboard a moment later.
    """
    try:
        import data_layer
        import portfolio_metrics as pm
        import numpy as np

        clean = [r for r in rows if r.get("ticker") and r.get("shares")]
        if not clean:
            return {}
        book = pf.build_portfolio(clean, sector_for=shelf.sector_of)
        tickers = [p["ticker"] for p in book["positions"]]
        contexts = data_layer.get_context_batch(tickers)
        df = pm.position_values(book, contexts)
        weights = {r.ticker: r.weight_pct / 100.0 for r in df.itertuples()
                   if np.isfinite(r.weight_pct)}
        if not weights:
            return {}
        spy = data_layer.get_benchmark_history("SPY")
        out = {"hhi": pm.diversification_score(weights).get("hhi"),
               "max_weight": max(weights.values())}
        out["beta"] = (pm.market_model(contexts, weights, spy) or {}).get("beta")
        out["max_drawdown"] = (pm.risk_metrics(contexts, weights, spy)
                               or {}).get("max_drawdown")
        return out
    except Exception:  # noqa: BLE001 — a tension we cannot compute is simply not shown
        return {}


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------

def _frame() -> pd.DataFrame:
    rows = st.session_state.get(DRAFT) or []
    return pd.DataFrame(
        [{c: r.get(c) for c in COLUMNS} for r in rows] or
        [{c: None for c in COLUMNS}],
        columns=list(COLUMNS))


def _render_table():
    theme.section("Your holdings")
    st.caption("One row per holding. Pick a ticker, then how many shares you "
               "hold and what you paid per share — the amount invested is worked "
               "out for you.")

    return st.data_editor(
        _frame(),
        key=EDITOR_KEY,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.SelectboxColumn(
                "Ticker", options=shelf.tickers(), required=False,
                help="Pick from the shelf this app has market data for, so "
                     "every holding can be priced — including offline."),
            # NO format= on either number column. See note 1 above: it would
            # paint a rounded currency string while announcing the raw float.
            "shares": st.column_config.NumberColumn(
                "Shares", min_value=0.0, step=1.0),
            "cost_basis": st.column_config.NumberColumn(
                "Cost per share", min_value=0.0, step=1.0),
        })


def _rows_from(edited) -> list:
    """The editor's RETURN VALUE as plain rows. Never session_state[key].

    Each row keeps the position it occupies IN THE EDITOR (`_row`), because
    blank rows are skipped here and the validator's indices would otherwise
    address a different row than the one the reader is looking at — a bad entry
    in visible row 3 was reported as "Row 1".
    """
    if edited is None or not hasattr(edited, "to_dict"):
        return []
    out = []
    for i, r in enumerate(edited.to_dict("records")):
        # pd.isna, not falsiness: once a book is drafted the frame is float64 and
        # a blank added row comes back as NaN, and `bool(nan)` is True. The rows
        # were dropped later by the validator anyway, so nothing was visibly
        # wrong — but the guard did not do what it reads as doing.
        if all(pd.isna(r.get(c)) or r.get(c) == "" for c in COLUMNS):
            continue
        row = {c: r.get(c) for c in COLUMNS}
        row["_row"] = i
        out.append(row)
    return out


# --------------------------------------------------------------------------
# Totals, computed from the return value so they are never a rerun stale
# --------------------------------------------------------------------------

def _render_totals(rows: list, issues: list) -> None:
    ss = st.session_state

    priced = []
    invested = 0.0
    for r in rows:
        try:
            shares = float(r.get("shares") or 0)
            cost = float(r.get("cost_basis") or 0)
        except (TypeError, ValueError):
            continue
        if r.get("ticker") and shares > 0 and cost >= 0:
            amount = shares * cost
            invested += amount
            priced.append((r["ticker"], shares, cost, amount))

    if priced:
        head = "".join(f"<th scope='col'>{h}</th>"
                       for h in ("Ticker", "Shares", "Cost per share", "Invested",
                                 "Share of book"))
        body = []
        for ticker, shares, cost, amount in priced:
            pct = (100.0 * amount / invested) if invested else 0.0
            body.append(
                "<tr>"
                f"<th scope='row'>{theme.safe(ticker)}</th>"
                f"<td>{shares:,.2f}</td>"
                f"<td>{theme.fmt_money(cost)}</td>"
                f"<td>{theme.fmt_money(amount)}</td>"
                f"<td>{pct:.1f}%</td>"
                "</tr>")
        st.markdown(
            "<div class='rs-table-wrap'><table class='rs-table'>"
            "<caption>What you have entered, priced at your own cost basis. "
            "Invested is shares multiplied by cost per share.</caption>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
            "</table></div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        ss[CASH] = float(st.number_input(
            "Cash to hold", min_value=0.0, step=100.0,
            value=float(ss.get(CASH, 0.0) or 0.0), key="builder_cash_input",
            help="Not counted in any weight, sector split or beta."))
    with c2:
        st.metric("Invested", theme.fmt_money(invested))
    with c3:
        st.metric("Book value", theme.fmt_money(invested + ss[CASH]))

    for issue in issues:
        # The editor's own row number, not the index within the filtered list.
        shown = rows[issue["row"]].get("_row", issue["row"]) if issue["row"] < len(rows) \
            else issue["row"]
        st.error(f"Row {shown + 1}: {issue['message']}")


def _profile_for_report(generated: dict, rows: list) -> dict:
    """The questionnaire as the PDF states it back. No free text — see below.

    A reader of the exported report gets the reasoning chain: what was answered,
    what those answers required numerically, and where the resulting book pulls
    against them. What they do not get is the author describing themselves in
    their own words, because this document exists to be forwarded and that
    sentence is nobody else's business by default.
    """
    ss = st.session_state
    answers = ss.get(ANSWERS) or {}
    constraints = book_spec.constraints(answers)

    pairs = []
    for q in book_spec.QUESTIONS:
        opt = book_spec.option(q["id"], answers.get(q["id"]))
        if opt:
            pairs.append((q["prompt"], opt["label"]))
    for label, key in (("Would like included", "include_categories"),
                       ("Wants excluded", "exclude_categories")):
        picked = answers.get(key) or []
        if picked:
            pairs.append((label, ", ".join(picked)))

    bounds = [line.lstrip("- ").strip()
              for line in book_spec.describe_constraints(constraints).splitlines()
              if line.strip()]

    tensions = list(book_spec.answer_tensions(answers))
    measured = _measure(rows)
    if measured:
        tensions += book_spec.book_tensions(answers, constraints, measured)

    return {"answers": pairs, "bounds": bounds, "tensions": tensions,
            "note": (generated or {}).get("notice")}


def _render_commit(rows: list, issues: list, on_commit) -> None:
    usable = [r for r in rows if r.get("ticker")]
    blocked = bool(issues) or not usable

    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button(":material/check: Use this portfolio", type="primary",
                     use_container_width=True, disabled=blocked):
            try:
                book = pf.build_portfolio(
                    rows, cash=float(st.session_state.get(CASH, 0.0) or 0.0),
                    sector_for=shelf.sector_of, universe=shelf.tickers(),
                    empty_message="Add at least one holding first.")
            except pf.PortfolioError as e:
                st.error(str(e))
                return
            generated = st.session_state.get(GENERATED)
            source = (book_source.drafted((generated or {}).get("notice"))
                      if generated else book_source.built())
            # Computed BEFORE the commit (it reads the builder's own state) but
            # written AFTER it, because `_load` clears the key so a stale
            # questionnaire cannot follow a book that replaced the drafted one.
            profile = _profile_for_report(generated, rows) if generated else None
            on_commit(book, source=source)
            st.session_state["portfolio_profile"] = profile
            close()
            st.rerun()
    with c2:
        if st.button("Start over", use_container_width=True):
            _reset()
            st.rerun()

    if not usable:
        st.caption(":material/info: Add a holding, or draft a book above.")
