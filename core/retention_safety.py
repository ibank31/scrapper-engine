"""Retention and media reachability decisions for preview/provider dependencies."""
from __future__ import annotations

from typing import Any

ACTIVE_OPERATION_STATES = {"planned", "pending", "attempting", "unknown", "scheduled", "unresolved"}
TERMINAL_OPERATION_STATES = {"published", "failed", "cancelled"}


def operation_requires_retention(state: str | None) -> bool:
    return str(state or "").lower() in ACTIVE_OPERATION_STATES


def retention_decision(*, preview_status: str, object_key: str | None, operations: list[dict[str, Any]], now_iso: str, expires_at: str | None = None) -> dict[str, Any]:
    active = [op for op in operations if operation_requires_retention(op.get("provider_state") or op.get("status"))]
    if active:
        return {"retain": True, "reason": "active_delivery_dependency", "operation_keys": [str(op.get("operation_key") or "") for op in active if op.get("operation_key")], "object_key": object_key, "evaluated_at": now_iso}
    if preview_status in {"pending_review", "changes_requested", "approved_for_manual_post", "pending_render"}:
        return {"retain": True, "reason": "review_or_approved_window", "operation_keys": [], "object_key": object_key, "evaluated_at": now_iso}
    return {"retain": False, "reason": "no_active_dependency", "operation_keys": [], "object_key": object_key, "expires_at": expires_at, "evaluated_at": now_iso}


def media_reachability_contract(*, url: str, content_type: str | None, content_length: int | None, accepts_ranges: bool, expected_hash: str | None = None, observed_hash: str | None = None) -> dict[str, Any]:
    failures = []
    if not url.startswith("https://"): failures.append({"field": "url", "code": "https_required"})
    if not content_type or not content_type.lower().startswith("video/"): failures.append({"field": "content_type", "code": "video_content_type_required", "actual": content_type})
    if not isinstance(content_length, int) or content_length <= 0: failures.append({"field": "content_length", "code": "positive_length_required", "actual": content_length})
    if not accepts_ranges: failures.append({"field": "accept_ranges", "code": "byte_ranges_required"})
    if expected_hash and observed_hash and expected_hash != observed_hash: failures.append({"field": "hash", "code": "artifact_hash_mismatch"})
    return {"ok": not failures, "status": "pass" if not failures else "fail", "failures": failures, "url": url, "content_type": content_type, "content_length": content_length, "accepts_ranges": accepts_ranges, "observed_hash": observed_hash}


__all__ = ["ACTIVE_OPERATION_STATES", "TERMINAL_OPERATION_STATES", "media_reachability_contract", "operation_requires_retention", "retention_decision"]
