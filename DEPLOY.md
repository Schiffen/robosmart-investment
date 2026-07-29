# Deploying RoboSmart to Hugging Face Spaces

Follow these in order. Steps 0–2 are on your machine; 3–5 need your Hugging Face
account; 6–7 confirm it actually works.

Times assume a normal connection. Total: about 25 minutes, most of it waiting for the
first build.

---

## Step 0 — Rotate the Anthropic API key (do this first)

**Why first:** `.env` in this folder contains a live-looking key. This folder is not a
git repo, so `~/Downloads/robosmart_FULL_project.zip` almost certainly contains that
key in plaintext, and `README.md` currently claims no secrets are committed. Treat the
current key as compromised.

1. Go to <https://console.anthropic.com/settings/keys>
2. Find the key currently in your `.env` and click **Delete** (or Revoke).
3. Click **Create Key**, name it something like `robosmart-hf-space`, and copy it.
   You will not be able to view it again — paste it somewhere safe for Step 5.
4. Update your local `.env` so you can still run the app locally:

   ```bash
   cd "/Users/schiffen/Downloads/robosmart 3"
   # replace the ANTHROPIC_API_KEY line with the new key
   open -e .env
   ```

5. Delete the old zip so the dead key stops circulating:

   ```bash
   rm ~/Downloads/robosmart_FULL_project.zip
   ```

Do **not** skip this. Everything below assumes the key in `.env` is the new one.

---

## Step 1 — Optional: slim the image and drop dev-only files

Not required, but `statsmodels` is pinned and imported nowhere, and it drags in `scipy`:
**151 MB of your Space image for zero functionality** (every regression in this project
is hand-rolled in numpy). To remove it:

```bash
cd "/Users/schiffen/Downloads/robosmart 3"
grep -v '^statsmodels' requirements.txt > /tmp/req && mv /tmp/req requirements.txt
.venv/bin/python -m pytest -q          # confirm still 38 passed
```

Also consider excluding these from the Space — they are development artifacts, not part
of the deliverable:

| File | Why |
|---|---|
| `_preview_app.py` | dev harness; assumes cwd is the repo root |
| `data_layer_mock.py` | only used by two tests, never by the app |
| `docs/summary_document_long.md` | the pre-trim draft, kept for reference |
| `mock_context.json` | 377 KB, loaded by nothing at runtime |

Keeping them does no harm beyond image size — your call.

---

## Step 2 — Initialise git and prove no secrets are going up

```bash
cd "/Users/schiffen/Downloads/robosmart 3"
git init -b main
git add -A

# THE CRITICAL CHECK — .env must not appear in this list:
git status --short | grep -E "\.env$|secrets" && echo "!! STOP: a secret is staged" || echo "OK: no secrets staged"

# Second check — no key string anywhere in what you're about to commit:
git diff --cached | grep -i "sk-ant-" && echo "!! STOP: key found in diff" || echo "OK: no key in diff"

git commit -m "RoboSmart Investment — portfolio analysis app with AI debate and factor attribution"
```

If either check prints `!! STOP`, do not continue. `.gitignore` already lists `.env`,
so this should pass — the checks exist because "should" is not "did."

---

## Step 3 — Create the Space

1. Go to <https://huggingface.co/new-space>
2. Fill in:
   - **Owner:** your username
   - **Space name:** `robosmart-investment`
   - **License:** MIT (or whatever your course requires)
   - **SDK:** **Streamlit** ← must be Streamlit, not Gradio or Docker
   - **Hardware:** **CPU basic (free)** — this app needs no GPU
   - **Visibility:** **Public** (the assignment requires a public link)
3. Click **Create Space**.

You do **not** need to configure the Streamlit version in the UI — Hugging Face reads it
from the YAML front-matter already at the top of `README.md`:

```yaml
sdk: streamlit
sdk_version: 1.60.0
app_file: app.py
```

---

## Step 4 — Push the code

Hugging Face no longer accepts your account password over git. Create a write token:

1. <https://huggingface.co/settings/tokens> → **Create new token** → type **Write** →
   copy it.

Then push (replace `YOUR_USERNAME`):

```bash
cd "/Users/schiffen/Downloads/robosmart 3"
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/robosmart-investment
git push space main
```

When prompted:
- **Username:** your Hugging Face username
- **Password:** paste the **write token** (not your account password)

The Space will start building immediately. Watch the **Logs** tab. First build takes
3–8 minutes while it installs pandas, numpy, plotly and yfinance.

---

## Step 5 — Add the API key as a Space secret

The two AI tabs need this. Without it the app still runs — it falls back to recorded
demo output, banner-labelled in the UI — but a grader will not see a live debate.

1. Open your Space → **Settings**
2. Scroll to **Variables and secrets** → **New secret**
3. **Name:** `ANTHROPIC_API_KEY` — exactly this, case-sensitive, no quotes, no spaces
4. **Value:** the new key from Step 0
5. **Save**, then **Settings → Factory rebuild** so the running container picks it up.

> A secret added without a rebuild will not reach the process. If the debate tab still
> shows the demo banner after saving, that is why.

---

## Step 6 — Verify, and know the one real risk

Open your Space URL and check, in order:

- [ ] The dashboard loads with **real numbers**, not `N/A` (allow ~20s on first load —
      it makes about 24 Yahoo requests for the 7-holding demo book)
- [ ] The sidebar shows **"Active ticker (tabs 2 & 3)"** with a dropdown
- [ ] **Bull vs Bear** → Start the Debate → arguments stream in with **no** demo-mode
      banner (a banner means the secret isn't reaching the process — redo Step 5)
- [ ] Switch the ticker to JNJ and run again — the debate should be about
      Johnson & Johnson, not NVIDIA
- [ ] **What Happened Today** → Explain → the cited headline mentions the company

**The genuine risk: Yahoo Finance rate-limiting.** `yfinance` is an unauthenticated
scraper, and Yahoo throttles datacenter IP ranges more aggressively than home
connections. Your Space shares its IP with other Hugging Face workloads. Symptoms are
`N/A` metrics or a "Ticker not found" error that does not reproduce locally.

Mitigations, cheapest first:
1. Reload. The 15-minute `st.cache_data` TTL means a successful load stays warm.
2. Open the Space and let it warm up a few minutes *before* your demo or defence.
3. **Set `USE_MOCK_DATA=1` as a Space variable.** The app then serves the recorded
   snapshot in `market_data/fixtures/market_data.json` — real prices, real headlines,
   zero Yahoo requests — while the AI tabs stay live. The sidebar states the snapshot
   date, so nothing is passed off as live. Re-record before the demo with
   `python -m market_data.refresh`.
4. If it is throttled persistently, record the demo video locally, where it works
   reliably. The assignment asks for a deployed link *and* a video — the video does not
   have to be screen-recorded from the deployed instance.

> Note: this is a *manual* switch. There is deliberately no automatic fallback — an app
> that silently serves stale prices when the network hiccups is worse than one that
> visibly degrades.

---

## Step 7 — Put the live URL in the README

`README.md` line 16 still has a placeholder. Replace it:

```bash
cd "/Users/schiffen/Downloads/robosmart 3"
open -e README.md    # change: **Live app:** _<add your Hugging Face Space URL here>_
                     # to:     **Live app:** https://huggingface.co/spaces/YOUR_USERNAME/robosmart-investment
git add README.md && git commit -m "Add live Space URL" && git push space main
```

Then hand in:

| Deliverable | Where it is |
|---|---|
| Summary PDF (≤5 pages) | `docs/summary_document.pdf` — rebuild with `./docs/build_pdf.sh` |
| Public repo + README + requirements.txt | the Space repo itself satisfies this, or mirror to GitHub |
| Live deployed app | your Space URL |
| Demo video (3–5 min) | script in `docs/video_script.md` |
| Student-app survey | the Google Form link in the assignment PDF (5% of the grade) |

---

## If the build fails

| Log message | Cause and fix |
|---|---|
| `sdk_version 1.60.0 is not available` | HF dropped that Streamlit build. Bump `sdk_version` in the README front-matter to a version HF lists, run `pytest` locally against it, and push. |
| `ModuleNotFoundError: No module named 'X'` | `X` is missing from `requirements.txt`. Note `yfinance` and `anthropic` are imported lazily *inside* functions, so they will not surface until a tab is opened — both are already pinned. |
| App loads but every metric is `N/A` | Yahoo throttling, not a code bug. See Step 6. |
| Debate tab shows the demo-mode banner | The secret is missing or misnamed, or you skipped the factory rebuild. Redo Step 5. |
| `Repository not found` on push | Wrong username in the remote URL, or you used your password instead of a write token. |
