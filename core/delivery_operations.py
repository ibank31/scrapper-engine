"""Pure delivery operation model for idempotent provider workflows."""
from __future__ import annotations

import hashlib
import json
from typing import Any

OPERATION_SCHEMA_VERSION = 1
STATES = {"pending", "attempting", "unknown", "scheduled", "published", "failed", "cancelled"}
TRANSITIONS = {
    "pending": {"attempting", "cancelled"},
    "attempting": {"scheduled", "unknown", "failed", "cancelled"},
    "unknown": {"scheduled", "published", "failed", "attempting", "cancelled"},
    "scheduled": {"published", "failed", "unknown", "cancelled"},
    "published": set(),
    "failed": {"attempting", "cancelled"},
    "cancelled": set(),
}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict): return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list): return [_canonical(item) for item in value]
    return value


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_canonical(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def operation_key(preview_id: str, channel_id: str, schedule_revision: str, caption_revision_id: str) -> str:
    raw = "|".join([str(preview_id), str(channel_id), str(schedule_revision), str(caption_revision_id)])
    return "delivery-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> dict[str, Any]:
    if current not in STATES or target not in STATES or not can_transition(current, target):
        raise ValueError(f"invalid delivery transition: {current} -> {target}")
    return {"from": current, "to": target}


def build_operation(*, preview_id: str, channel_id: str, schedule_intent: dict[str, Any], caption_revision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    revision = str(schedule_intent.get("schedule_revision") or schedule_intent.get("capability_version") or "schedule-v1")
    return {"schema_version": OPERATION_SCHEMA_VERSION, "operation_key": operation_key(preview_id, channel_id, revision, caption_revision_id), "preview_id": preview_id, "channel_id": channel_id, "schedule_revision": revision, "caption_revision_id": caption_revision_id, "payload_hash": payload_hash(payload), "schedule_intent": schedule_intent, "provider_state": "pending", "retry_class": "not_attempted", "provider_post_id": None, "provider_due_at": None, "provider_response": {}, "last_error": None, "attempt_count": 0}


__all__ = ["OPERATION_SCHEMA_VERSION", "STATES", "build_operation", "can_transition", "operation_key", "payload_hash", "transition"]
