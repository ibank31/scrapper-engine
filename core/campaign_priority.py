"""Priority scoring for the campaign radar.

The public campaign payload does not expose real competitor counts.  The
competition value below is therefore deliberately named a *proxy*: it estimates
how attractive a campaign may be to other clippers from payout, remaining
budget, and distribution breadth.  It must never be presented as an observed
competitor count.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any, Mapping


MY_PLATFORMS = {"tiktok", "youtube", "instagram"}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def recency_score(campaign: Mapping[str, Any], now: datetime | None = None) -> float:
    """Return 0..1, preferring campaigns updated/published in the last 30 days."""
    now = now or datetime.now(timezone.utc)
    for key in ("published_at", "created_at", "start_date", "updated_source_at", "updatedAt", "createdAt", "startDate"):
        parsed = _date(campaign.get(key))
        if parsed:
            age_days = max(0.0, (now - parsed).total_seconds() / 86400)
            return round(math.exp(-age_days / 30.0), 3)
    # Missing dates are unknown, not stale. Do not punish the campaign twice.
    return 0.5


def ease_score(campaign: Mapping[str, Any]) -> float:
    """Estimate how easy it is to start from the published rules/materials."""
    text = " ".join(str(campaign.get(k) or "") for k in (
        "description", "rules", "requirements", "resources", "materials", "source_of_truth"
    )).lower()
    score = 0.55
    if re.search(r"provided|official footage|content bank|asset|google drive|youtube|reference", text):
        score += 0.25
    if re.search(r"download|edit from scratch|recreate|original footage", text):
        score -= 0.10
    mandatory = len(re.findall(r"must|required|mandatory|only|don't|do not|禁止", text))
    score -= min(mandatory * 0.025, 0.20)
    if not text.strip():
        score -= 0.10
    return round(max(0.0, min(1.0, score)), 3)


def competition_proxy(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate competition pressure without claiming observed competitor data."""
    rate = max(_number(campaign.get("rate_per_1k")) or 0.0, 0.0)
    budget = max(_number(campaign.get("budget_left")) or 0.0, 0.0)
    platforms = {str(p).lower() for p in (campaign.get("platforms") or [])}
    attractiveness = (
        min(rate, 15.0) / 15.0 * 0.45
        + min(budget, 50000.0) / 50000.0 * 0.35
        + min(len(platforms & MY_PLATFORMS), 3) / 3.0 * 0.20
    )
    pressure = round(max(0.0, min(1.0, attractiveness)), 3)
    # Higher score is better for ranking, so expose both risk and opportunity.
    risk = "high" if pressure >= 0.67 else "medium" if pressure >= 0.34 else "low"
    return {
        "score": round(1.0 - pressure, 3),
        "risk": risk,
        "label": "competition proxy",
        "basis": "payout + remaining budget + platform breadth; not competitor count",
    }


def score_campaign(campaign: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Return component scores and the final priority score (0..100)."""
    ai_fit = _number(campaign.get("ai_fit_score"))
    if ai_fit is None:
        ai_rules = campaign.get("ai_rules")
        if isinstance(ai_rules, Mapping):
            ai_fit = _number((ai_rules.get("campaign_fit") or {}).get("score"))
    relevance = max(0.0, min(1.0, ai_fit if ai_fit is not None else (_number(campaign.get("relevance")) or 0.0)))
    recency = recency_score(campaign, now)
    budget_left = max(_number(campaign.get("budget_left")) or 0.0, 0.0)
    budget = min(budget_left, 50000.0) / 50000.0
    ease = ease_score(campaign)
    competition = competition_proxy(campaign)
    components = {
        "relevance": round(relevance, 3),
        "recency": recency,
        "budget": round(budget, 3),
        "ease": ease,
        "competition": competition["score"],
    }
    score = round(100 * (
        components["relevance"] * 0.20
        + components["recency"] * 0.25
        + components["budget"] * 0.20
        + components["ease"] * 0.20
        + components["competition"] * 0.15
    ), 1)
    return {
        "score": score,
        "priority_components": components,
        "competition_proxy": competition,
    }
