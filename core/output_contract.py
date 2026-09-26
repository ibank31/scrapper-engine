"""Versioned campaign output-contract construction and validation."""
from __future__ import annotations

import math
from typing import Any


OUTPUT_CONTRACT_VERSION = "default-v1"
DISTINCTNESS_PROFILE = "default-v1"
INVALID_OUTPUT_CONTRACT_REASON = "blocked_invalid_output_contract"

_REQUIRED_FIELDS = (
    "version",
    "expected_count",
    "tier_allocation",  # distribution slots: tier_1 and tier_2
    "min_duration_seconds",
    "max_duration_seconds",
    "distinctness_profile",
)


def build_output_contract(
    min_duration_seconds: Any = 0,
    max_duration_seconds: Any = 0,
) -> dict[str, Any]:
    """Build the default two-output contract using tier labels as distribution slots."""
    return {
        "version": OUTPUT_CONTRACT_VERSION,
        "expected_count": 2,
        "tier_allocation": {"tier_1": 1, "tier_2": 1},
        "min_duration_seconds": 0 if min_duration_seconds is None else min_duration_seconds,
        "max_duration_seconds": 0 if max_duration_seconds is None else max_duration_seconds,
        "distinctness_profile": DISTINCTNESS_PROFILE,
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        return None
    return result if math.isfinite(result) else None


def validate_output_contract(contract: Any) -> dict[str, Any]:
    """Return a stable validation result and a worker/job-ready blocking reason."""
    if not isinstance(contract, dict):
        return _invalid("output_contract must be an object")

    missing = [field for field in _REQUIRED_FIELDS if field not in contract]
    if missing:
        return _invalid("missing required fields", fields=missing)

    if contract.get("version") != OUTPUT_CONTRACT_VERSION:
        return _invalid("invalid output contract version", field="version")
    if not isinstance(contract.get("expected_count"), int) or isinstance(contract.get("expected_count"), bool) or contract.get("expected_count") != 2:
        return _invalid("expected_count must be exactly 2", field="expected_count")

    allocation = contract.get("tier_allocation")
    if not isinstance(allocation, dict):
        return _invalid("tier_allocation must be an object", field="tier_allocation")
    if set(allocation) != {"tier_1", "tier_2"}:
        return _invalid("tier_allocation must contain tier_1 and tier_2 only", field="tier_allocation")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in allocation.values()):
        return _invalid("tier allocation values must be non-negative integers", field="tier_allocation")
    if allocation["tier_1"] != 1 or allocation["tier_2"] != 1:
        return _invalid("tier allocation must be exactly 1 Tier 1 and 1 Tier 2", field="tier_allocation")
    if sum(allocation.values()) != contract["expected_count"]:
        return _invalid("tier allocation must total expected_count", field="tier_allocation")

    minimum = _number(contract.get("min_duration_seconds"))
    maximum = _number(contract.get("max_duration_seconds"))
    if minimum is None or maximum is None or minimum < 0 or maximum < 0:
        return _invalid("duration bounds must be finite non-negative numbers", field="duration")
    if maximum and minimum and minimum > maximum:
        return _invalid("minimum duration cannot exceed maximum duration", field="duration")

    if not isinstance(contract.get("distinctness_profile"), str) or not contract["distinctness_profile"].strip():
        return _invalid("distinctness_profile must be a non-empty string", field="distinctness_profile")

    return {"valid": True, "reason": None, "errors": []}


def validate_plan_output_contract(plan: Any) -> dict[str, Any]:
    """Validate the contract carried by a compiled campaign plan."""
    if not isinstance(plan, dict) or "output_contract" not in plan:
        return _invalid("missing output_contract", field="output_contract")
    return validate_output_contract(plan["output_contract"])


def _invalid(message: str, **details: Any) -> dict[str, Any]:
    error = {"message": message, **details}
    return {
        "valid": False,
        "reason": INVALID_OUTPUT_CONTRACT_REASON,
        "errors": [error],
    }


__all__ = [
    "DISTINCTNESS_PROFILE",
    "INVALID_OUTPUT_CONTRACT_REASON",
    "OUTPUT_CONTRACT_VERSION",
    "build_output_contract",
    "validate_output_contract",
    "validate_plan_output_contract",
]
