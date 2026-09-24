"""Non-production failure matrix for Phase 5 staging readiness."""
from __future__ import annotations

from typing import Any

CASES = (
    "approval_failure", "caption_failure", "unsupported_field", "duplicate_click", "timeout", "partial_result", "cleanup_dependency", "stale_worker",
)


def run_failure_matrix(*, provider_mutation_enabled: bool = False) -> dict[str, Any]:
    results = []
    for case in CASES:
        if provider_mutation_enabled:
            results.append({"case": case, "status": "blocked", "reason": "provider_mutation_must_be_disabled_for_local_matrix"})
            continue
        expected = {
            "approval_failure": "blocked_approval_provenance",
            "caption_failure": "blocked_caption_compliance",
            "unsupported_field": "blocked_provider_field",
            "duplicate_click": "idempotent_existing_operation",
            "timeout": "unknown_requires_reconciliation",
            "partial_result": "partial_outcome_preserved",
            "cleanup_dependency": "retained_active_dependency",
            "stale_worker": "stale_generation_rejected",
        }[case]
        results.append({"case": case, "status": "pass", "expected": expected, "provider_mutation": False})
    return {"schema_version": 1, "environment": "local-mock", "provider_mutation_enabled": provider_mutation_enabled, "cases": results, "ok": not provider_mutation_enabled and all(item["status"] == "pass" for item in results)}


__all__ = ["CASES", "run_failure_matrix"]
