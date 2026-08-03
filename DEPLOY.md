# Deploying RoboSmart Debate Club

Target: **Streamlit Community Cloud**. Deploy is a `git push` — the platform pulls the
repo, installs `requirements.txt`, and runs `app.py`.

> **This file used to describe Hugging Face Spaces. That route is dead.** HF removed the
> Streamlit SDK (`sdk` now accepts only `gradio|docker|static`) and put Docker Spaces
> behind a PRO subscription. A working `Dockerfile` is still in the repo as a fallback,
> but nothing uses it.

---

## The one-time setup

Already done for this repo, recorded so it can be rebuilt:

1. <https://share.streamlit.io> → **New app** → pick the GitHub repo, branch `main`,
   main file `app.py`.
2. **Advanced settings → Secrets**, in TOML:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

   Community Cloud exposes these through `st.secrets` and **does not set them as
   environment variables**. `app.py::_adopt_streamlit_secrets()` bridges the gap. Without
   it the deployed app finds no key and quietly serves **recorded** AI output while looking
   completely healthy — the worst failure mode available, because nothing errors. Two tests
   guard this.

---

## Every deploy after that

```bash
git add -A            # NOT `commit -am` — see below
git commit -m "..."
git push
```

Then wait ~2–5 minutes and reload the app URL.

### Why `git add -A` and not `git commit -am`

`-am` stages **modified tracked files only**. New files are invisible to it. `app.py`
imports `about`, `brand` and `report`, and `brand` reads `logos/` — all of which were
untracked when first written. A `commit -am` therefore pushes a modified `app.py` without
the modules it imports, and the deploy dies on boot with:

```
ModuleNotFoundError: No module named 'about'
```

There is no warning locally, because locally the files exist. Verify what a deploy would
actually receive:

```bash
git status --short          # anything with ?? is NOT going to be deployed
```

---

## Dependencies

`requirements.txt` is pinned and deliberately lean. The PDF export adds three, all pure
Python, all installing cleanly on Cloud: **reportlab** and **svglib** build the document
and embed the marks as vectors; **matplotlib** draws the figures.

**Not kaleido.** It is the obvious way to rasterise a Plotly figure and it fails three
ways: 0.2.1 ships no macOS arm64 binary, 1.x refuses Plotly 5.24 through `fig.to_image()`,
and 1.x drives a **real headless Chrome** that Community Cloud does not have. That last one
left the deployed export with tables and no charts. `reporting/charts.py` redraws the same
DataFrames with matplotlib instead — no browser, and ~0.5s against kaleido's ~7s.

---

## After every push: verify the LIVE app, not the local tree

A clean local checkout of HEAD booting is **not** evidence the deploy worked. That check
passed, and the deployed app was down at the same moment.

**How it fails:** Community Cloud re-runs `app.py` on a push but can keep an
already-imported module in `sys.modules`. A deploy that adds a NEW function to an existing
module lands new `app.py` against the OLD module. `brand.masthead()` resolved and
`brand.page_title()` did not — same module, same commit, same file. Git was perfectly
consistent; the container was not.

Open the URL and check, in this order:

1. **It renders** — no `AttributeError` traceback where the dashboard should be. The
   header is now guarded so this degrades to a typeset title instead of an outage, but a
   guard firing still means something is stale.
2. **"Live market data · prices as of the close on …"** — if it reads *Recorded snapshot*,
   the API key is not reaching the app and it is serving canned AI while looking healthy.
3. **Export → Build the report** — the size line is the tell. **~340 KB means the charts
   are in there**; ~10 KB means it fell back to a chartless document.

If the app is stale rather than broken, **Manage app → Reboot app** forces a clean
interpreter.

---
## Running it locally

```bash
.venv/bin/streamlit run app.py        # → http://localhost:8501
```

Live market data, and live Anthropic if `ANTHROPIC_API_KEY` is in `.env`. Use
`.venv/bin/python` (3.12) — pandas 2.2.3 segfaults on the system 3.14.

Run modes (`run_mode.py`): `USE_MOCK=1` for fully offline, `USE_MOCK_DATA=1` to freeze the
market while iterating on prompts, `USE_MOCK_LLM=1` for the reverse.

---

## Secrets hygiene

`.env` is gitignored and must stay that way. `.env.example` documents the keys with no
values. If a key has ever been pasted into a shared transcript or a zip, rotate it at
<https://console.anthropic.com/settings/keys> before submission.
