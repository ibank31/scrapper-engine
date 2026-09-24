"""Pure gates for the required Tier 1/Tier 2 output pair."""
from __future__ import annotations

import re
from itertools import combinations
from typing import Any


DISTINCTNESS_PROFILE = "default-v1"


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9$%]+", str(value or "").lower()))


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    if str(left.get("source_asset_id") or left.get("source") or "") != str(right.get("source_asset_id") or right.get("source") or ""):
        return 0.0
    start = max(float(left.get("start") or 0), float(right.get("start") or 0))
    end = min(float(left.get("end") or 0), float(right.get("end") or 0))
    intersection = max(0.0, end - start)
    shortest = max(0.001, min(float(left.get("end") or 0) - float(left.get("start") or 0), float(right.get("end") or 0) - float(right.get("start") or 0)))
    return intersection / shortest


def pairwise_distinctness(left: dict[str, Any], right: dict[str, Any], profile: str = DISTINCTNESS_PROFILE) -> dict[str, Any]:
    """Return auditable evidence for whether two candidates are materially distinct."""
    if profile != DISTINCTNESS_PROFILE:
        return {"profile": profile, "distinct": False, "reasons": ["unsupported_distinctness_profile"]}
    left_id, right_id = left.get("candidate_id"), right.get("candidate_id")
    same_candidate = bool(left_id and right_id and left_id == right_id)
    overlap = _overlap(left, right)
    left_tokens, right_tokens = _tokens(left.get("text")), _tokens(right.get("text"))
    token_similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens)) if left_tokens and right_tokens else 0.0
    same_source_hash = bool(left.get("source_hash") and left.get("source_hash") == right.get("source_hash"))
    same_transcript_window = bool(left.get("transcript_hash") and left.get("transcript_hash") == right.get("transcript_hash") and overlap >= 0.45)
    reasons: list[str] = []
    if same_candidate:
        reasons.append("same_candidate_id")
    if overlap >= 0.45:
        reasons.append("temporal_overlap")
    if same_source_hash and token_similarity >= 0.82:
        reasons.append("same_source_high_text_similarity")
    if same_transcript_window:
        reasons.append("same_transcript_window")
    if token_similarity >= 0.82 and abs(float(left.get("duration") or 0) - float(right.get("duration") or 0)) <= 12 and (same_source_hash or overlap >= 0.45):
        reasons.append("high_text_similarity")
    return {
        "profile": profile,
        "distinct": not reasons,
        "candidate_ids": [left_id, right_id],
        "source_asset_ids": [left.get("source_asset_id") or left.get("source"), right.get("source_asset_id") or right.get("source")],
        "temporal_overlap_ratio": round(overlap, 4),
        "token_similarity": round(token_similarity, 4),
        "same_source_hash": same_source_hash,
        "reasons": reasons,
    }


def _near_miss(item: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "candidate_id": item.get("candidate_id"),
        "tier": item.get("tier", "unknown"),
        "score": item.get("score"),
        "start": item.get("start"),
        "end": item.get("end"),
        "reason": reason,
    }


def select_required_output_pair(candidates: list[dict[str, Any]], contract: dict[str, Any] | None) -> dict[str, Any]:
    """Select one distinct eligible candidate for each required audience tier."""
    allocation = (contract or {}).get("tier_allocation") or {"tier_1": 1, "tier_2": 1}
    expected = {"tier_1": int(allocation.get("tier_1") or 0), "tier_2": int(allocation.get("tier_2") or 0)}
    eligible = {tier: sorted([item for item in candidates if item.get("tier") == tier], key=lambda item: (-float(item.get("score") or 0), float(item.get("start") or 0))) for tier in expected}
    actual = {tier: len(items) for tier, items in eligible.items()}
    diagnostics: dict[str, Any] = {
        "schema_version": 1,
        "distinctness_profile": (contract or {}).get("distinctness_profile") or DISTINCTNESS_PROFILE,
        "expected": expected,
        "actual": actual,
        "rejected_reasons": {},
        "near_misses": [],
    }
    if expected != {"tier_1": 1, "tier_2": 1}:
        diagnostics["rejected_reasons"]["contract"] = "required allocation is not one Tier 1 and one Tier 2"
        return {"ok": False, "reason": "blocked_insufficient_output_contract", "selected": [], "diagnostics": diagnostics}
    for tier in expected:
        if not eligible[tier]:
            diagnostics["rejected_reasons"][tier] = "no eligible candidate"
            diagnostics["near_misses"].extend(_near_miss(item, "unclassifiable_or_wrong_tier") for item in sorted(candidates, key=lambda x: -float(x.get("score") or 0))[:3])
    if diagnostics["rejected_reasons"]:
        diagnostics["near_misses"] = diagnostics["near_misses"][:3]
        return {"ok": False, "reason": "blocked_insufficient_output_contract", "selected": [], "diagnostics": diagnostics}

    pair_attempts = []
    for left, right in combinations(eligible["tier_1"] + eligible["tier_2"], 2):
        if {left.get("tier"), right.get("tier")} != {"tier_1", "tier_2"}:
            continue
        evidence = pairwise_distinctness(left, right, diagnostics["distinctness_profile"])
        pair_attempts.append((evidence["distinct"], -float(left.get("score") or 0) - float(right.get("score") or 0), left, right, evidence))
    pair_attempts.sort(key=lambda item: (not item[0], item[1]))
    for is_distinct, _score, left, right, evidence in pair_attempts:
        if is_distinct:
            selected = sorted([left, right], key=lambda item: 0 if item.get("tier") == "tier_1" else 1)
            diagnostics["pairwise_distinctness"] = evidence
            diagnostics["actual_selected"] = {"tier_1": 1, "tier_2": 1}
            return {"ok": True, "reason": None, "selected": selected, "diagnostics": diagnostics}
        if len(diagnostics["near_misses"]) < 3:
            diagnostics["near_misses"].append({"candidate_ids": evidence.get("candidate_ids"), "reason": ";".join(evidence.get("reasons") or ["not_materially_distinct"]), "evidence": evidence})
    diagnostics["rejected_reasons"]["distinctness"] = "no materially distinct Tier 1/Tier 2 pair"
    diagnostics["near_misses"] = diagnostics["near_misses"][:3]
    return {"ok": False, "reason": "blocked_insufficient_output_contract", "selected": [], "diagnostics": diagnostics}


__all__ = ["DISTINCTNESS_PROFILE", "pairwise_distinctness", "select_required_output_pair"]
