#!/usr/bin/env python3
"""Deterministic Campaign Critic for CA-02.

The critic challenges a canonical Campaign Brain against source-backed evidence.
It never mutates the Brain and does not resolve conflicts; reconciliation belongs
 to CA-03.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable

from core.campaign_evidence import source_fingerprint, verify_quote

SCHEMA_VERSION = 1
SEVERITIES = ("CRITICAL", "WARNING", "AMBIGUITY", "INFO")
_PLATFORMS = {"instagram", "tiktok", "youtube", "facebook", "x", "twitter", "linkedin", "threads"}
_MATERIAL_WORDS = re.compile(r"\b(footage|asset|assets|logo|imagery|image|material|video|clip|source|product shot|product footage)\b", re.I)
_HANDLE_RE = re.compile(r"@[A-Za-z0-9._-]+")
_HASHTAG_RE = re.compile(r"#[A-Za-z0-9_]+")
_URL_RE = re.compile(r"https?://[^\s)\]}>,]+", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:\s*[-–]\s*\d+)?\s*(?:seconds?|secs?|detik|s)?\b", re.I)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


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


def _leaf(path: Any) -> str:
    return _lower(path).removeprefix("rules.").split(".")[-1]


def _path_key(path: Any) -> str:
    return _lower(path).removeprefix("rules.")


def _rule_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_rule_values(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(_rule_values(item))
        return result
    text = _norm(value)
    return [text] if text else []


def _platforms(path: Any, quote: Any) -> set[str]:
    text = f"{_lower(path)} {_lower(quote)}"
    return {platform for platform in _PLATFORMS if re.search(rf"\b{re.escape(platform)}\b", text)}


def _scope(rule: dict[str, Any]) -> tuple[str, ...]:
    raw = rule.get("scope") if isinstance(rule.get("scope"), dict) else {}
    return tuple(sorted({_lower(item) for item in raw.get("platforms", []) if _norm(item)}))


def _is_mandatory(item: dict[str, Any]) -> bool:
    return bool(item.get("mandatory")) or _lower(item.get("requirement_level")) == "mandatory"


def _verified_evidence(brain: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = (brain.get("evidence") or {}).get("verified") if isinstance(brain.get("evidence"), dict) else []
    return [item for item in evidence or [] if isinstance(item, dict) and item.get("evidence_id")]


def _expected_evidence(campaign: dict[str, Any], brain: dict[str, Any]) -> list[dict[str, Any]]:
    """Use golden expected evidence when available, otherwise verified Brain evidence."""
    expected = [item for item in campaign.get("expected_evidence") or [] if isinstance(item, dict) and _norm(item.get("quote"))]
    if not expected:
        return _verified_evidence(brain)

    source_hash = source_fingerprint(campaign)
    result: list[dict[str, Any]] = []
    for item in expected:
        checked = verify_quote(campaign, item.get("quote"), source_hash=source_hash)
        entry = dict(item)
        entry.update({key: value for key, value in checked.items() if value is not None})
        entry["rule_path"] = _norm(item.get("rule_path"))
        result.append(entry)
    return result


def _evidence_by_id(brain: dict[str, Any], expected: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {str(item["evidence_id"]): item for item in _verified_evidence(brain) if item.get("evidence_id")}
    for item in expected:
        if item.get("evidence_id"):
            result[str(item["evidence_id"])] = item
    return result


def _bound_rules(expected: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_id = str(expected.get("evidence_id") or "")
    path = _path_key(expected.get("rule_path"))
    result = []
    for rule in rules:
        ids = {str(item) for item in rule.get("evidence_ids") or []}
        rule_path = _path_key(rule.get("source_rule_path"))
        if evidence_id and evidence_id in ids and (rule_path == path or rule_path.endswith("." + path) or path.endswith("." + rule_path)):
            result.append(rule)
    return result


def _references(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for item in items:
        refs.append({
            "source_type": str(item.get("source_type") or ""),
            "location": str(item.get("location") or ""),
            "source_url": item.get("source_url"),
        })
    return sorted({json.dumps(ref, ensure_ascii=False, sort_keys=True): ref for ref in refs}.values(), key=lambda ref: (ref["source_type"], ref["location"], str(ref["source_url"] or "")))


def _concrete_values(path: Any, quote: Any) -> list[str]:
    text = _norm(quote)
    leaf = _leaf(path)
    if leaf in {"handles", "handle", "account", "username"}:
        return [item.lower() for item in _HANDLE_RE.findall(text)]
    if leaf in {"hashtags", "hashtag", "native_tags"}:
        return [item.lower() for item in _HASHTAG_RE.findall(text)]
    if leaf in {"cta", "cta_text", "call_to_action"}:
        quoted = re.findall(r"[\"“‘']([^\"”’']+)[\"”’']", text)
        if quoted:
            return [_lower(max(quoted, key=len))]
        match = re.search(r"(?:cta|call to action)\s*:\s*(.+)$", text, re.I)
        if match:
            return [_norm(match.group(1))]
        return [_norm(text)] if text else []
    values = [item.lower().rstrip(".,;:") for item in _URL_RE.findall(text)]
    values.extend(item.lower() for item in _HANDLE_RE.findall(text))
    values.extend(item.lower() for item in _HASHTAG_RE.findall(text))
    values.extend(item.lower() for item in _NUMBER_RE.findall(text))
    return list(dict.fromkeys(values))


def _contains_value(rule: dict[str, Any], expected_values: Iterable[str], *, path: str) -> bool:
    actual = [_lower(item) for item in _rule_values(rule.get("value"))]
    actual_text = " ".join(actual)
    for expected in expected_values:
        wanted = _lower(expected).rstrip(".,;:")
        if not wanted:
            continue
        if _leaf(path) in {"handles", "handle", "account", "username", "hashtags", "hashtag", "native_tags"}:
            if wanted in actual or wanted in actual_text:
                return True
        elif wanted in actual_text or actual_text in wanted:
            return True
    return False


def _has_conflict_marker(brain: dict[str, Any], path: str) -> bool:
    target = _path_key(path)
    for key in ("conflicts", "variants"):
        for item in brain.get(key) or []:
            if _path_key(item.get("rule_path")) == target:
                return True
    return False


def _finding(
    *,
    campaign: dict[str, Any],
    code: str,
    severity: str,
    category: str,
    message: str,
    rule_path: str = "",
    brain_rules: Iterable[dict[str, Any]] = (),
    evidence: Iterable[dict[str, Any]] = (),
    reason: str,
) -> dict[str, Any]:
    rules = sorted({str(item.get("rule_id")) for item in brain_rules if item.get("rule_id")})
    evidence_items = sorted({str(item.get("evidence_id")): item for item in evidence if item.get("evidence_id")}.values(), key=lambda item: str(item.get("evidence_id")))
    evidence_ids = [str(item.get("evidence_id")) for item in evidence_items]
    source_references = _references(evidence_items)
    payload = {
        "campaign_id": str(campaign.get("id") or ""),
        "source_hash": source_fingerprint(campaign),
        "code": code,
        "severity": severity,
        "category": category,
        "rule_path": _norm(rule_path),
        "brain_rule_ids": rules,
        "evidence_ids": evidence_ids,
        "message": _norm(message),
        "reason": _norm(reason),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "finding_id": "finding-v1:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "severity": severity,
        "code": code,
        "category": category,
        "message": _norm(message),
        "rule_path": _norm(rule_path),
        "brain_rule_ids": rules,
        "evidence_ids": evidence_ids,
        "source_references": source_references,
        "reason": _norm(reason),
        "status": "open",
    }


def _append(findings: list[dict[str, Any]], **kwargs: Any) -> None:
    findings.append(kwargs.pop("finding")) if "finding" in kwargs else findings.append(_finding(**kwargs))


def critique_campaign(campaign: dict[str, Any], brain: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic findings without modifying ``brain``."""
    rules = [item for item in brain.get("rules") or [] if isinstance(item, dict)]
    expected = _expected_evidence(campaign, brain)
    by_id = _evidence_by_id(brain, expected)
    findings: list[dict[str, Any]] = []

    for item in expected:
        path = _norm(item.get("rule_path"))
        evidence = [item] if item.get("evidence_id") else []
        bound = _bound_rules(item, rules)
        mandatory = _is_mandatory(item)
        severity = "CRITICAL" if mandatory else "WARNING"
        leaf = _leaf(path)
        material = leaf in {"asset_sources", "material_policy", "material", "source_policy"} and bool(_MATERIAL_WORDS.search(_norm(item.get("quote"))) )
        if not bound:
            code = "MISSING_MATERIAL_REQUIREMENT" if material else "MISSING_RULE"
            category = "material_requirement" if material else "missing_rule"
            _append(findings, campaign=campaign, code=code, severity=severity, category=category,
                    message=f"Source-backed rule is missing from Campaign Brain: {path}.", rule_path=path,
                    evidence=evidence, reason="Verified source evidence has no canonical Brain rule bound to its evidence ID.")
            if leaf in {"cta", "cta_text", "handle", "handles", "hashtag", "hashtags"}:
                code = {"cta": "WRONG_CTA", "cta_text": "WRONG_CTA", "handle": "WRONG_HANDLE", "handles": "WRONG_HANDLE", "hashtag": "WRONG_HASHTAG", "hashtags": "WRONG_HASHTAG"}[leaf]
                _append(findings, campaign=campaign, code=code, severity=severity, category=leaf,
                        message=f"Source-backed {leaf} is missing from Campaign Brain.", rule_path=path,
                        evidence=evidence, reason="The source contains a concrete posting value but no Brain rule preserves it.")
            continue

        if _platforms(path, item.get("quote")):
            source_platforms = _platforms(path, item.get("quote"))
            for rule in bound:
                rule_platforms = set(_scope(rule))
                if rule_platforms != source_platforms:
                    _append(findings, campaign=campaign, code="PLATFORM_SCOPE_MISMATCH", severity=severity,
                            category="scope_mismatch", message=f"Brain scope {sorted(rule_platforms)} does not match source scope {sorted(source_platforms)}.",
                            rule_path=path, brain_rules=[rule], evidence=evidence,
                            reason="Platform scope must be no broader or narrower than the source evidence.")

        expected_values = _concrete_values(path, item.get("quote"))
        if leaf in {"cta", "cta_text", "handle", "handles", "hashtag", "hashtags"} and not any(_contains_value(rule, expected_values, path=path) for rule in bound):
            code = {"cta": "WRONG_CTA", "cta_text": "WRONG_CTA", "handle": "WRONG_HANDLE", "handles": "WRONG_HANDLE", "hashtag": "WRONG_HASHTAG", "hashtags": "WRONG_HASHTAG"}[leaf]
            _append(findings, campaign=campaign, code=code, severity=severity, category=leaf,
                    message=f"Brain value does not preserve the source-backed {leaf}.", rule_path=path,
                    brain_rules=bound, evidence=evidence,
                    reason="The concrete source token is absent or changed in the canonical Brain value.")
        elif expected_values and not any(_contains_value(rule, expected_values, path=path) for rule in bound):
            _append(findings, campaign=campaign, code="LOST_VALUE", severity=severity, category="lost_value",
                    message=f"Brain value does not preserve a concrete source value for {path}.", rule_path=path,
                    brain_rules=bound, evidence=evidence,
                    reason="A concrete source value was verified but could not be found in the canonical Brain rule.")

    groups: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        groups[(_path_key(rule.get("source_rule_path")), _value_key(rule.get("value")), _scope(rule))].append(rule)
    for (path, _value, _rule_scope), group in sorted(groups.items()):
        if len(group) > 1 and not _has_conflict_marker(brain, path):
            _append(findings, campaign=campaign, code="DUPLICATE_RULE", severity="WARNING", category="duplicate_rule",
                    message=f"Semantically duplicated Brain rules exist for {path}.", rule_path=path,
                    brain_rules=group, evidence=[by_id[eid] for rule in group for eid in rule.get("evidence_ids") or [] if eid in by_id],
                    reason="Rules have the same semantic path, value, and platform scope without a legitimate variant marker.")

    contradiction_groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        if _lower(rule.get("requirement_level")) == "mandatory":
            contradiction_groups[(_path_key(rule.get("source_rule_path")), _scope(rule))].append(rule)
    for (path, rule_scope), group in sorted(contradiction_groups.items()):
        values = {_value_key(rule.get("value")) for rule in group}
        if len(values) > 1 and not _has_conflict_marker(brain, path):
            _append(findings, campaign=campaign, code="CONTRADICTORY_RULE", severity="CRITICAL", category="contradiction",
                    message=f"Mandatory Brain rules contradict each other for {path}.", rule_path=path,
                    brain_rules=group, evidence=[by_id[eid] for rule in group for eid in rule.get("evidence_ids") or [] if eid in by_id],
                    reason="Multiple mandatory values apply to the same semantic rule and scope without an explicit conflict or variant marker.")

    for rule in rules:
        interpretation = _lower(rule.get("interpretation_type"))
        evidence_ids = [str(item) for item in rule.get("evidence_ids") or []]
        evidence = [by_id[item] for item in evidence_ids if item in by_id]
        if interpretation == "inferred" and not evidence_ids:
            _append(findings, campaign=campaign, code="UNSUPPORTED_INFERENCE", severity="CRITICAL" if _lower(rule.get("requirement_level")) == "mandatory" else "WARNING", category="unsupported_inference",
                    message="Brain marks a rule as inferred without source evidence.", rule_path=str(rule.get("source_rule_path") or ""),
                    brain_rules=[rule], evidence=evidence, reason="An inferred rule requires evidence before it can be trusted.")
        elif interpretation == "inferred" and _lower(rule.get("requirement_level")) == "mandatory":
            _append(findings, campaign=campaign, code="UNSUPPORTED_MANDATORY_INFERENCE", severity="CRITICAL", category="unsupported_inference",
                    message="Brain promotes an inferred rule to mandatory.", rule_path=str(rule.get("source_rule_path") or ""),
                    brain_rules=[rule], evidence=evidence, reason="Mandatory status requires explicit source support, not inference alone.")

    findings.sort(key=lambda item: (SEVERITIES.index(item["severity"]), item["code"], item["rule_path"], item["finding_id"]))
    counts = {severity: sum(1 for item in findings if item["severity"] == severity) for severity in SEVERITIES}
    status = "blocked" if counts["CRITICAL"] else "review" if counts["WARNING"] or counts["AMBIGUITY"] else "pass"
    stable = {"schema_version": SCHEMA_VERSION, "campaign_id": str(campaign.get("id") or ""), "source_hash": source_fingerprint(campaign), "brain_id": brain.get("brain_id"), "findings": findings}
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        **stable,
        "critic_id": "critic-v1:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "status": status,
        "summary": {"finding_count": len(findings), "by_severity": counts},
    }


__all__ = ["SCHEMA_VERSION", "SEVERITIES", "critique_campaign"]
