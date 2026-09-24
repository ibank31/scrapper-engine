"""Pure recovery and capacity policies for provider operations."""
from __future__ import annotations

import hashlib
import random
from typing import Any

RETRY_CLASSES = {"transient", "throttled", "permanent", "unknown_outcome", "capacity", "not_retryable"}


def classify_provider_error(*, http_status: int | None = None, timeout: bool = False, unknown_outcome: bool = False, message: str = "") -> str:
    if unknown_outcome or timeout: return "unknown_outcome"
    if http_status == 429: return "throttled"
    if http_status is not None and 500 <= http_status < 600: return "transient"
    if any(token in message.lower() for token in ("timeout", "temporarily", "rate limit", "connection reset")): return "transient"
    return "permanent"


def retry_decision(retry_class: str, attempt_count: int, *, max_attempts: int = 3) -> dict[str, Any]:
    retryable = retry_class in {"transient", "throttled"} and attempt_count < max_attempts
    return {"retryable": retryable, "retry_class": retry_class, "attempt_count": attempt_count, "max_attempts": max_attempts, "reason": "bounded_transient_retry" if retryable else "manual_or_terminal"}


def jittered_delay(operation_key: str, attempt_count: int, *, base_seconds: float = 2.0, cap_seconds: float = 60.0) -> float:
    seed = int(hashlib.sha256(f"{operation_key}:{attempt_count}".encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    return min(cap_seconds, base_seconds * (2 ** max(0, attempt_count - 1)) + rng.uniform(0, base_seconds))


def capacity_preflight(*, selected_channels: int, channel_capacity: dict[str, int], channel_usage: dict[str, int], request_count: int, request_budget: int, requested_channel_ids: list[str]) -> dict[str, Any]:
    failures = []
    if selected_channels != len(requested_channel_ids): failures.append({"code": "channel_count_mismatch"})
    if selected_channels > 3: failures.append({"code": "free_plan_channel_limit", "limit": 3, "actual": selected_channels})
    if request_count >= request_budget: failures.append({"code": "request_budget_exhausted", "limit": request_budget, "actual": request_count})
    for channel_id in requested_channel_ids:
        capacity = int(channel_capacity.get(channel_id, 0)); used = int(channel_usage.get(channel_id, 0))
        if used >= capacity: failures.append({"code": "scheduled_capacity_exhausted", "channel_id": channel_id, "capacity": capacity, "used": used})
    return {"ok": not failures, "status": "pass" if not failures else "fail", "failures": failures}


def stuck_operation_alert(*, provider_state: str, updated_age_seconds: float, threshold_seconds: float = 900.0) -> dict[str, Any]:
    stuck = provider_state in {"attempting", "unknown"} and updated_age_seconds >= threshold_seconds
    return {"alert": stuck, "severity": "high" if stuck else "none", "provider_state": provider_state, "age_seconds": updated_age_seconds, "threshold_seconds": threshold_seconds}


__all__ = ["capacity_preflight", "classify_provider_error", "jittered_delay", "retry_decision", "stuck_operation_alert"]
