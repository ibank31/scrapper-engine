"""All-or-nothing aggregate gate for the required rendered output pair."""
from __future__ import annotations

from typing import Any


def evaluate_output_pair(rendered: list[dict[str, Any]], validation_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Require two rendered artifacts and two non-failing validation records."""
    evidence = {
        "expected_count": 2,
        "rendered_count": len(rendered),
        "validation_count": len(validation_results or []),
        "validation_statuses": [item.get("status") for item in (validation_results or [])],
    }
    if len(rendered) != 2:
        return {"ok": False, "reason": "render_pair_incomplete", "evidence": evidence}
    if validation_results is None:
        return {"ok": True, "reason": None, "evidence": evidence}
    if len(validation_results) != 2:
        return {"ok": False, "reason": "validation_pair_incomplete", "evidence": evidence}
    if any(item.get("status") == "fail" for item in validation_results):
        return {"ok": False, "reason": "validation_pair_failed", "evidence": evidence}
    return {"ok": True, "reason": None, "evidence": evidence}


__all__ = ["evaluate_output_pair"]
