"""profiles.py — sample investor books.

`mock_portfolio.json` was never a realistic person's finances. It is a demo prop
engineered to trip exactly one warning: three tech names to push Technology past
the 40% sector guideline, plus a gold sleeve so the correlation heatmap shows
something other than an all-red block.

That makes for one screenshot and one story. These profiles give the risk engine
four more books to disagree about, which is the actual pedagogy: the same
analysis, four different verdicts.

    aggressive_growth    trips all three concentration guidelines
    conservative_income  trips NOTHING — proof the engine doesn't cry wolf
    diversified_global   genuinely low pairwise correlation
    concentrated_risk    effective holdings far below the position count
    balanced_growth      the original demo book

Each file carries `expect`, a one-line statement of what it should demonstrate.
`tests/test_profiles.py` asserts that claim actually holds, so a profile whose
composition drifts away from its own description fails the build rather than
quietly becoming a lie in the UI.

Returns Contract A (`portfolio.py`), unchanged: {positions, cash, currency}.
"""

from __future__ import annotations

import copy
import json
import os

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")

# Display order, worked through deliberately: start dull, end alarming.
ORDER = ["balanced_growth", "conservative_income", "diversified_global",
         "aggressive_growth", "concentrated_risk"]


class ProfileNotFound(Exception):
    """Requested profile id has no file."""


def _read(profile_id: str) -> dict:
    path = os.path.join(PROFILE_DIR, f"{profile_id}.json")
    if not os.path.exists(path):
        raise ProfileNotFound(
            f"No profile {profile_id!r}. Available: {', '.join(available_ids())}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def available_ids() -> list:
    """Profile ids present on disk, in ORDER, with any extras appended."""
    on_disk = {f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")}
    ordered = [p for p in ORDER if p in on_disk]
    return ordered + sorted(on_disk - set(ordered))


def list_profiles() -> list:
    """[{id, name, emoji, tagline, expect}] — metadata only, no positions."""
    out = []
    for pid in available_ids():
        doc = _read(pid)
        out.append({k: doc.get(k, "") for k in ("id", "name", "emoji", "tagline", "expect")})
    return out


def load_portfolio(profile_id: str) -> dict:
    """Contract A for one profile — a DEEP COPY, never the parsed document.

    This used to hand back a live reference into the freshly-parsed file. That
    was survivable while a loaded portfolio was read-only, but cash is now
    editable from the sidebar and the builder can start from a sample book, so
    a caller writing to `st.session_state.portfolio` would be writing into the
    profile itself and every later read in that run would see the mutation.
    `market_data.fixture.get_context` copies for exactly this reason.
    """
    doc = _read(profile_id)
    portfolio = doc.get("portfolio")
    if not isinstance(portfolio, dict) or not portfolio.get("positions"):
        raise ProfileNotFound(f"Profile {profile_id!r} has no positions")
    return copy.deepcopy(portfolio)


def label(profile: dict) -> str:
    """'🚀 Aggressive growth' — for a selectbox."""
    emoji = profile.get("emoji", "")
    return f"{emoji} {profile.get('name', profile.get('id'))}".strip()


def all_tickers() -> list:
    """Every symbol across every profile — what the offline fixture must cover.

    `market_data.refresh` reads this, so adding a holding to a profile can never
    leave the offline build silently missing it.
    """
    seen = []
    for pid in available_ids():
        for pos in load_portfolio(pid).get("positions", []):
            t = str(pos.get("ticker", "")).upper().strip()
            if t and t not in seen:
                seen.append(t)
    return seen


if __name__ == "__main__":
    for p in list_profiles():
        print(f"{label(p):32s} {p['tagline']}")
    print(f"\n{len(all_tickers())} unique tickers: {', '.join(all_tickers())}")
