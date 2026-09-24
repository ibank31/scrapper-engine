"""Deterministic caption compliance validator shared by save/approval/preflight logic."""
from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return str(value or "")


def _contains(text: str, value: str) -> bool:
    return _text(value).casefold() in text.casefold()


def validate_caption_revision(revision: dict[str, Any], profile: dict[str, Any], *, expected_rules_hash: str | None = None) -> dict[str, Any]:
    text = _text(revision.get("text"))
    failures: list[dict[str, Any]] = []
    def fail(field: str, code: str, expected: Any, actual: Any = None) -> None:
        failures.append({"field": field, "code": code, "expected": expected, "actual": actual})

    for handle in profile.get("required_handles") or []:
        if not _contains(text, _text(handle)):
            fail("handles", "required_handle_missing", handle)
    for hashtag in profile.get("required_hashtags") or []:
        if not _contains(text, _text(hashtag)):
            fail("hashtags", "required_hashtag_missing", hashtag)
    for disclosure in profile.get("required_disclosures") or []:
        if not _contains(text, _text(disclosure)):
            fail("disclosures", "required_disclosure_missing", disclosure)
    for phrase in profile.get("required_phrases") or []:
        if not _contains(text, _text(phrase)):
            fail("phrases", "required_phrase_missing", phrase)
    for cta in profile.get("cta") or []:
        if not _contains(text, _text(cta)):
            fail("cta", "cta_missing", cta)
    for term in profile.get("prohibited_terms") or []:
        if _contains(text, _text(term)):
            fail("prohibited_terms", "prohibited_term_present", term)
    limit = int(profile.get("caption_limit") or 0)
    if limit and len(text) > limit:
        fail("text", "caption_too_long", limit, len(text))
    if expected_rules_hash is not None and revision.get("rules_hash") != expected_rules_hash:
        fail("rules_hash", "rules_hash_mismatch", expected_rules_hash, revision.get("rules_hash"))
    if revision.get("caption_hash"):
        from core.caption_revisions import revision_hash
        comparable = dict(revision)
        comparable.pop("caption_hash", None)
        comparable.pop("revision_id", None)
        if revision_hash(comparable) != revision.get("caption_hash"):
            fail("caption_hash", "caption_hash_mismatch", revision.get("caption_hash"))
    return {"ok": not failures, "status": "pass" if not failures else "fail", "platform": profile.get("platform"), "profile_version": profile.get("version"), "failures": failures}


__all__ = ["validate_caption_revision"]
