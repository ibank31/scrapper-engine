"""Provider-neutral sound and native-tag evidence states."""
from __future__ import annotations

from typing import Any

STATUSES = {"verified", "unsupported", "manual_required", "failed"}


def normalize_sound_tags(*, platform: str, policy: str | None, source: str | None = None, track_id: str | None = None, evidence: dict[str, Any] | None = None, status: str | None = None, native_tags: list[str] | None = None) -> dict[str, Any]:
    requested = str(status or "manual_required")
    if requested not in STATUSES:
        requested = "manual_required"
    # Local metadata can never manufacture provider verification.
    if requested == "verified" and not evidence:
        requested = "manual_required"
    return {"schema_version": 1, "platform": str(platform), "policy": str(policy or "manual_required"), "source": source, "track_id": track_id, "evidence": evidence or {}, "status": requested, "native_tags": list(dict.fromkeys(str(x) for x in (native_tags or []) if str(x).strip()))}


def merge_provider_evidence(current: dict[str, Any], provider_evidence: dict[str, Any] | None, *, status: str) -> dict[str, Any]:
    if status not in STATUSES or status == "verified" and not provider_evidence:
        status = "manual_required"
    result = dict(current or {})
    result["evidence"] = provider_evidence or result.get("evidence") or {}
    result["status"] = status
    return result


__all__ = ["STATUSES", "merge_provider_evidence", "normalize_sound_tags"]
