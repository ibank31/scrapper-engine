#!/usr/bin/env python3
"""Deterministic CA-09 human review contract.

The review contract is a human-facing projection of CA-08 plus the current
rendered preview. It does not call an LLM, mutate upstream artifacts, or grant
a compliance override.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

SCHEMA_VERSION = 1
REVIEWABLE_PREVIEW_STATUSES = {"pending_review", "changes_requested"}
ALLOWED_GATE_STATUSES = {"ready", "review"}
GATE_BLOCKED_STATUS = "blocked"


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    return value


def _key(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_key(value).encode("utf-8")).hexdigest()


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _check(check_id: str, status: str, label: str, detail: str, *, action: str | None = None) -> dict[str, Any]:
    item = {
        "id": check_id,
        "status": status,
        "label": label,
        "detail": " ".join(str(detail or "").split()),
    }
    if action:
        item["action"] = action
    return item


def _issue_message(issue: Mapping[str, Any]) -> tuple[str, str, str]:
    code = _norm(issue.get("code"))
    mapping = {
        "upstream_review": (
            "Ada bagian aturan campaign yang perlu diperhatikan.",
            "Periksa detail aturan sebelum menyetujui video.",
            "Lihat detail aturan",
        ),
        "unresolved_issue": (
            "Ada bagian analisis campaign yang belum terselesaikan.",
            "Pastikan bagian ini tidak memengaruhi video sebelum menyetujui.",
            "Lihat detail pemeriksaan",
        ),
        "critical_unresolved": (
            "Ada masalah penting yang belum terselesaikan.",
            "Video tidak dapat dilanjutkan sampai masalah tersebut diperbaiki.",
            "Lihat masalah",
        ),
        "material_blocked": (
            "Material yang dibutuhkan belum siap.",
            "Selesaikan material campaign sebelum membuat atau menyetujui video.",
            "Lihat material",
        ),
        "selected_asset_not_ready": (
            "Bahan video yang dipilih belum siap digunakan.",
            "Perbaiki sumber bahan sebelum melanjutkan.",
            "Lihat material",
        ),
        "platform_scope_lost": (
            "Platform tujuan belum memenuhi aturan campaign.",
            "Periksa kembali platform yang dituju.",
            "Lihat platform",
        ),
        "provenance_invalid": (
            "Mesin tidak dapat memastikan asal aturan yang dipakai.",
            "Jangan setujui video sampai sumber aturan kembali terverifikasi.",
            "Lihat evidence",
        ),
        "posting_requirement_lost": (
            "Syarat publikasi wajib tidak terbawa ke hasil akhir.",
            "Jangan publikasikan sebelum syarat tersebut dipulihkan.",
            "Lihat aturan publikasi",
        ),
    }
    return mapping.get(
        code,
        (
            "Ada pemeriksaan campaign yang membutuhkan perhatian.",
            "Periksa detail pemeriksaan sebelum melanjutkan.",
            "Lihat detail pemeriksaan",
        ),
    )


def compile_review_contract(
    compliance_gate: Mapping[str, Any] | None,
    preview: Mapping[str, Any] | None,
    *,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic human-review projection without mutating inputs."""
    gate = deepcopy(compliance_gate) if isinstance(compliance_gate, Mapping) else {}
    item = deepcopy(preview) if isinstance(preview, Mapping) else {}

    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    expected_campaign = str(campaign_id or gate.get("campaign_id") or "")
    expected_source_hash = str(gate.get("source_hash") or "")
    gate_id = str(gate.get("compliance_gate_id") or "")
    gate_status = _norm(gate.get("status"))
    preview_status = _norm(item.get("status"))

    identity_ok = bool(
        gate.get("schema_version") == 1
        and gate_id
        and expected_campaign
        and str(gate.get("campaign_id") or "") == expected_campaign
        and expected_source_hash
    )
    if gate.get("schema_version") != 1:
        issues.append({"code": "gate_schema_invalid", "severity": "critical"})
    if not gate_id:
        issues.append({"code": "gate_missing", "severity": "critical"})
    if gate_status == GATE_BLOCKED_STATUS:
        issues.append({"code": "compliance_blocked", "severity": "critical"})
    elif gate_status not in ALLOWED_GATE_STATUSES:
        issues.append({"code": "gate_status_invalid", "severity": "critical"})

    if preview_status not in REVIEWABLE_PREVIEW_STATUSES:
        issues.append({"code": "preview_not_reviewable", "severity": "critical"})
    if not item.get("artifact_hash"):
        issues.append({"code": "artifact_hash_missing", "severity": "critical"})
    if not item.get("caption_revision_id"):
        issues.append({"code": "caption_revision_missing", "severity": "critical"})

    validation = item.get("validation") if isinstance(item.get("validation"), Mapping) else {}
    distinctness = item.get("distinctness") if isinstance(item.get("distinctness"), Mapping) else {}
    subtitle = item.get("subtitle_delivery") if isinstance(item.get("subtitle_delivery"), Mapping) else {}
    sound = item.get("sound_tags") if isinstance(item.get("sound_tags"), Mapping) else {}
    source_asset_id = _norm(item.get("source_asset_id"))
    source_hash = _norm(item.get("source_hash") or validation.get("source_hash"))
    source_identity_ok = bool(source_asset_id and source_asset_id != "unknown-source" and source_hash)
    checklist = item.get("checklist") if isinstance(item.get("checklist"), list) else []
    mandatory_review_items = [str(x).strip() for x in checklist if str(x).strip().lower().startswith("mandatory campaign requirement:")]

    checks.append(_check(
        "campaign_compliance",
        "pass" if gate_status == "ready" else "review" if gate_status == "review" else "blocked",
        "Aturan campaign",
        "Semua pemeriksaan wajib lolos." if gate_status == "ready" else (
            "Ada pemeriksaan campaign yang perlu perhatian." if gate_status == "review"
            else "Campaign memiliki masalah yang menghentikan proses."
        ),
        action="Lihat detail pemeriksaan" if gate_status == "review" else None,
    ))

    checks.append(_check(
        "video_identity",
        "pass" if item.get("candidate_id") and source_identity_ok else "review",
        "Identitas potongan",
        "Potongan dan bahan sumber teridentifikasi." if item.get("candidate_id") and source_identity_ok else "Identitas potongan atau asal bahan belum lengkap; jangan menyetujui sebelum lineage terverifikasi.",
    ))

    checks.append(_check(
        "artifact",
        "pass" if item.get("artifact_hash") else "blocked",
        "File video",
        "Versi video saat ini memiliki identitas file yang tetap." if item.get("artifact_hash") else "Versi video belum memiliki identitas file yang dapat diverifikasi.",
    ))

    checks.append(_check(
        "caption",
        "pass" if item.get("caption_draft") and item.get("caption_revision_id") else "blocked",
        "Caption",
        "Caption tersedia dan terikat ke revision yang dapat diaudit." if item.get("caption_draft") and item.get("caption_revision_id") else "Caption belum siap atau belum memiliki revision.",
        action="Edit caption" if item.get("caption_draft") else None,
    ))

    validation_status = _norm(validation.get("status"))
    checks.append(_check(
        "validation",
        "pass" if validation_status in {"pass", "passed", "ok"} else "review" if validation_status in {"needs_review", "review"} else "blocked" if validation_status in {"fail", "failed"} else "review",
        "Pemeriksaan video",
        "Pemeriksaan teknis dasar lolos." if validation_status in {"pass", "passed", "ok"} else (
            "Ada hasil teknis yang perlu Anda lihat." if validation_status in {"needs_review", "review"} else
            "Pemeriksaan teknis belum memberikan hasil yang aman." if validation_status not in {"fail", "failed"} else
            "Pemeriksaan teknis menemukan masalah."
        ),
        action="Lihat pemeriksaan video" if validation_status not in {"pass", "passed", "ok"} else None,
    ))

    distinct = distinctness.get("distinct")
    checks.append(_check(
        "distinctness",
        "pass" if distinct is True else "review",
        "Perbedaan dari kandidat lain",
        "Potongan ini dinyatakan berbeda dari kandidat lain." if distinct is True else "Perbedaan dengan kandidat lain belum dapat dipastikan secara penuh.",
        action="Bandingkan kandidat lain" if distinct is not True else None,
    ))

    subtitle_mode = _norm(subtitle.get("mode"))
    checks.append(_check(
        "subtitle",
        "pass" if subtitle_mode in {"burned_in", "native_caption_file", "none"} else "review",
        "Subtitle",
        "Status subtitle sudah diketahui." if subtitle_mode else "Status subtitle belum diketahui.",
        action="Periksa subtitle" if subtitle_mode not in {"burned_in", "native_caption_file", "none"} else None,
    ))

    sound_status = _norm(sound.get("status"))
    checks.append(_check(
        "audio",
        "pass" if sound_status == "verified" else "review",
        "Audio",
        "Audio sudah terverifikasi." if sound_status == "verified" else "Audio perlu diperiksa atau ditambahkan manual.",
        action="Periksa audio" if sound_status != "verified" else None,
    ))

    if mandatory_review_items:
        checks.append(_check(
            "mandatory_requirements",
            "review",
            "Syarat wajib campaign",
            "Ada syarat wajib campaign yang tercatat tetapi belum memiliki bukti pemenuhan pada output.",
            action="Lihat syarat wajib",
        ))

    for issue in gate.get("issues") or []:
        if not isinstance(issue, Mapping):
            continue
        issues.append(deepcopy(dict(issue)))
        if str(issue.get("severity") or "").lower() in {"warning", "critical"}:
            label, reason, action = _issue_message(issue)
            exceptions.append({
                "id": str(issue.get("issue_id") or issue.get("code") or "issue"),
                "severity": str(issue.get("severity") or "review").lower(),
                "label": label,
                "reason": reason,
                "action": action,
                "code": str(issue.get("code") or ""),
            })

    if not identity_ok:
        checks.insert(0, _check(
            "review_contract_identity",
            "blocked",
            "Kesiapan review",
            "Kontrak review tidak memiliki identitas campaign dan compliance gate yang lengkap.",
        ))

    # A blocked preview check is itself a hard stop. Do not let a malformed
    # or technically failed preview reach an approval action merely because
    # the upstream campaign gate was otherwise reviewable.
    for check in checks:
        if check.get("status") == "blocked":
            issues.append({
                "code": "review_check_blocked",
                "severity": "critical",
                "field": str(check.get("id") or ""),
                "message": str(check.get("detail") or "Review check is blocked."),
            })

    blocked = any(issue.get("severity") == "critical" for issue in issues)
    attention = any(check.get("status") == "review" for check in checks) or bool(exceptions)
    if blocked:
        decision_state = "blocked"
        summary_status = "tidak_dapat_dilanjutkan"
        summary_message = "Video belum dapat disetujui karena ada masalah yang harus diselesaikan lebih dulu."
    else:
        decision_state = "ready_for_review"
        summary_status = "perlu_perhatian" if attention else "siap_ditinjau"
        summary_message = (
            "Ada beberapa hal yang perlu Anda periksa sebelum menyetujui video."
            if attention else
            "Video siap diperiksa sebelum dipublikasikan."
        )

    result = {
        "schema_version": SCHEMA_VERSION,
        "review_contract_id": "",
        "campaign_id": expected_campaign,
        "source_hash": expected_source_hash,
        "compliance_gate_id": gate_id,
        "preview_id": str(item.get("id") or ""),
        "artifact_hash": str(item.get("artifact_hash") or ""),
        "caption_revision_id": str(item.get("caption_revision_id") or ""),
        "decision_state": decision_state,
        "summary": {
            "status": summary_status,
            "message": summary_message,
            "label": "Siap ditinjau" if summary_status == "siap_ditinjau" else "Perlu diperiksa" if summary_status == "perlu_perhatian" else "Tidak dapat dilanjutkan",
        },
        "checks": checks,
        "exceptions": sorted(exceptions, key=lambda x: (x.get("severity") != "critical", x.get("code", ""), x.get("id", ""))),
        "issues": sorted(issues, key=lambda x: (str(x.get("severity") or ""), str(x.get("code") or ""), str(x.get("field") or ""))),
        "submission_ready": (
            decision_state == "ready_for_review"
            and all(check.get("status") == "pass" for check in checks)
            and not exceptions
            and not issues
            and bool(item.get("artifact_hash"))
            and bool(item.get("caption_revision_id"))
        ),
        "review_actions": {
            "approve": (
                decision_state == "ready_for_review"
                and bool(item.get("artifact_hash"))
                and bool(item.get("caption_revision_id"))
                and all(check.get("status") == "pass" for check in checks)
                and not exceptions
                and not issues
            ),
            "reject": decision_state == "ready_for_review",
            "request_changes": decision_state == "ready_for_review",
        },
        "provenance": {
            "campaign_id": expected_campaign,
            "source_hash": expected_source_hash,
            "compliance_gate_id": gate_id,
            "preview_id": str(item.get("id") or ""),
            "artifact_hash": str(item.get("artifact_hash") or ""),
            "caption_revision_id": str(item.get("caption_revision_id") or ""),
        },
    }
    stable = {key: value for key, value in result.items() if key != "review_contract_id"}
    result["review_contract_id"] = _hash("review-contract-v1:", stable)
    return result


def review_contract_is_current(contract: Mapping[str, Any] | None, compliance_gate: Mapping[str, Any] | None, preview: Mapping[str, Any] | None) -> bool:
    if not isinstance(contract, Mapping) or not isinstance(compliance_gate, Mapping) or not isinstance(preview, Mapping):
        return False
    expected = compile_review_contract(compliance_gate, preview, campaign_id=str(compliance_gate.get("campaign_id") or ""))
    return contract == expected


__all__ = ["SCHEMA_VERSION", "compile_review_contract", "review_contract_is_current"]
