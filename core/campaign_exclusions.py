#!/usr/bin/env python3
"""Deterministic campaign exclusions applied before daily hydration and AI analysis."""
from __future__ import annotations

import json
import re
from typing import Any

# Keep this list explicit and conservative. Generic words such as "money" or
# "game" are intentionally absent to avoid excluding legitimate business or
# video-game campaigns. Add a term only when it identifies regulated gambling,
# real-money gaming, or a known gambling operator.
EXCLUDED_CAMPAIGN_TERMS: tuple[str, ...] = (
    "gambling",
    "casino",
    "poker",
    "sportsbook",
    "sports betting",
    "betting",
    "wager",
    "roulette",
    "blackjack",
    "slot machine",
    "slots",
    "real money",
    "real-money",
    "money game",
    "moneygame",
    "deposit match",
    "boosted rtp",
    "1win",
    "coinpoker",
    "shuffle streamers",
    "shuffle clipping",
)

_COMPILED_TERMS = tuple(
    (term, re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.IGNORECASE))
    for term in EXCLUDED_CAMPAIGN_TERMS
)


def _campaign_text(campaign: dict[str, Any]) -> str:
    """Build a searchable text view without relying on a single field."""
    fields = (
        campaign.get("title"),
        campaign.get("brand"),
        campaign.get("category"),
        campaign.get("description"),
        campaign.get("docs_text"),
        campaign.get("requirements"),
        campaign.get("resources"),
        campaign.get("payouts"),
        campaign.get("ai_rules"),
        campaign.get("plan_json"),
    )
    return " ".join(
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for value in fields
        if value not in (None, "", [], {})
    ).lower()


def excluded_campaign_terms(campaign: dict[str, Any]) -> list[str]:
    """Return matched exclusion terms in stable order."""
    text = _campaign_text(campaign)
    return [term for term, pattern in _COMPILED_TERMS if pattern.search(text)]


def is_excluded_campaign(campaign: dict[str, Any]) -> bool:
    return bool(excluded_campaign_terms(campaign))


__all__ = ["EXCLUDED_CAMPAIGN_TERMS", "excluded_campaign_terms", "is_excluded_campaign"]


if __name__ == "__main__":
    import sys

    sample = json.loads(sys.stdin.read())
    print(json.dumps({"excluded": is_excluded_campaign(sample), "terms": excluded_campaign_terms(sample)}))
