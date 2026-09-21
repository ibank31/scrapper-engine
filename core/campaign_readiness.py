"""Assess whether a Content Rewards campaign is easy and safe to clip.

Phase 1 goal: the machine ranks campaigns so a non-expert user only sees
clear Indonesian status labels. Output captions/subtitles stay English later;
this module is decision support only.

Content type on Content Rewards is often NOT in `type` (that field is usually
the payout model: cpm). We infer clipping vs UGC vs slideshow from title,
description, category, and materials text.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

STATUS_SIAP = "siap"
STATUS_KETAT = "ketat"
STATUS_BELUM = "belum_siap"
STATUS_LEWATI = "lewati"

LABELS = {
    STATUS_SIAP: "Siap dikerjakan",
    STATUS_KETAT: "Bisa, tapi ketat",
    STATUS_BELUM: "Belum siap",
    STATUS_LEWATI: "Lewati dulu",
}

CLIPPING_TITLE = re.compile(
    r"\bclip(?:ping|s)?\b|clipper|repurpos|short[- ]form from|cut (?:from|the)",
    re.I,
)
UGC_HINT = re.compile(
    r"\bugc\b|user[- ]generated|on[- ]camera|with face|faceless creator|"
    r"create (?:authentic|original) content|talking about (?:your|the) product",
    re.I,
)
SLIDESHOW_HINT = re.compile(r"\bslideshow\b|carousel posts?|slide deck", re.I)

PUBLIC_HOST_HINTS = (
    "youtube.com",
    "youtu.be",
    "drive.google.com",
    "docs.google.com",
    "dropbox.com",
    "vimeo.com",
)
LOGIN_PORTAL_HINTS = (
    "mediasilo.com",
    "frame.io",
    "wipster",
    "iconik.cloud",
    "box.com",
)

ACCOUNT_HEAVY = re.compile(
    r"warmup|warm[- ]up|day 1\b|day 2\b|day 3\b|required (?:account )?bio|"
    r"must use a (?:fully )?\w+ based[- ]account|tier[- ]?1 audience|"
    r"dedicated page|new channel",
    re.I,
)
CAPTION_STRICT = re.compile(
    r"exact (?:phrase|wording|caption)|must include the exact|no substitutions|"
    r"caption must|required caption|ftc disclosure|this exact wording",
    re.I,
)
WATERMARK_STRICT = re.compile(
    r"logo watermark|watermark required|mandatory watermark|official watermark",
    re.I,
)
FIXED_TAG = re.compile(r"tag @\w+|must tag|tagging requirement", re.I)
DISCORD_ONLY = re.compile(r"join discord|discord\.gg|see discord|rules in discord", re.I)
RAW_OK = re.compile(
    r"provided (?:footage|clips|assets|video)|official footage|content (?:bank|folder)|"
    r"source footage|repurpose|do not (?:create|make) (?:full )?videos? from scratch",
    re.I,
)
BUDGET_GONE = 50.0  # USD left considered effectively empty for ranking


def _blob(campaign: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "title",
        "brand",
        "description",
        "category",
        "type",
        "content_kind",
    ):
        parts.append(str(campaign.get(key) or ""))
    for key in ("requirements", "resources", "payouts", "creatorRequirements", "contentRequirements"):
        val = campaign.get(key)
        if val is None and isinstance(campaign.get("detail"), dict):
            val = campaign["detail"].get(key)
        if isinstance(val, (list, dict)):
            parts.append(json.dumps(val, ensure_ascii=False))
        elif val:
            parts.append(str(val))
    # Plan / docs text attached during sync
    for key in ("rules_text", "docs_text", "materials_text"):
        if campaign.get(key):
            parts.append(str(campaign.get(key)))
    plan = campaign.get("plan_json") or campaign.get("plan") or {}
    if isinstance(plan, dict):
        prod = plan.get("production") or {}
        parts.append(json.dumps(prod, ensure_ascii=False))
        sot = plan.get("source_of_truth") or {}
        parts.append(str(sot.get("description") or ""))
    return "\n".join(parts)


def _urls_from(campaign: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    text = _blob(campaign)
    for m in re.finditer(r"https?://[^\s<>\]\"')]+", text, re.I):
        u = m.group(0).rstrip(".,;:)]}\"'")
        if u not in found:
            found.append(u)
    plan = campaign.get("plan_json") or campaign.get("plan") or {}
    if isinstance(plan, dict):
        for u in (plan.get("production") or {}).get("asset_urls") or []:
            if u and str(u) not in found:
                found.append(str(u))
    for resource in campaign.get("resources") or []:
        if isinstance(resource, dict) and resource.get("url"):
            u = str(resource["url"])
            if u not in found:
                found.append(u)
    return found


def classify_content_kind(campaign: Mapping[str, Any]) -> str:
    """Return clipping | ugc | slideshow | other."""
    title = str(campaign.get("title") or "")
    desc = str(campaign.get("description") or "")
    cat = str(campaign.get("category") or "").lower()
    explicit = str(
        campaign.get("content_type")
        or campaign.get("campaign_content_type")
        or campaign.get("contentType")
        or ""
    ).lower()
    if "clip" in explicit:
        return "clipping"
    if "ugc" in explicit:
        return "ugc"
    if "slideshow" in explicit or "slide" in explicit:
        return "slideshow"
    if SLIDESHOW_HINT.search(title) or "slideshow" in cat:
        return "slideshow"
    if UGC_HINT.search(title) or UGC_HINT.search(desc):
        # Title wins if it also says Clipping
        if CLIPPING_TITLE.search(title):
            return "clipping"
        return "ugc"
    if CLIPPING_TITLE.search(title) or CLIPPING_TITLE.search(desc):
        return "clipping"
    # Many CR cards are clipping but only say CPM in type field.
    # Prefer clipping when materials language is repurpose/provided footage.
    blob = _blob(campaign)
    if RAW_OK.search(blob) and not UGC_HINT.search(blob):
        return "clipping"
    if "clip" in title.lower():
        return "clipping"
    return "other"


def _material_signals(campaign: Mapping[str, Any]) -> dict[str, Any]:
    urls = _urls_from(campaign)
    hosts = [urlparse(u).netloc.lower() for u in urls]
    has_youtube = any("youtube.com" in h or "youtu.be" in h for h in hosts)
    has_drive = any("drive.google.com" in h for h in hosts)
    has_docs = any("docs.google.com" in h for h in hosts)
    has_direct = any(re.search(r"\.(mp4|mov|m4v|webm)(\?|$)", u, re.I) for u in urls)
    has_login_portal = any(any(p in (h + u) for p in LOGIN_PORTAL_HINTS) for h, u in zip(hosts, urls))
    has_public_hint = has_youtube or has_drive or has_docs or has_direct
    docs_text = str(campaign.get("docs_text") or campaign.get("rules_text") or "")
    docs_fetched = bool(docs_text.strip()) and not docs_text.startswith("FAIL")
    return {
        "urls": urls[:12],
        "has_youtube": has_youtube,
        "has_drive": has_drive,
        "has_docs": has_docs,
        "has_direct_media": has_direct,
        "has_login_portal": has_login_portal,
        "has_public_hint": has_public_hint,
        "docs_fetched": docs_fetched,
        "url_count": len(urls),
    }


def _count_strict_rules(text: str) -> dict[str, bool]:
    return {
        "account_heavy": bool(ACCOUNT_HEAVY.search(text)),
        "caption_strict": bool(CAPTION_STRICT.search(text)),
        "watermark_strict": bool(WATERMARK_STRICT.search(text)),
        "fixed_tag": bool(FIXED_TAG.search(text)),
        "discord_centric": bool(DISCORD_ONLY.search(text)) and not RAW_OK.search(text),
        "provided_footage": bool(RAW_OK.search(text)),
    }


def assess_readiness(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Return readiness fields to merge onto a campaign dict."""
    kind = classify_content_kind(campaign)
    text = _blob(campaign)
    materials = _material_signals(campaign)
    strict = _count_strict_rules(text)
    budget_left = 0.0
    try:
        budget_left = float(campaign.get("budget_left") or 0)
    except (TypeError, ValueError):
        budget_left = 0.0
    status_raw = str(campaign.get("status") or "active").lower()

    # --- hard skip ---
    if kind in {"ugc", "slideshow"}:
        return _result(
            kind,
            STATUS_LEWATI,
            "Bukan campaign clipping (UGC/slideshow)."
            if kind != "slideshow"
            else "Ini slideshow, bukan clipping video.",
            ease=0.15,
            safety=0.4,
            materials=materials,
            strict=strict,
        )
    if status_raw not in {"active", ""}:
        return _result(kind, STATUS_LEWATI, "Campaign tidak aktif.", 0.1, 0.5, materials, strict)
    if budget_left < BUDGET_GONE:
        return _result(
            kind,
            STATUS_LEWATI,
            "Sisa budget sudah hampir habis.",
            0.2,
            0.3,
            materials,
            strict,
        )
    if kind == "other" and not materials["has_public_hint"] and not strict["provided_footage"]:
        return _result(
            kind,
            STATUS_LEWATI,
            "Tidak jelas ini clipping; bahan resmi juga belum terlihat.",
            0.25,
            0.35,
            materials,
            strict,
        )

    # --- ease 0..1 ---
    ease = 0.45
    if materials["has_public_hint"] or materials["docs_fetched"]:
        ease += 0.22
    if materials["has_youtube"] or materials["has_direct_media"]:
        ease += 0.08
    if strict["provided_footage"]:
        ease += 0.10
    if materials["has_login_portal"]:
        ease -= 0.25
    if strict["account_heavy"]:
        ease -= 0.22
    if strict["caption_strict"]:
        ease -= 0.12
    if strict["watermark_strict"]:
        ease -= 0.08
    if not materials["has_public_hint"] and not materials["docs_fetched"]:
        ease -= 0.18
    ease = max(0.0, min(1.0, ease))

    # --- safety 0..1 (rules clarity + reject risk) ---
    safety = 0.50
    if materials["docs_fetched"] or materials["has_docs"]:
        safety += 0.18
    if strict["provided_footage"]:
        safety += 0.10
    if strict["discord_centric"]:
        safety -= 0.25
    if not text.strip() or len(text) < 80:
        safety -= 0.15
    # Strict but written rules are safer than vague rules
    if strict["caption_strict"] or strict["fixed_tag"]:
        safety += 0.05
    if materials["has_login_portal"] and not materials["has_public_hint"]:
        safety -= 0.05
    safety = max(0.0, min(1.0, safety))

    # --- status ---
    needs_google = materials["has_drive"] and not materials["has_youtube"] and not materials["has_direct_media"]
    # Drive may still be public via gdown; "belum siap" only when login portal
    # dominates or zero material hints.
    if materials["has_login_portal"] and not (materials["has_youtube"] or materials["has_direct_media"]):
        status = STATUS_BELUM
        reason = "Bahan ada di portal berlogin (bukan Drive/YouTube publik)."
    elif not materials["has_public_hint"] and not materials["docs_fetched"] and not strict["provided_footage"]:
        status = STATUS_BELUM
        reason = "Bahan resmi belum terdeteksi di halaman campaign."
    elif strict["account_heavy"] or (
        strict["caption_strict"] and strict["watermark_strict"]
    ) or (strict["caption_strict"] and strict["fixed_tag"] and strict["watermark_strict"]):
        status = STATUS_KETAT
        bits = []
        if strict["account_heavy"]:
            bits.append("aturan akun/warmup ketat")
        if strict["caption_strict"]:
            bits.append("caption wajib teks tertentu")
        if strict["fixed_tag"]:
            bits.append("wajib tag akun")
        if strict["watermark_strict"]:
            bits.append("watermark wajib")
        reason = "Bisa dikerjakan, tapi " + ", ".join(bits[:3]) + "."
    elif ease >= 0.55 and safety >= 0.45 and materials["has_public_hint"]:
        status = STATUS_SIAP
        if materials["has_youtube"]:
            reason = "Clipping dengan bahan YouTube/sumber publik terdeteksi."
        elif materials["has_drive"]:
            reason = "Clipping dengan folder/file Drive terdeteksi."
        elif materials["has_docs"]:
            reason = "Ada Google Docs rules; bahan tercantum di materi campaign."
        else:
            reason = "Bahan resmi terdeteksi dan aturan relatif sederhana."
    elif ease >= 0.35 and (materials["has_public_hint"] or materials["docs_fetched"]):
        status = STATUS_KETAT
        reason = "Bahan ada, tetapi aturan campaign cukup ketat atau perlu cek manual."
    else:
        status = STATUS_BELUM
        reason = "Belum cukup bukti bahan mudah diambil; sambungkan Google nanti jika perlu Drive."

    if needs_google and status == STATUS_SIAP and not materials["docs_fetched"]:
        # Soften: public Drive often works with gdown; keep siap but mention
        reason = "Bahan di Google Drive; mesin akan coba ambil (publik). Jika gagal, perlu akun Google."

    return _result(kind, status, reason, ease, safety, materials, strict)


def _result(
    kind: str,
    status: str,
    reason: str,
    ease: float,
    safety: float,
    materials: dict[str, Any],
    strict: dict[str, bool],
) -> dict[str, Any]:
    return {
        "content_kind": kind,
        "is_clipping": kind == "clipping",
        "readiness_status": status,
        "readiness_label": LABELS.get(status, status),
        "readiness_reason": reason,
        "readiness_ease": round(ease, 3),
        "readiness_safety": round(safety, 3),
        "readiness_materials": {
            "has_youtube": materials.get("has_youtube"),
            "has_drive": materials.get("has_drive"),
            "has_docs": materials.get("has_docs"),
            "has_direct_media": materials.get("has_direct_media"),
            "has_login_portal": materials.get("has_login_portal"),
            "has_public_hint": materials.get("has_public_hint"),
            "docs_fetched": materials.get("docs_fetched"),
            "url_count": materials.get("url_count"),
        },
        "readiness_flags": [k for k, v in strict.items() if v],
    }


def apply_readiness(campaign: dict[str, Any]) -> dict[str, Any]:
    """Mutate campaign with readiness fields and return it."""
    result = assess_readiness(campaign)
    campaign.update(result)
    return campaign


def readiness_sort_key(campaign: Mapping[str, Any]) -> tuple:
    """Sort: siap first, then ketat, belum, lewati; higher ease inside bucket."""
    order = {STATUS_SIAP: 0, STATUS_KETAT: 1, STATUS_BELUM: 2, STATUS_LEWATI: 3}
    status = str(campaign.get("readiness_status") or STATUS_LEWATI)
    return (
        order.get(status, 9),
        -float(campaign.get("readiness_ease") or 0),
        -float(campaign.get("readiness_safety") or 0),
        -float(campaign.get("score") or 0),
    )


__all__ = [
    "STATUS_SIAP",
    "STATUS_KETAT",
    "STATUS_BELUM",
    "STATUS_LEWATI",
    "LABELS",
    "classify_content_kind",
    "assess_readiness",
    "apply_readiness",
    "readiness_sort_key",
]
