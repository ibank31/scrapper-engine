#!/usr/bin/env python3
"""Campaign-aware transcript relevance checks before human review."""
from __future__ import annotations

import re

STOP = {"the", "and", "for", "with", "from", "your", "this", "that", "campaign", "content", "clipping", "video", "official", "brand", "views", "short", "form", "post", "posts", "social", "allowed"}
KNOWN = {
    "boxabl": ("boxabl", "casita", "foldable home", "foldable homes", "modular home", "prefabricated home", "factory tour"),
    "forgegui": ("forgegui", "forge g-u-i", "roblox", "roblox dev", "gui", "3d models", "ai tool"),
    "fundingpips": ("fundingpips", "forex", "trading", "trader"),
}
COMPETING_TERMS = tuple(sorted({"starship", "starbase", "boxabl", "casita", "roblox", "forgegui", "fundingpips", "forex", "trading"}))


def _text(plan: dict) -> str:
    source = plan.get("source_of_truth") or {}
    campaign = plan.get("campaign") or {}
    return " ".join(str(x) for x in (campaign.get("title"), campaign.get("brand"), source.get("description")) if x)


def terms_for_plan(plan: dict) -> list[str]:
    ai = plan.get("ai_rules") if isinstance(plan.get("ai_rules"), dict) else {}
    ai_rule_set = ai.get("rules") if isinstance(ai.get("rules"), dict) else {}
    ai_terms = [str(x).strip().lower() for x in (ai_rule_set.get("topic_terms") or []) if str(x).strip()]
    if ai_terms:
        campaign = plan.get("campaign") or {}
        seed = [str(campaign.get("title") or "").lower(), str(campaign.get("brand") or "").lower()]
        return list(dict.fromkeys(ai_terms + [x for x in seed if len(x) >= 3]))
    text = _text(plan)
    lower = text.lower()
    terms: list[str] = []
    for key, values in KNOWN.items():
        if key in lower:
            terms.extend(values)
    if terms:
        return list(dict.fromkeys(terms))
    for phrase in re.findall(r"\b[a-z][a-z-]{4,}(?:\s+[a-z][a-z-]{4,})?\b", lower):
        if phrase not in STOP and phrase not in terms and phrase not in {"description", "provided", "required"}:
            terms.append(phrase)
    return list(dict.fromkeys(terms))


def check_candidate(plan: dict, candidate: dict) -> dict:
    text = str(candidate.get("text") or "").lower()
    terms = terms_for_plan(plan)
    matches = [term for term in terms if term in text]
    # A plan with no extractable topical terms is not auto-rejected; require human review.
    if not terms:
        return {"status": "uncertain", "matches": [], "terms": [], "reason": "no reliable topical terms extracted; human review required"}
    if matches:
        return {"status": "pass", "matches": matches[:8], "terms": terms[:30], "reason": "candidate transcript matches campaign topic signals"}
    competing = [term for term in COMPETING_TERMS if term in text and term not in terms]
    if competing:
        return {"status": "blocked", "matches": competing[:8], "terms": terms[:30], "reason": "candidate contains a clearly competing campaign topic"}
    return {"status": "uncertain", "matches": [], "terms": terms[:30], "reason": "no literal topic match; render for human relevance review"}
