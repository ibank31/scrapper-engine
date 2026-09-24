"""Provider-neutral schedule intent contract for Phase 3."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEDULE_CAPABILITY_VERSION = "schedule-capability-v1"
PRODUCT_CONTRACT = "next_queue_slot"
CAPABILITY_MATRIX = {
    "buffer": {"version": SCHEDULE_CAPABILITY_VERSION, "queue_slot": True, "exact_timezone_aware": False, "provider_status": "unverified_exact"},
}


def capability_matrix(provider: str = "buffer") -> dict[str, Any]:
    return dict(CAPABILITY_MATRIX.get(provider, {"version": SCHEDULE_CAPABILITY_VERSION, "queue_slot": False, "exact_timezone_aware": False, "provider_status": "unsupported"}))


def local_to_utc(local_iso: str, timezone: str) -> str:
    """Convert a local ISO datetime to a canonical UTC ISO instant."""
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {timezone}") from exc
    value = datetime.fromisoformat(local_iso.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    else:
        value = value.astimezone(zone)
    return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def build_schedule_intent(*, provider: str = "buffer", timezone: str = "UTC", requested_local: str | None = None) -> dict[str, Any]:
    matrix = capability_matrix(provider)
    if PRODUCT_CONTRACT != "next_queue_slot":
        raise ValueError("unsupported product schedule contract")
    intent = {"schema_version": 1, "contract": PRODUCT_CONTRACT, "provider": provider, "capability_version": matrix["version"], "timezone": timezone, "requested_local": requested_local, "requested_utc": local_to_utc(requested_local, timezone) if requested_local else None, "provider_mode": "automatic/addToQueue", "provider_due_at": None}
    return intent


__all__ = ["CAPABILITY_MATRIX", "PRODUCT_CONTRACT", "SCHEDULE_CAPABILITY_VERSION", "build_schedule_intent", "capability_matrix", "local_to_utc"]
