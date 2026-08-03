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

## Dependencies, and the one that is deliberately optional

`requirements.txt` is pinned and deliberately lean. Two notes:

- **`reportlab` and `svglib`** are pure Python and produce the PDF export — the cover,
  the tables, and the logos as embedded vectors. They install fine on Cloud.
- **`kaleido`** renders Plotly charts into the PDF and is scoped
  `platform_system != "Linux"`, so **Community Cloud does not install it**. It drives a
  real headless Chrome, which the container does not have and should not be made to
  download mid-demo.

  This is not a defect. `report.py` treats charts as an enhancement: without the engine
  the export still produces a complete document and prints one line saying the charts
  could not be rendered. Tests pin that path, and it was verified by simulating the
  import failure. **To get charts in the PDF, generate it locally** — which is the machine
  where a report's figures are worth producing anyway.

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

## Confirming a deploy actually worked

Reload the app and check, in order:

1. **It boots at all** — a `ModuleNotFoundError` here is almost always the `add -A` trap.
2. **The line under the title** reads *"Live market data · prices as of the close on …"*.
   If it says **recorded snapshot**, the API key or the secrets bridge is not working —
   the app is serving canned output and looking fine.
3. **The tab icon and sidebar** show the seal.
4. **Bull vs Bear** actually calls the model rather than replaying `mock_debate.json`.
5. **Dashboard → Export → Generate PDF report** produces a file. On Cloud it will
   correctly say charts are excluded; the tables and the debate must still be there.

---

## Secrets hygiene

`.env` is gitignored and must stay that way. `.env.example` documents the keys with no
values. If a key has ever been pasted into a shared transcript or a zip, rotate it at
<https://console.anthropic.com/settings/keys> before submission.
