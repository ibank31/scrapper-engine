#!/usr/bin/env python3
"""Extract production constraints and asset links from a campaign detail.

The campaign text is the source of truth. This module deliberately produces
recommendations and gates; it never assumes that a clip is safe to publish.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.I)


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:!?)]}")


def _text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(x) for x in value if x is not None)
    return "\n".join(parts)


def _find_urls(text: str) -> list[str]:
    out: list[str] = []
    for match in URL_RE.findall(text):
        url = _clean_url(match)
        if url not in out:
            out.append(url)
    return out


def _contains(text: str, *terms: str) -> bool:
    t = text.lower()
    return any(term.lower() in t for term in terms)


def _first_number(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def compile_plan(detail: dict[str, Any]) -> dict[str, Any]:
    campaign = detail.get("campaign") or detail
    static = detail.get("staticDetails") or {}
    requirements = static.get("requirements") or []
    resources = static.get("resources") or []
    req_texts = [str(r.get("text") or "").strip() if isinstance(r, dict) else str(r).strip() for r in requirements if r]
    description = str(campaign.get("description") or "")
    full_text = _text(description, req_texts)
    urls = _find_urls(full_text)

    asset_urls: list[str] = []
    for resource in resources:
        if isinstance(resource, dict) and resource.get("url"):
            asset_urls.append(str(resource["url"]))
    for url in urls:
        host = urlparse(url).netloc.lower()
        if any(x in host for x in ("drive.google", "dropbox", "frame.io", "youtube", "youtu.be", "vimeo")):
            if url not in asset_urls:
                asset_urls.append(url)

    watermark_required = _contains(
        full_text,
        "mandatory watermark",
        "watermark required",
        "watermark wajib",
        "official watermark",
        "watermark asset",
        "watermark",
    ) and not _contains(full_text, "no watermark", "without watermark")
    no_third_party_watermark = _contains(full_text, "no third-party watermark", "no third party watermark", "tanpa watermark")
    official_audio_required = _contains(full_text, "official audio", "official sound", "attach the official sound", "audio resmi")
    supplied_material_required = _contains(
        full_text,
        "provided video clips",
        "provided clips",
        "raw assets",
        "raw footage",
        "content bank",
        "campaign folders",
        "content tab",
        "pull our raw assets",
    )
    vertical_required = _contains(full_text, "9:16", "vertical")
    no_bots = _contains(full_text, "no view-manipulation", "no bot", "view bots", "engagement rings", "botting")

    prohibited: list[str] = []
    for label, terms in {
        "third_party_watermark": ("no third-party watermark", "no third party watermark"),
        "view_manipulation": ("no view-manipulation", "no view manipulation", "view bots", "botting"),
        "generic_or_unrelated_content": ("generic motivational", "unrelated content", "random stock footage", "ai spam"),
        "reupload_only": ("no re-uploads", "raw, unedited video dumps"),
    }.items():
        if _contains(full_text, *terms):
            prohibited.append(label)

    tags = sorted(set(re.findall(r"@[A-Za-z0-9_.-]+", full_text)))
    cta_urls = [u for u in urls if any(x in u.lower() for x in ("http://", "https://")) and not any(
        host in urlparse(u).netloc.lower() for host in ("dropbox.com", "drive.google.com", "youtube.com", "youtu.be", "tiktok.com")
    )]
    min_views = _first_number(full_text, [r"minimum floor\s*:?\s*([\d,]+)\s*views", r"minimum\s+([\d,]+)\s*views", r"min(?:imum)?\s+views?\s*:?\s*([\d,]+)"])
    max_payout = _first_number(full_text, [r"maximum cap\s*:?\s*\$?([\d,.]+)", r"max(?:imum)?\s+payout\s*:?\s*\$?([\d,.]+)"])

    normalized_requirements = []
    for item, text in zip(requirements, req_texts):
        lower = text.lower()
        normalized_requirements.append({
            "id": "demographic_information" if _contains(lower, "demographic", "demografi") else
                  "caption_hashtag" if _contains(lower, "hashtag", "caption", "tag") else
                  "source_asset" if _contains(lower, "provided", "supplied", "raw asset", "content bank") else
                  "watermark" if _contains(lower, "watermark") else
                  "official_audio" if _contains(lower, "official audio", "official sound") else
                  "cta" if _contains(lower, "call to action", "cta", "link in bio") else "custom",
            "text": text,
            "mandatory": bool(item.get("isMandatory", True)) if isinstance(item, dict) else True,
            "platform": item.get("platform", "all") if isinstance(item, dict) else "all",
        })

    gates = [
        {"id": "campaign_active", "required": True, "check": "campaign status is active"},
        {"id": "assets_available", "required": supplied_material_required, "check": "required campaign assets are downloaded or supplied"},
        {"id": "vertical_916", "required": vertical_required, "check": "output aspect ratio is 9:16"},
        {"id": "watermark", "required": watermark_required, "check": "required official watermark is present for the full clip"},
        {"id": "no_third_party_watermark", "required": no_third_party_watermark, "check": "no third-party watermark is visible"},
        {"id": "official_audio", "required": official_audio_required, "check": "official audio/sound is attached or used as required"},
        {"id": "human_review", "required": True, "check": "human review completed before submission"},
    ]

    return {
        "schema_version": 1,
        "campaign": {
            "id": campaign.get("id"),
            "title": campaign.get("title"),
            "brand": campaign.get("brand"),
            "status": campaign.get("status"),
            "platforms": campaign.get("socialPlatforms") or campaign.get("platforms") or [],
            "campaign_type": campaign.get("campaignType") or campaign.get("type"),
        },
        "source_of_truth": {"description": description, "requirements": requirements, "normalized_requirements": normalized_requirements},
        "production": {
            "provided_material_required": supplied_material_required,
            "asset_urls": asset_urls,
            "aspect_ratio": "9:16" if vertical_required else None,
            "official_audio_required": official_audio_required,
            "watermark_required": watermark_required,
            "no_third_party_watermark": no_third_party_watermark,
            "required_handles": tags,
            "cta_urls": cta_urls,
            "minimum_views": int(min_views) if min_views is not None else None,
            "maximum_payout": max_payout,
            "prohibited": prohibited,
        },
        "gates": gates,
        "automation_policy": {
            "render_allowed": True,
            "publish_allowed": False,
            "reason": "Campaign rules must be validated and a human must approve before publishing.",
            "no_view_manipulation": no_bots,
        },
    }


def plan_markdown(plan: dict[str, Any]) -> str:
    c = plan["campaign"]
    p = plan["production"]
    lines = [f"# Production Plan — {c.get('title') or 'Campaign'}", "", f"- Campaign ID: `{c.get('id')}`", f"- Status: `{c.get('status')}`", f"- Platforms: {', '.join(c.get('platforms') or []) or '-'}", "", "## Production constraints", ""]
    rows = [
        ("Provided material required", p["provided_material_required"]),
        ("Aspect ratio", p["aspect_ratio"] or "not specified"),
        ("Official audio required", p["official_audio_required"]),
        ("Watermark required", p["watermark_required"]),
        ("No third-party watermark", p["no_third_party_watermark"]),
        ("Required handles", ", ".join(p["required_handles"]) or "-"),
        ("CTA URLs", ", ".join(p["cta_urls"]) or "-"),
        ("Minimum views", p["minimum_views"] or "-"),
        ("Maximum payout", p["maximum_payout"] or "-"),
    ]
    lines += ["| Rule | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    lines += ["", "## Asset URLs", ""] + [f"- {u}" for u in p["asset_urls"]] if p["asset_urls"] else lines + ["- No asset URL detected"]
    lines += ["", "## Prohibited", ""] + [f"- `{x}`" for x in p["prohibited"]] if p["prohibited"] else lines + ["- None detected"]
    lines += ["", "## Mandatory gates", "", "| Gate | Required | Check |", "|---|---:|---|"]
    lines += [f"| {g['id']} | {'yes' if g['required'] else 'no'} | {g['check']} |" for g in plan["gates"]]
    lines += ["", "> Publishing is disabled by default. A clip must pass every required gate and human review.", ""]
    return "\n".join(lines)


__all__ = ["compile_plan", "plan_markdown"]
