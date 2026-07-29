# RoboSmart Investment — Demo Video Script

**Target length:** 4:00 · **Hard cap:** 5:00
**Format:** screen recording with voiceover
**Demo ticker:** NVDA (see pre-recording checklist for why)
**Golden rule:** open on the *problem*, show don't tell, end on the Judge's
falsifiers.

Each beat below gives a timestamp, the **narration** to read aloud (natural
spoken register — read it, don't recite it), and an **on-screen / action** note
for what to show and click.

---

## Full script (target 4:00)

### 0:00 – 0:12 — The hook (the problem, not the tech)

**Narration:**
> "Here's your portfolio. It's up eight tenths of a percent today. Okay — *why*?
> Your broker won't tell you. And if you ask an AI chatbot, it'll happily invent a
> reason. One tool gives you numbers with no meaning; the other gives you meaning
> with no numbers. We built the thing in the middle."

**On screen / action:** Cold-open on the Portfolio Dashboard already loaded — the
big value and P&L number visible, nothing clicked yet. No title card, no stack
intro. Let the number sit for a beat as you say "Okay — why?"

### 0:12 – 0:25 — What RoboSmart is (one sentence)

**Narration:**
> "This is RoboSmart. You upload a portfolio as a CSV, and it gives you three
> things: an honest dashboard, an AI debate about any holding, and a daily
> explanation of what actually moved your stocks — where every claim is tied to a
> real number."

**On screen / action:** Briefly show the three tab headers at the top —
Dashboard, Bull vs Bear, What Happened Today — hovering the cursor across them.
Don't click yet.

### 0:25 – 1:05 — Dashboard: numbers that interpret themselves

**Narration:**
> "Start with the dashboard. This isn't just a table — it reads its own numbers.
> It's flagging that Technology is fifty-six percent of the book — that's a
> concentration warning, not a footnote. The portfolio beta is about one-point-three
> with an R-squared near ninety percent, so this book basically *is* the market,
> amplified. And look here — effective holdings: about five-point-six out of seven.
> You *think* you own seven names; you're really diversified like you own five and a
> half. This gold position? Negatively correlated to your stocks — that's the one
> thing actually protecting you."

**On screen / action:** Scroll slowly. Pause on the **Technology 56% concentration
flag** as you say it. Pause on the **beta / R²** figures. Pause on **effective
holdings ≈ 5.6**. Finally hover the **GLD** row/cell in the correlation heatmap
where it reads negative (a different color from the rest). Let each number land
under the cursor as you name it.

### 1:05 – 2:35 — Bull vs Bear (the centerpiece — give it the most time)

**Narration (setup, ~10s):**
> "Now the part I actually want to show you. Pick any holding, and three AI agents
> debate it — a Bull, a Bear, and a Judge — over five rounds. Two rules matter:
> every claim has to cite a number from *your* data, and the Bear is never allowed
> to give up. No polite AI agreement."

**On screen / action:** Click **Bull vs Bear**, select **NVDA**, start the debate.

**Narration (progressive reveal — let the transcript breathe, ~50s):**
> "Watch it build. The Bull opens on the fundamentals — and notice, it's citing the
> actual beta, the actual P&L, not vibes. The Bear comes back on the fifty-six
> percent tech concentration and that one-point-three beta cutting *both* ways… and
> the Bull answers… and the Bear presses again — it can't concede, so it has to find
> a real counter every single round. This is the disagreement most AI tools smooth
> away."

**On screen / action:** Let the rounds stream in. As each turn appears, briefly
highlight (cursor-select) the *number* being cited in that turn — beta, the 56%,
P&L — so the viewer sees the grounding rule working live. Don't rush; this reveal
is the emotional core of the demo. Scroll to keep the newest turn in frame.

**Narration (the Judge — land on the falsifiers, ~30s):**
> "Then the Judge. And here's what makes this honest: the Judge is allowed to say
> *inconclusive* — it doesn't have to crown a winner. But the real payoff is this:
> it has to give three falsifiers. Three specific things that would change its mind.
> That's not an opinion you take on faith — it's a watch-list. If *this* number
> breaks, the bull case is wrong. That's a conclusion you can actually check."

**On screen / action:** Scroll to the Judge's verdict. Pause on the verdict line
(especially if it reads "inconclusive"). Then slowly reveal the **three
falsifiers**, cursor resting on each one in turn. Hold on the falsifiers — this is
the closing image of the whole video, so let it sit.

### 2:35 – 3:35 — What Happened Today (incl. the honesty beat)

**Narration (~20s):**
> "Last tool. Your stock moved today — how much of that was just *the market*, how
> much was the *sector*, and how much was the *company*? RoboSmart runs a factor
> model to split the move apart. For NVDA today: up point-eight-six total —
> basically all market. The sector actually dragged it down a bit. And this sliver —
> plus point-six-two — is the only part that's really *about the company*."

**On screen / action:** Click **What Happened Today**, select **NVDA**. Show the
decomposition bars: **market +0.86 / sector −0.63 / idiosyncratic +0.62, R² ≈
0.66**. Point the cursor at the idiosyncratic sliver as you name it.

**Narration (the "no clear cause" beat, framed as a feature — ~40s):**
> "And here's the part I'm proudest of. The AI only ever explains *that* sliver —
> the company-specific piece — never the market noise. And when there's no news that
> actually explains it, it says so: 'no clear cause found.' It doesn't invent a
> story. In finance, a tool that admits when it doesn't know is worth more than one
> that always has an answer — because the one that always has an answer is sometimes
> confidently lying to you."

**On screen / action:** Show the explanation panel. If the take lands on a real
explanation, read it; ideally pre-stage the example (see checklist) so it shows the
**"no clear cause found"** message, and rest the cursor on that line as you deliver
the "admits when it doesn't know" line.

### 3:35 – 3:55 — Close (architecture in one breath, then back to honesty)

**Narration:**
> "Under the hood, the math is deterministic and unit-tested — betas, correlations,
> the factor model. The AI only ever reasons *about* those numbers; it never makes
> them up. Numbers you can trust, reasoning that's honest about its limits, and a
> tool that's brave enough to say 'I don't know.'"

**On screen / action:** Quick, calm scroll back to the Judge's three falsifiers
from the Bull vs Bear tab (or a split showing decomposition + falsifiers). End
frame rests on the falsifiers.

### 3:55 – 4:00 — Sign-off

**Narration:**
> "RoboSmart. Numbers with meaning. Meaning with numbers."

**On screen / action:** Hold on the falsifiers / final frame. Fade.

*(Total ≈ 4:00. If running long, trim the Dashboard beat to two numbers and the
factor-model setup by one sentence to stay under the 5:00 cap.)*

---

## 30-second elevator version

**On screen:** Dashboard → one click to the Judge's falsifiers → one click to
"no clear cause found."

> "Your broker gives you numbers with no meaning. An AI chatbot gives you meaning
> with no numbers — and half of it's made up. RoboSmart is the thing in between.
> Upload a portfolio: it flags that you're fifty-six percent in tech, it runs an AI
> Bull-versus-Bear debate where every claim cites a real number and the Judge has to
> give you three things that would change its mind, and it tells you what actually
> moved your stock today — market, sector, or company — and when it can't find a
> cause, it *says* 'no clear cause found' instead of inventing one. Numbers you can
> trust, reasoning that's honest about its limits."

---

## Pre-recording checklist

**Ticker choice — use NVDA, and here's why:** it has a high beta and lives in the
flagged Technology sector, so it drives the Dashboard's concentration story; it
produces a clean, teachable factor decomposition (big market component, sector
pulling the other way, a small but real idiosyncratic sliver); and it's a name the
audience recognizes, so no one gets lost on the ticker instead of the point. Keep a
second recognizable ticker staged as a fallback in case a live take misbehaves.

**Stage the "no clear cause found" beat.** This beat is the honesty payoff — don't
gamble on it appearing live. Pre-select a ticker/day (in mock mode this is
deterministic) where the residual explainer returns "no clear cause found," and
confirm it before you hit record.

**Run in `USE_MOCK` for the recording.** Set `USE_MOCK` so the whole app runs off
the frozen mock dataset — no network, no API latency, fully reproducible takes. The
illustrative numbers (beta ≈ 1.30, R² ≈ 89%, Tech ≈ 56%, effective holdings ≈ 5.6,
NVDA decomposition) are stable in mock mode, so what you rehearse is exactly what
records.

**If an LLM call is slow (only relevant if recording live):** don't wait on-camera.
Either cut to `USE_MOCK` for a guaranteed instant, deterministic take, or pre-warm
the debate and explainer once before recording so responses are cached, then record
the second run. Never leave a spinner on screen — a stalled call reads as a broken
product.

**Warm the cache before the real take.** Do one full dry run through all three tabs
(upload → dashboard → debate → factor model) immediately before recording so
prices, the debate, and the explanation are all cached and everything renders
instantly.

**Screen hygiene:**
- Browser zoom at a level where the value/P&L header, the concentration flag, and a
  full debate turn are readable without squinting (≈ 100–110%; verify on the actual
  recording resolution).
- Hide the bookmarks bar (Ctrl/Cmd+Shift+B).
- Clean desktop — no personal files, no stray icons, notifications silenced (Do Not
  Disturb on).
- Close unrelated tabs; only the RoboSmart app tab open.
- Full-screen or a clean, cropped window so no browser chrome distracts.
- Confirm the dark theme (`theme.py`) is rendering consistently across all three
  tabs before you start.

**Rehearse the pacing.** The Bull vs Bear reveal (1:05–2:35) gets the most time —
practice scrolling so the newest turn stays in frame and you can highlight the cited
number in each turn without fumbling. Time a full run to confirm you land under 5:00
with margin, targeting 4:00.
