#!/usr/bin/env python3
"""Deterministic, provenance-preserving Campaign Rule Reconciliation (CA-03).

The reconciler consumes source evidence, the canonical Campaign Brain, and the
read-only Campaign Critic output. It never edits its inputs, calls an LLM, or
silently discards a critic finding.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 1


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return _norm(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return value


def _value_key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prefix: str, value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reconciled_rule_id(campaign_id: str, rule: dict[str, Any]) -> str:
    payload = {key: rule[key] for key in ("source_rule_path", "value", "requirement_level", "scope", "evidence_ids", "brain_rule_ids")}
    return _hash("reconciled-rule-v1:", {"campaign_id": campaign_id, **payload})


def _path(value: Any) -> str:
    return _norm(value).lower().removeprefix("rules.")


def _scope(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, dict) else {}
    return {
        dimension: sorted({_norm(item).lower() for item in raw.get(dimension, []) or [] if _norm(item)})
        for dimension in ("platforms", "languages", "audiences")
    }


def _scope_overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Empty scope means global; disjoint explicit dimensions are valid variants."""
    for dimension in ("platforms", "languages", "audiences"):
        a, b = set(_scope(left).get(dimension, [])), set(_scope(right).get(dimension, []))
        if a and b and not a.intersection(b):
            return False
    return True


def _evidence_index(evidence_contract: dict[str, Any], brain: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    sources = [evidence_contract.get("verified"), (brain.get("evidence") or {}).get("verified")]
    for collection in sources:
        for item in collection or []:
            if isinstance(item, dict) and item.get("evidence_id"):
                key = str(item["evidence_id"])
                if key not in result or (not result[key].get("source_url") and item.get("source_url")):
                    result[key] = dict(item)
    return result


def _references(evidence_items: list[dict[str, Any]], brain_rule: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for item in evidence_items:
        ref = {
            "source_type": str(item.get("source_type") or ""),
            "location": str(item.get("location") or ""),
            "source_url": item.get("source_url"),
        }
        refs[_value_key(ref)] = ref
    for item in (brain_rule or {}).get("source_references") or []:
        if isinstance(item, dict):
            ref = {"source_type": str(item.get("source_type") or ""), "location": str(item.get("location") or ""), "source_url": item.get("source_url")}
            refs[_value_key(ref)] = ref
    return sorted(refs.values(), key=lambda item: (item["source_type"], item["location"], str(item["source_url"] or "")))


def _requirement_for_evidence(campaign: dict[str, Any], evidence: dict[str, Any]) -> str:
    quote = _norm(evidence.get("quote")).lower()
    path = _path(evidence.get("rule_path"))
    for item in campaign.get("expected_evidence") or []:
        if not isinstance(item, dict):
            continue
        same_quote = _norm(item.get("quote")).lower() == quote
        same_path = not item.get("rule_path") or _path(item.get("rule_path")) == path
        if same_quote and same_path and "mandatory" in item:
            return "mandatory" if bool(item.get("mandatory")) else "optional"
    for item in campaign.get("requirements") or []:
        text = _norm(item.get("text") if isinstance(item, dict) else item)
        if text and (text.lower() in quote or quote in text.lower()):
            if not isinstance(item, dict) or bool(item.get("isMandatory", True)):
                return "mandatory"
            return "optional"
    return "unknown"


def _candidate(
    *, path: str, value: Any, requirement: str, scope: dict[str, Any], evidence_ids: list[str],
    evidence_index: dict[str, dict[str, Any]], brain_rule_ids: list[str], method: str,
    reason: str, brain_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ids = sorted(set(str(item) for item in evidence_ids if item))
    items = [evidence_index[item] for item in ids if item in evidence_index]
    priority = max((int(item.get("source_priority") or 0) for item in items), default=0)
    normalized_scope = _scope(scope)
    return {
        "source_rule_path": _norm(path),
        "value": _canonical(value),
        "requirement_level": requirement if requirement in {"mandatory", "optional", "unknown"} else "unknown",
        "scope": normalized_scope,
        "evidence_ids": ids,
        "source_references": _references(items, brain_rule),
        "brain_rule_ids": sorted(set(str(item) for item in brain_rule_ids if item)),
        "source_priority": priority,
        "resolution": {"status": "resolved", "method": method, "reason": reason},
    }


def _finding_severity(finding: dict[str, Any]) -> str:
    return str(finding.get("severity") or "INFO").upper()


def reconcile_campaign_rules(
    campaign: dict[str, Any],
    evidence_contract: dict[str, Any] | None,
    campaign_brain: dict[str, Any],
    campaign_critic: dict[str, Any],
) -> dict[str, Any]:
    """Produce a deterministic reconciliation contract from the CA-00–CA-02 chain."""
    evidence_contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    brain = campaign_brain if isinstance(campaign_brain, dict) else {}
    critic = campaign_critic if isinstance(campaign_critic, dict) else {}
    campaign_id = str(campaign.get("id") or "")
    source_hash = str(evidence_contract.get("source_hash") or brain.get("source_hash") or "")
    brain_id, critic_id = str(brain.get("brain_id") or ""), str(critic.get("critic_id") or "")
    evidence_by_id = _evidence_index(evidence_contract, brain)
    findings = [item for item in critic.get("findings") or [] if isinstance(item, dict)]
    integrity_errors = []
    if str(brain.get("campaign_id") or campaign_id) != campaign_id:
        integrity_errors.append("brain_campaign_id_mismatch")
    if critic.get("campaign_id") is not None and str(critic.get("campaign_id")) != campaign_id:
        integrity_errors.append("critic_campaign_id_mismatch")
    if brain.get("source_hash") and source_hash and brain.get("source_hash") != source_hash:
        integrity_errors.append("brain_source_hash_mismatch")
    if critic.get("source_hash") and source_hash and critic.get("source_hash") != source_hash:
        integrity_errors.append("critic_source_hash_mismatch")
    if critic.get("brain_id") and brain_id and critic.get("brain_id") != brain_id:
        integrity_errors.append("critic_brain_id_mismatch")

    candidates: list[dict[str, Any]] = []
    # Never promote a model-only inference. Source-backed Brain rules retain their
    # canonical value and complete evidence chain.
    for rule in brain.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        evidence_ids = [str(item) for item in rule.get("evidence_ids") or [] if str(item) in evidence_by_id]
        interpretation = _norm(rule.get("interpretation_type")).lower()
        if not evidence_ids or interpretation in {"unsupported", "inferred"} and not evidence_ids:
            continue
        candidate = _candidate(
            path=str(rule.get("source_rule_path") or ""), value=rule.get("value"),
            requirement=str(rule.get("requirement_level") or "unknown"), scope=rule.get("scope"),
            evidence_ids=evidence_ids, evidence_index=evidence_by_id,
            brain_rule_ids=[str(rule.get("rule_id") or "")], method="evidence_backed_brain_rule",
            reason="Retained the canonical Brain value because its linked evidence is present in the current evidence contract.",
            brain_rule=rule,
        )
        if interpretation in {"ambiguous", "conflicting", "manual_required"}:
            candidate["resolution"] = {
                "status": "unresolved", "method": "brain_semantics_require_review",
                "reason": f"The source-backed Brain rule is marked {interpretation}; CA-03 preserves it but cannot assert a unique canonical interpretation.",
            }
        candidates.append(candidate)

    # Reconstruct only explicit missing-rule findings, and only from cited verified
    # evidence. A quote is retained as an opaque source-backed value; semantics not
    # established by structured campaign requirements remain unknown.
    reconstructed_by_finding: dict[str, list[int]] = {}
    for finding in findings:
        if str(finding.get("code") or "").upper() not in {"MISSING_RULE", "MISSING_MATERIAL_REQUIREMENT"}:
            continue
        path = _norm(finding.get("rule_path") or "")
        evidence_ids = sorted({str(item) for item in finding.get("evidence_ids") or [] if str(item) in evidence_by_id})
        for evidence_id in evidence_ids:
            evidence = evidence_by_id[evidence_id]
            if _path(evidence.get("rule_path")) and _path(evidence.get("rule_path")) != _path(path):
                continue
            value = _norm(evidence.get("quote"))
            if not value:
                continue
            index = len(candidates)
            candidates.append(_candidate(
                path=path or str(evidence.get("rule_path") or ""), value=value,
                requirement=_requirement_for_evidence(campaign, evidence),
                scope={}, evidence_ids=[evidence_id], evidence_index=evidence_by_id,
                brain_rule_ids=[], method="reconstructed_from_evidence",
                reason="Reconstructed the omitted rule as an opaque source quote; no unsupported semantic value was inferred.",
            ))
            reconstructed_by_finding.setdefault(str(finding.get("finding_id") or ""), []).append(index)

    # Coalesce exact same-scope agreements without losing any evidence or rule IDs.
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        scope = candidate["scope"]
        key = (_path(candidate["source_rule_path"]), _value_key(candidate["value"]), _value_key(candidate["requirement_level"]), _value_key(scope))
        grouped.setdefault(key, []).append(candidate)
    agreed: list[dict[str, Any]] = []
    for key in sorted(grouped):
        group = grouped[key]
        base = dict(group[0])
        base["evidence_ids"] = sorted({eid for item in group for eid in item["evidence_ids"]})
        base["source_references"] = sorted({ _value_key(ref): ref for item in group for ref in item["source_references"] }.values(), key=lambda item: (item["source_type"], item["location"], str(item["source_url"] or "")))
        base["brain_rule_ids"] = sorted({rid for item in group for rid in item["brain_rule_ids"]})
        base["source_priority"] = max(item["source_priority"] for item in group)
        if len(group) > 1:
            base["resolution"] = {"status": "resolved", "method": "exact_agreement", "reason": "Equivalent value, requirement semantics, and scope were coalesced; all provenance was retained."}
        agreed.append(base)

    conflicts: list[dict[str, Any]] = []
    by_path: dict[str, list[dict[str, Any]]] = {}
    for item in agreed:
        by_path.setdefault(_path(item["source_rule_path"]), []).append(item)
    rejected_finding_ids: set[str] = set()
    unsupported_ids = {str(item.get("finding_id") or "") for item in findings if str(item.get("code") or "").upper() in {"UNSUPPORTED_INFERENCE", "UNSUPPORTED_MANDATORY_INFERENCE"}}
    for finding in findings:
        if str(finding.get("finding_id") or "") in unsupported_ids:
            rejected_finding_ids.add(str(finding.get("finding_id") or ""))

    resolved_rules: list[dict[str, Any]] = []
    handled: set[int] = set()
    for path in sorted(by_path):
        group = by_path[path]
        for index, item in enumerate(group):
            if index in handled:
                continue
            cluster = [item]
            for other_index in range(index + 1, len(group)):
                if _scope_overlaps(item["scope"], group[other_index]["scope"]):
                    cluster.append(group[other_index])
                    handled.add(other_index)
            if len(cluster) == 1:
                resolved_rules.append(cluster[0])
                if cluster[0]["resolution"]["status"] == "unresolved":
                    conflict_payload = {
                        "path": path,
                        "evidence_ids": cluster[0]["evidence_ids"],
                        "brain_rule_ids": cluster[0]["brain_rule_ids"],
                        "method": cluster[0]["resolution"]["method"],
                    }
                    conflicts.append({
                        "conflict_id": _hash("reconciliation-ambiguity-v1:", conflict_payload),
                        "kind": "brain_semantic_ambiguity", "rule_path": cluster[0]["source_rule_path"],
                        "status": "unresolved", "evidence_ids": cluster[0]["evidence_ids"],
                        "rule_ids": [_hash("reconciled-rule-v1:", {
                            "campaign_id": campaign_id,
                            **{key: cluster[0][key] for key in ("source_rule_path", "value", "requirement_level", "scope", "evidence_ids", "brain_rule_ids")},
                        })],
                        "brain_rule_ids": cluster[0]["brain_rule_ids"],
                        "reason": cluster[0]["resolution"]["reason"],
                    })
                continue
            # A conflict exists only for different values or requirement semantics
            # on overlapping scopes. Equal-scope exact agreements were coalesced.
            priorities = [candidate["source_priority"] for candidate in cluster]
            highest = max(priorities)
            winners = [candidate for candidate in cluster if candidate["source_priority"] == highest]
            if highest > 0 and len(winners) == 1 and all(candidate["resolution"]["status"] == "resolved" for candidate in cluster):
                winner = winners[0]
                winner["resolution"] = {
                    "status": "resolved", "method": "explicit_source_priority",
                    "reason": "The unique highest-priority cited source wins; all lower-priority alternatives are retained in the conflict record.",
                    "winner_evidence_ids": list(winner["evidence_ids"]),
                    "loser_evidence_ids": sorted({eid for candidate in cluster if candidate is not winner for eid in candidate["evidence_ids"]}),
                }
                resolved_rules.append(winner)
                resolution_status = "resolved"
                method = "explicit_source_priority"
            else:
                resolution_status, method = "unresolved", "no_unique_source_precedence"
                for candidate in cluster:
                    candidate["resolution"] = {"status": "unresolved", "method": method, "reason": "Overlapping source-backed rules disagree and available metadata provides no unique authoritative winner."}
                    resolved_rules.append(candidate)
            conflict_payload = {
                "campaign_id": campaign_id, "rule_path": path,
                "rule_ids": sorted(_hash("reconciled-rule-v1:", {
                    "campaign_id": campaign_id,
                    **{key: candidate[key] for key in ("source_rule_path", "value", "requirement_level", "scope", "evidence_ids", "brain_rule_ids")},
                }) for candidate in cluster),
                "evidence_ids": sorted({eid for candidate in cluster for eid in candidate["evidence_ids"]}),
                "method": method,
            }
            conflicts.append({
                "conflict_id": _hash("reconciliation-conflict-v1:", conflict_payload),
                "kind": "overlapping_rule_disagreement", "rule_path": path,
                "status": resolution_status, "method": method,
                "rule_ids": conflict_payload["rule_ids"], "evidence_ids": conflict_payload["evidence_ids"],
                "reason": "Conflicting values or requirement semantics on overlapping scopes were not silently overwritten.",
            })

    # Every critic finding gets an explicit resolution record, even if it remains
    # open for human review. This is the anti-silent-disappearance invariant.
    finding_records: list[dict[str, Any]] = []
    for finding in findings:
        fid = str(finding.get("finding_id") or _hash("critic-finding-fallback:", finding))
        code = str(finding.get("code") or "UNKNOWN")
        path = _path(finding.get("rule_path"))
        finding_evidence = {str(item) for item in finding.get("evidence_ids") or []}
        matching = [rule for rule in resolved_rules if _path(rule["source_rule_path"]) == path and finding_evidence.intersection(rule["evidence_ids"])]
        reconstructed = reconstructed_by_finding.get(fid, [])
        if fid in rejected_finding_ids:
            status, method, reason = "resolved", "rejected_unsupported_inference", "The unsupported model-only inference was excluded from canonical reconciled rules; no evidence was available to promote it."
        elif code.upper() in {"MISSING_RULE", "MISSING_MATERIAL_REQUIREMENT"} and reconstructed:
            status, method, reason = "resolved", "reconstructed_from_evidence", "The missing rule was reconstructed from its verified source evidence and retained with provenance."
        elif code.upper() == "DUPLICATE_RULE" and any(rule["resolution"]["method"] == "exact_agreement" for rule in matching):
            status, method, reason = "resolved", "exact_agreement", "Duplicate equivalent rules were coalesced while preserving all Brain rule and evidence IDs."
        elif matching and all(rule["resolution"]["status"] == "resolved" for rule in matching) and any(rule["resolution"]["method"] == "explicit_source_priority" for rule in matching):
            status, method, reason = "resolved", "explicit_source_priority", "A unique authoritative source determined the canonical value; alternatives remain visible in conflicts."
        elif code.upper() in {"UNSUPPORTED_INFERENCE", "UNSUPPORTED_MANDATORY_INFERENCE"}:
            status, method, reason = "resolved", "rejected_unsupported_inference", "The unsupported inference is not promoted to a canonical rule."
        else:
            status, method, reason = "unresolved", "requires_review", "Available verified evidence and explicit source metadata do not justify a safe deterministic repair. The original critic finding remains visible."
        finding_records.append({
            "finding_id": fid, "code": code, "severity": _finding_severity(finding),
            "rule_path": _norm(finding.get("rule_path") or ""), "evidence_ids": sorted(finding_evidence),
            "status": status, "method": method, "reason": reason,
        })
        if status == "unresolved":
            conflicts.append({
                "conflict_id": _hash("reconciliation-finding-v1:", {"finding_id": fid, "status": status, "method": method}),
                "kind": "critic_finding", "critic_finding_id": fid, "rule_path": _norm(finding.get("rule_path") or ""),
                "status": "unresolved", "severity": _finding_severity(finding), "code": code,
                "evidence_ids": sorted(finding_evidence), "reason": reason,
                "rule_ids": sorted(_reconciled_rule_id(campaign_id, rule) for rule in matching),
            })

    # Stable rule identities include their complete source lineage and semantics.
    final_rules = []
    for item in resolved_rules:
        final_rules.append({"rule_id": _reconciled_rule_id(campaign_id, item), **item})
    final_rules.sort(key=lambda item: (_path(item["source_rule_path"]), _value_key(item["scope"]), _value_key(item["value"]), item["rule_id"]))
    conflict_ids_by_rule: dict[str, set[str]] = {}
    for conflict in conflicts:
        for rule_id in conflict.get("rule_ids") or []:
            conflict_ids_by_rule.setdefault(str(rule_id), set()).add(str(conflict["conflict_id"]))
    for item in final_rules:
        item["conflict_ids"] = sorted(conflict_ids_by_rule.get(item["rule_id"], set()))
    conflicts.sort(key=lambda item: (item.get("kind", ""), item.get("rule_path", ""), item.get("conflict_id", "")))
    finding_records.sort(key=lambda item: (item["code"], item["rule_path"], item["finding_id"]))
    unresolved = [item for item in finding_records if item["status"] == "unresolved"]
    critical_unresolved = any(item["severity"] == "CRITICAL" for item in unresolved)
    unresolved_rules = [item for item in final_rules if item["resolution"]["status"] == "unresolved"]
    status = "blocked" if integrity_errors or critical_unresolved else "review" if unresolved or unresolved_rules else "resolved"
    stable = {
        "schema_version": SCHEMA_VERSION, "campaign_id": campaign_id,
        "source_hash": source_hash, "brain_id": brain_id, "critic_id": critic_id,
        "status": status, "rules": final_rules, "conflicts": conflicts,
        "findings": finding_records,
        "integrity_errors": sorted(integrity_errors),
        "summary": {
            "rule_count": len(final_rules), "conflict_count": len(conflicts),
            "critic_finding_count": len(finding_records),
            "resolved_finding_count": sum(item["status"] == "resolved" for item in finding_records),
            "unresolved_finding_count": len(unresolved),
            "unresolved_critical_count": sum(item["status"] == "unresolved" and item["severity"] == "CRITICAL" for item in finding_records),
            "unresolved_rule_count": len(unresolved_rules),
        },
    }
    stable["reconciliation_id"] = _hash("reconciliation-v1:", stable)
    return stable


__all__ = ["SCHEMA_VERSION", "reconcile_campaign_rules"]
