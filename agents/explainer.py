"""
agents/explainer.py — Person 4's idiosyncratic-move explainer.
==============================================================
The factor model (factor_model.decompose_move) does the MATH: it splits today's
move into market, sector, and company-specific (idiosyncratic) pieces. This agent
does the NARROW language job on top of that: it looks ONLY at the idiosyncratic
residual and tries to explain it from recent news headlines.

Hard design rules (so the tab stays honest):
- The decomposition is given to the model as ESTABLISHED FACT. It must NOT
  re-litigate or recompute the math.
- Each candidate explanation must cite a SPECIFIC headline. No headline, no claim.
- If no headline plausibly explains a residual of this size, the RIGHT answer is
  "no clear cause found" — never a fabricated reason.
- A residual under ~0.3% is daily noise and needs no explanation at all.

Mock-first: when llm.use_mock() is True we return a DETERMINISTIC result derived
from the decomposition + news, with NO API call and NO network — so the whole app
demos end-to-end with no key.

Public API (fixed signature):
    def explain_idiosyncratic(context: dict, decomposition: dict) -> dict
"""

from __future__ import annotations

import os
import re

from agents import llm

# Residual smaller than this (in percentage points, absolute) is daily noise.
NOISE_THRESHOLD = 0.3
# Residual at/above this is treated as a large, "significant" company-specific move.
SIGNIFICANT_THRESHOLD = 2.0

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), os.pardir,
                            "prompts", "explainer.txt")


def _load_prompt() -> str:
    """Load the prompt template from prompts/explainer.txt."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _residual(decomposition: dict) -> float:
    """Absolute idiosyncratic residual in percentage points (0.0 if missing)."""
    return abs(decomposition.get("idiosyncratic_pct") or 0.0)


def _news_block(news: list) -> str:
    """Render the headlines as a compact, numbered evidence list for the prompt."""
    if not news:
        return "(no recent headlines available)"
    lines = []
    for i, item in enumerate(news, 1):
        # str() before strip(): `published` arrives as a Unix epoch int from one
        # of yfinance's two news schemas. The data layer now normalises it, but
        # this block also runs on contexts built elsewhere (tests, fixtures
        # recorded by older code), and a crash here takes out the whole tab.
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        publisher = str(item.get("publisher") or "").strip()
        published = str(item.get("published") or "").strip()
        link = str(item.get("link") or "").strip()
        meta = " · ".join(p for p in (publisher, published) if p)
        head = f"{i}. \"{title}\""
        if meta:
            head += f" ({meta})"
        if link:
            head += f"\n   link: {link}"
        lines.append(head)
    return "\n".join(lines) if lines else "(no recent headlines available)"


def _assessment(resid: float) -> str:
    """Bucket the residual magnitude into noise / notable / significant."""
    if resid < NOISE_THRESHOLD:
        return "noise"
    if resid < SIGNIFICANT_THRESHOLD:
        return "notable"
    return "significant"


_CORP_STOPWORDS = {
    "corporation", "corp", "inc", "incorporated", "ltd", "limited", "co", "company",
    "plc", "group", "holdings", "holding", "shares", "trust", "the", "and", "class",
}


def _mentions_company(headline: str, context: dict) -> bool:
    """True when the headline actually names this company or its ticker.

    `data_layer` already filters the news feed, but it deliberately falls back to the
    unfiltered pool rather than starving the tab — so the mock re-checks here. Without
    this guard it attributed NVDA's move to a headline about Teva purely because Teva's
    story was the most recent one Yahoo happened to attach to NVDA.
    """
    text = (headline or "").lower()
    if not text:
        return False
    tokens = {str(context.get("ticker") or "").lower()}
    for tok in re.split(r"[^a-z0-9]+", str(context.get("company_name") or "").lower()):
        if len(tok) >= 3 and tok not in _CORP_STOPWORDS:
            tokens.add(tok)
    return any(t and t in text for t in tokens)


def _mock(context: dict, decomposition: dict) -> dict:
    """Deterministic, API-free result derived from the decomposition + news.

    Mirrors the real agent's contract so the tab renders identically in demo mode.
    """
    resid = _residual(decomposition)

    if resid < NOISE_THRESHOLD:
        return {
            "explanations": [],
            "no_cause_found": True,
            "residual_assessment": "noise",
            "caveat": "Residual is within daily noise; no explanation needed.",
        }

    # Only headlines that name the company are candidates. Attributing a move to a
    # story about someone else is worse than admitting we don't know.
    news = [n for n in (context.get("news") or [])
            if _mentions_company((n or {}).get("title", ""), context)]
    if news:
        top = news[0] or {}
        headline = (top.get("title") or "").strip()
        link = top.get("link", "") or ""
        idio = decomposition.get("idiosyncratic_pct")
        direction = "gain" if (idio or 0.0) >= 0 else "decline"
        assessment = "notable" if resid < SIGNIFICANT_THRESHOLD else "significant"
        return {
            "explanations": [
                {
                    "cause": headline or "Company-specific news",
                    "likelihood": "medium",
                    "evidence_headline": headline,
                    "source_link": link,
                    "reasoning": (
                        f"After stripping out the market and sector, about "
                        f"{resid:.2f}% of today's {direction} is company-specific. "
                        f"This headline is the most likely driver of that residual, "
                        f"though the link is a heuristic association, not confirmed "
                        f"causation."
                    ),
                }
            ],
            "no_cause_found": False,
            "residual_assessment": assessment,
            "caveat": (
                "Demo attribution: the headline is matched to the residual by "
                "recency, not by verified causation."
            ),
        }

    # No headline names the company. Say so — "no clear cause found" is a designed,
    # legitimate outcome that the tab already renders as an answer rather than an error.
    return {
        "explanations": [],
        "no_cause_found": True,
        "residual_assessment": _assessment(resid),
        "caveat": (
            "No recent headline mentions this company, so the company-specific move "
            "has no news explanation in the available data."
        ),
    }


def _coerce(result: dict, context: dict, decomposition: dict) -> dict:
    """Defensively normalize the model's JSON to the fixed output contract."""
    resid = _residual(decomposition)
    out: dict = {}

    explanations = result.get("explanations")
    clean: list = []
    if isinstance(explanations, list):
        for e in explanations[:3]:
            if not isinstance(e, dict):
                continue
            like = str(e.get("likelihood", "medium")).lower()
            if like not in ("high", "medium", "low"):
                like = "medium"
            clean.append({
                "cause": str(e.get("cause", "")).strip(),
                "likelihood": like,
                "evidence_headline": str(e.get("evidence_headline", "")).strip(),
                "source_link": str(e.get("source_link", "")).strip(),
                "reasoning": str(e.get("reasoning", "")).strip(),
            })
    out["explanations"] = clean

    no_cause = result.get("no_cause_found")
    if not isinstance(no_cause, bool):
        no_cause = len(clean) == 0
    # Consistency guard: empty list must mean no cause found, and vice-versa.
    if not clean:
        no_cause = True
    out["no_cause_found"] = no_cause

    assessment = str(result.get("residual_assessment", "")).lower()
    if assessment not in ("noise", "notable", "significant"):
        assessment = _assessment(resid)
    out["residual_assessment"] = assessment

    out["caveat"] = str(result.get("caveat", "")).strip() or (
        "This attribution links news to a statistical residual and may be incomplete."
    )
    return out


def explain_idiosyncratic(context: dict, decomposition: dict) -> dict:
    """Explain ONLY the idiosyncratic residual from decompose_move using news.

    Returns JSON with keys: explanations[], no_cause_found, residual_assessment,
    caveat. Never raises for the "no cause" case — that is a valid, expected answer.
    """
    resid = _residual(decomposition)

    # Sub-noise residual: no LLM needed at all, regardless of mode.
    if resid < NOISE_THRESHOLD:
        return {
            "explanations": [],
            "no_cause_found": True,
            "residual_assessment": "noise",
            "caveat": "Residual is within daily noise; no explanation needed.",
        }

    # Demo / no-key path: deterministic, no API, no network.
    if llm.use_mock():
        return _mock(context, decomposition)

    news = context.get("news") or []
    prompt = _load_prompt().format(
        ticker=context.get("ticker", "") or "",
        company_name=context.get("company_name", "") or context.get("ticker", "") or "the company",
        sector=context.get("sector", "") or "Unknown",
        sector_etf=context.get("sector_etf", "") or "SPY",
        total_move_pct=decomposition.get("total_move_pct"),
        market_component_pct=decomposition.get("market_component_pct"),
        sector_component_pct=decomposition.get("sector_component_pct"),
        idiosyncratic_pct=decomposition.get("idiosyncratic_pct"),
        news_block=_news_block(news),
    )

    system = (
        "You attribute a stock's company-specific daily move to specific news "
        "headlines. The market/sector/idiosyncratic split is already computed and is "
        "FACT — never recompute it. Cite only headlines you are given. If nothing "
        "fits, answer 'no clear cause found' rather than inventing a reason. "
        "Respond with JSON only."
    )

    result = llm.call_json(system, prompt, max_tokens=1500)
    return _coerce(result, context, decomposition)
