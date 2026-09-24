"""Evidence contract for a human-confirmed, low-volume pilot."""
from __future__ import annotations

REQUIRED_FIELDS = ("job_id", "run_id", "rules_hash", "source_hashes", "operation_keys", "provider_ids", "due_times", "terminal_states", "rollback_evidence")


def build_pilot_evidence(*, human_confirmation: bool, mutation_executed: bool = False, **values):
    missing = [field for field in REQUIRED_FIELDS if not values.get(field)]
    status = "ready_for_human_confirmation" if not missing and not mutation_executed and not human_confirmation else "confirmed" if not missing and human_confirmation else "blocked_missing_evidence"
    if mutation_executed and not human_confirmation:
        status = "blocked_confirmation_required"
    return {"schema_version": 1, "status": status, "human_confirmation": bool(human_confirmation), "mutation_executed": bool(mutation_executed), "missing": missing, **{field: values.get(field) for field in REQUIRED_FIELDS}}


__all__ = ["REQUIRED_FIELDS", "build_pilot_evidence"]
