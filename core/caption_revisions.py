"""Immutable caption revisions with deterministic hashes."""
from __future__ import annotations

import hashlib
import json
from typing import Any


REVISION_SCHEMA_VERSION = 1
CHARACTER_COUNT_METHOD = "unicode-codepoints-v1"


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def revision_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(_canonical(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_caption_revision(*, text: str, fields: dict[str, Any] | None, platform: str, revision_number: int, editor: str, rules_hash: str, platform_profile_version: str) -> dict[str, Any]:
    exact_text = str(text or "")
    revision = {
        "schema_version": REVISION_SCHEMA_VERSION,
        "text": exact_text,
        "fields": fields or {},
        "platform": str(platform),
        "revision_number": int(revision_number),
        "editor": str(editor or "system"),
        "character_count_method": CHARACTER_COUNT_METHOD,
        "character_count": len(exact_text),
        "rules_hash": str(rules_hash or ""),
        "platform_profile_version": str(platform_profile_version or ""),
    }
    revision["caption_hash"] = revision_hash(revision)
    revision["revision_id"] = f"caption-{revision['caption_hash'][:20]}"
    return revision


def is_current_revision(revision: dict[str, Any], *, revision_id: str, caption_hash: str, rules_hash: str) -> bool:
    return bool(revision and revision.get("revision_id") == revision_id and revision.get("caption_hash") == caption_hash and revision.get("rules_hash") == rules_hash)


__all__ = ["CHARACTER_COUNT_METHOD", "REVISION_SCHEMA_VERSION", "create_caption_revision", "is_current_revision", "revision_hash"]
