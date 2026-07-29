# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: a beginner retail investor.** Owns a handful of stocks, does not know what
beta means, and arrives with one question — *"my stock moved, why?"* Needs jargon
explained where it appears, not in a glossary.

**Secondary: a technical evaluator.** Reviews the system in roughly ten minutes and
judges architecture and AI sophistication. Must be able to reach the rigour underneath
the plain-language surface without reading the source.

Confirmed by the user: the design must serve the beginner first while remaining legible
to the evaluator. That implies progressive disclosure — the plain answer on the surface,
the method one layer down, never hidden but never in the way.

## Product Purpose

Upload a stock portfolio and understand three things: what you own and how concentrated
it really is, what actually moved a holding today, and what the strongest arguments for
and against it are. Educational; it never recommends buying or selling.

Success is a user who understands *why* a number is what it is — not one who was told
what to do.

## Positioning

**Execution-led, and stated as such by the user:** *"Nothing is something that another
company cannot do by themselves. The goal is that the design, the different features, the
animations and motions, and the UX and frontend implementations will be the things that
differentiate us."*

Recorded verbatim because it sets the bar for all future work: this product does not
claim a defensible mechanism. It claims craft. That is a legitimate position, and a
demanding one — it means quality of execution is the product, not a coat of paint on it.

Underneath, the substance the execution must not undermine: the statistical
decomposition runs *before* any model speaks, the model may only interpret the residual
it could not explain, and "no clear cause found" is a designed, legitimate answer.
Sixteen tests enforce that citations are real. The craft has to make that rigour felt,
not hide it.

## Operating Context

- Opened in a desktop browser. Graders and demo viewers are on laptops.
- Deployed on Streamlit Community Cloud; the app sleeps after ~12 h idle and cold-starts
  on the next visit.
- Runs on live market data by default, with a recorded snapshot available; a viewer must
  never mistake recorded data for live.
- Short sessions: open, look, ask one question, leave.
- Also consumed as a 3–5 minute recorded demo and defended live in a short presentation.

## Capabilities and Constraints

**Stack (existing):** Python + Streamlit. This is a hard design constraint. Streamlit
custom components render inside isolated iframes and cannot call one another, so
orchestrated cross-component motion, shared animation timelines, and page-load
choreography are **not achievable in the current stack**. This directly limits the
differentiator stated under Positioning.

- Five sample investor books, each with a claim about what it demonstrates that is
  enforced against the computed numbers by tests.
- Analytics layer (portfolio metrics, OLS factor model) imports no Streamlit and is
  portable to any frontend.
- AI today is a prompt chain, not an agent: five sequential calls for the debate, one for
  the residual explainer. No tools, no loops, no autonomous investigation.
- Offline fixture mode reproduces the whole app with no network and no API key.
- Free hosting tier: ~1 GB RAM.

**Explicitly undecided:**
- Whether to migrate the frontend to React + FastAPI. The analytics layer would carry
  over untouched; the ~1,220 lines of Streamlit UI would be replaced.
- Whether to add a tool-using chat agent alongside the existing fixed-choreography chain.

**Scope of change, per the user:** nothing is a hard must-keep, but the existing features
and content are settled decisions worth preserving *in substance*. Structure, layout and
presentation may change; the Bull vs Bear concept stays; new tables and views may be
added. Existing AI features are not to be discarded and rebuilt from scratch. This is a
redesign of the surface, not a reinvention of the product.

## Brand Commitments

- Name: **RoboSmart Investment**. Not declared immutable, but it is embedded in the
  repository, the deployed URL and the submitted summary document, so changing it carries
  real cost.
- **"Not investment advice"** must stay visible, not buried. It is both an ethical
  commitment and a course requirement.
- Voice today: plain-spoken and explanatory. Explains a term at the point it is used
  ("40% less than the market" beside "β 0.60") rather than assuming knowledge.

## Evidence on Hand

Real, and usable in the interface:

- Recorded market snapshot: 18 tickers, 27 price histories, carrying its own timestamp
  (`market_data/fixtures/market_data.json`).
- Real news headlines with working publisher links, filtered to those that actually name
  the company.
- 159 passing tests, including 16 that verify the model only cites evidence it was given.
- Five investor profiles whose stated claims are test-enforced (`profiles/`).
- Screenshots of the current interface (`docs/`).

**Absent — must not be fabricated:** no users, no testimonials, no customers, no
performance track record, no benchmarks against other products. The performance chart is
an explicitly hypothetical constant-weight backtest and must always be labelled as one.

## Product Principles

1. **Numbers before narrative.** The math runs first and independently; language only
   interprets what the math left over.
2. **Say "I don't know" out loud.** A confident "no clear cause found" is a better answer
   than a fabricated one, and the interface must present it as an answer, not an error.
3. **The same engine must reach different verdicts.** If every portfolio produced the
   same warnings, the analysis would be decoration.
4. **Recorded data must never look live.** Any non-live state names its snapshot date in
   the interface.
5. **Explain to the beginner; let the evaluator drill down.** One surface, two depths.

## Accessibility & Inclusion

No formal standard was set by the user. Two known, concrete gaps recorded so future work
does not have to rediscover them:

- The holdings table exposes raw floats to assistive technology
  (`5.5705166001451385`) where the screen shows `5.6%` — formatting is visual only.
- Gain and loss are currently carried by **colour alone** (green/red), which fails for
  red-green colour blindness. A second, non-colour cue is needed.

Baseline to hold: keyboard navigable, visible focus, and reduced-motion honoured — the
last matters more once motion becomes a stated differentiator.
