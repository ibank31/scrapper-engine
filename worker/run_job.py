#!/usr/bin/env python3
"""Run one clipping job on an ephemeral GitHub Actions runner."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

# Repo root must be on sys.path so `from core...` works when the
# workflow invokes `python worker/run_job.py` (cwd is repo root,
# but the package root is not automatically on PYTHONPATH).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from core.relevance import check_candidate
from core.media_signals import source_quality_preflight

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_REVIEW_CANDIDATES = 2


def api_call(base: str, path: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    response = requests.request(method, base.rstrip("/") + path, headers={"content-type": "application/json", "x-worker-token": token}, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def update(base: str, job_id: str, token: str, status: str, progress: int, message: str, error: str | None = None) -> None:
    api_call(base, f"/api/jobs/{job_id}", token, "PATCH", {"status": status, "progress": progress, "message": message, "error": error})


def claim_job(base: str, job_id: str, token: str, dispatch_token: str = "") -> bool:
    """Atomically claim a queued job; a lost race is a clean no-op."""
    claim_token = dispatch_token or uuid.uuid4().hex
    try:
        api_call(base, f"/api/jobs/{job_id}/claim", token, "POST", {"claim_token": claim_token})
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 409:
            return False
        raise
    return True


def run(command: list[str], cwd: str | None = None, check: bool = True) -> None:
    subprocess.run(command, check=check, cwd=cwd, text=True)


def source_priority(path: Path) -> tuple[float, int]:
    """Prefer usable high-resolution sources; size alone is a poor quality proxy."""
    try:
        probe = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
        ], text=True)
        data = json.loads(probe)
        video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
        duration = float((data.get("format") or {}).get("duration") or 0)
        area_score = min(4.0, (width * height) / 2_000_000)
        duration_score = min(1.0, duration / 90.0) if duration >= 20 else 0.0
        vertical_bonus = 0.35 if height >= width else 0.0
        return area_score + duration_score + vertical_bonus, -path.stat().st_size
    except Exception:
        return 0.0, -path.stat().st_size


def upload_r2(api_base: str, job_id: str, token: str, path: str, key: str, content_type: str):
    with open(path, "rb") as stream:
        response = requests.post(api_base.rstrip("/") + f"/api/jobs/{job_id}/upload", headers={"x-worker-token": token}, files={"file": (Path(path).name, stream, content_type)}, data={"key": key}, timeout=180)
    response.raise_for_status()
    return response.json()["download_url"]


def _candidate_audit_reason(stats: dict[str, int], source_count: int, usable_count: int) -> str:
    """Compact, auditable explanation for a zero-candidate block."""
    return (
        f"sources={source_count}; usable_sources={usable_count}; "
        f"transcribed={stats['transcribed']}; raw_candidates={stats['raw_candidates']}; "
        f"semantic_rejects={stats['semantic_rejects']}; "
        f"hard_policy_rejects={stats['hard_policy_rejects']}; "
        f"relevance_blocks={stats['relevance_blocks']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one cloud clipping job")
    ap.add_argument("--api-base", default=os.environ.get("CLIPPER_API_URL"), required=False)
    ap.add_argument("--job-id", default=os.environ.get("JOB_ID"), required=False)
    ap.add_argument("--worker-token", default=os.environ.get("CLIPPER_WORKER_TOKEN"), required=False)
    ap.add_argument("--dispatch-token", default=os.environ.get("CLIPPER_DISPATCH_TOKEN", ""), required=False)
    ap.add_argument("--whisper-model", default=os.environ.get("CLIPPER_WHISPER_MODEL", "small"))
    ap.add_argument("--whisper-beam", type=int, default=int(os.environ.get("CLIPPER_WHISPER_BEAM", "5")))
    ap.add_argument("--max-video-sources", type=int, default=int(os.environ.get("CLIPPER_MAX_VIDEO_SOURCES", "3")))
    args = ap.parse_args()
    if not args.api_base or not args.worker_token:
        raise SystemExit("CLIPPER_API_URL dan CLIPPER_WORKER_TOKEN wajib tersedia")
    if not args.job_id:
        queued = api_call(args.api_base, "/api/jobs", args.worker_token).get("jobs", [])
        candidate = next((job for job in queued if job.get("status") == "queued"), None)
        if not candidate:
            print("Tidak ada job queued; runner selesai tanpa proses.")
            return
        args.job_id = candidate["id"]
    if not claim_job(args.api_base, args.job_id, args.worker_token, args.dispatch_token):
        print(f"Job {args.job_id} sudah diklaim runner lain; runner selesai tanpa proses.")
        return
    root = tempfile.mkdtemp(prefix="clipper-job-")
    try:
        job = api_call(args.api_base, f"/api/jobs/{args.job_id}", args.worker_token)["job"]
        live_campaign = api_call(args.api_base, f"/api/campaigns/{job['campaign_id']}", args.worker_token).get("campaign") or {}
        live_campaign_status = str(live_campaign.get("status") or "active").lower()
        if live_campaign_status != "active":
            update(
                args.api_base,
                args.job_id,
                args.worker_token,
                "blocked",
                100,
                "Campaign tidak aktif; job dihentikan sebelum mengambil asset",
                f"campaign_status={live_campaign_status}",
            )
            return
        plan = job.get("campaign_plan")
        if not plan:
            detail_root = os.path.join(root, "campaign-detail")
            os.environ["CAMPAIGN_HOME"] = detail_root
            update(args.api_base, args.job_id, args.worker_token, "processing", 3, "Mengambil detail dan syarat campaign")
            run([sys.executable, "run.py", "reward_detail", job["campaign_id"], "--no-translate"])
            details = list(Path(detail_root).rglob("detail.json"))
            if not details: raise RuntimeError("detail campaign tidak ditemukan")
            run([sys.executable, "run.py", "reward_plan", str(details[0])])
            plan_path = details[0].with_name("detail.plan.json")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        else:
            plan_path = Path(root) / "plan.json"
        plan_path = os.path.join(root, "plan.json")
        with open(plan_path, "w", encoding="utf-8") as fh: json.dump(plan, fh, ensure_ascii=False, indent=2)

        # Hard-block only when AI has analyzed and rejected the rules.
        # "unavailable" / missing means campaign-sync-ai has not run yet —
        # allow the pipeline so trial via Pages still works; final review
        # remains human-gated.
        ai_status = str(plan.get("ai_rules_status") or "unavailable").lower()
        ai_conf = float(((plan.get("ai_rules") or {}).get("confidence") or 0) or 0)
        ai_ambiguities = (plan.get("ai_rules") or {}).get("ambiguities") or []
        critical = sum(1 for x in ai_ambiguities if "critical" in str(x).lower())
        if ai_status in {"fail", "rejected", "blocked"} or critical > 0:
            update(
                args.api_base,
                args.job_id,
                args.worker_token,
                "blocked",
                100,
                "Rules campaign ditolak AI — produksi otomatis dihentikan",
                "ai_rules_status=%s confidence=%.2f critical_ambiguities=%d" % (
                    ai_status,
                    ai_conf,
                    critical,
                ),
            )
            return
        if ai_status == "pass" and ai_conf < 0.70:
            update(
                args.api_base,
                args.job_id,
                args.worker_token,
                "blocked",
                100,
                "Confidence AI di bawah ambang 0.70 — produksi otomatis dihentikan",
                "ai_rules_status=%s confidence=%.2f" % (ai_status, ai_conf),
            )
            return

        production_rules = plan.get("production") or {}
        campaign_min_duration = float(production_rules.get("min_duration_seconds") or 0)
        campaign_max_duration = float(production_rules.get("max_duration_seconds") or 0)
        if campaign_min_duration and campaign_max_duration and campaign_min_duration > campaign_max_duration:
            update(args.api_base, args.job_id, args.worker_token, "blocked", 100, "Rules campaign tidak konsisten: minimum durasi melebihi maksimum", "min_duration_seconds > max_duration_seconds")
            return
        max_sources = max(1, int(args.max_video_sources))
        update(args.api_base, args.job_id, args.worker_token, "processing", 8, f"Membaca rules · max {max_sources} sumber video")
        workspace_root = os.path.join(root, "jobs")
        run([sys.executable, "run.py", "reward_intake", plan_path, "--workspace", workspace_root, "--max-video-sources", str(max_sources)])
        workspace = next(Path(workspace_root).glob("*/"), None)
        if not workspace: raise RuntimeError("workspace asset tidak terbentuk")
        sources = [p for p in (workspace / "assets").rglob("*") if p.suffix.lower() in VIDEO_EXTENSIONS]
        # Prefer the highest-quality usable sources, not the smallest files.
        sources.sort(key=source_priority, reverse=True)
        sources = sources[:max_sources]
        if not sources: raise RuntimeError("tidak ada video asset langsung; periksa MANUAL_ASSETS.md")
        preflight_records = []
        usable_sources = []
        seen_hashes: dict[str, str] = {}
        for source in sources:
            quality = source_quality_preflight(str(source))
            record = {"source": str(source), "quality": quality}
            source_hash = quality.get("duplicate_hash")
            if source_hash and source_hash in seen_hashes:
                record["duplicate_of"] = seen_hashes[source_hash]
                record["excluded_before_transcription"] = True
            elif source_hash:
                seen_hashes[source_hash] = str(source)
            preflight_records.append(record)
            if not record.get("duplicate_of") and quality.get("available") and quality.get("has_video") and quality.get("has_audio") and float(quality.get("duration_seconds") or 0) >= 1.5:
                usable_sources.append(source)
            elif not record.get("excluded_before_transcription"):
                record["excluded_before_transcription"] = True
        (workspace / "source-preflight.json").write_text(json.dumps({"schema_version": 1, "sources": preflight_records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sources = usable_sources
        if not sources:
            reasons = [
                ",".join(str(k) for k, v in (record.get("quality") or {}).items() if k in {"available", "has_video", "has_audio", "duration_seconds"})
                for record in preflight_records
                if record.get("excluded_before_transcription")
            ]
            raise RuntimeError(f"semua source gagal preflight: video/audio/durasi tidak layak; sources={len(preflight_records)}; details={' | '.join(reasons[:3])}")
        if campaign_min_duration:
            long_enough = [
                record for record in preflight_records
                if not record.get("excluded_before_transcription")
                and float((record.get("quality") or {}).get("duration_seconds") or 0) >= campaign_min_duration
            ]
            if not long_enough:
                update(
                    args.api_base,
                    args.job_id,
                    args.worker_token,
                    "blocked",
                    100,
                    f"Semua video lebih pendek dari minimum campaign {campaign_min_duration:.0f} detik",
                    f"sources={len(preflight_records)}; minimum_duration={campaign_min_duration:.3f}; transcription_skipped=true",
                )
                return
        update(args.api_base, args.job_id, args.worker_token, "processing", 24, f"{len(sources)} bahan resmi lolos preflight")
        transcript_root = workspace / "transcripts"
        render_dir = workspace / "outputs"
        transcript_root.mkdir(exist_ok=True)
        render_dir.mkdir(exist_ok=True)
        editorial_min_duration = campaign_min_duration or (8.0 if not campaign_max_duration or campaign_max_duration >= 8.0 else 3.0)
        editorial_max_duration = campaign_max_duration if campaign_max_duration > 0 else 60.0
        all_candidates = []
        candidate_stats = {"transcribed": 0, "raw_candidates": 0, "semantic_rejects": 0, "hard_policy_rejects": 0, "relevance_blocks": 0}
        for source_index, source in enumerate(sources, 1):
            transcript_dir = transcript_root / f"source-{source_index:02d}"
            run([
                sys.executable, "run.py", "transcribe", str(source),
                "--out-dir", str(transcript_dir),
                "--model", args.whisper_model,
                "--beam-size", str(max(1, int(args.whisper_beam))),
            ])
            candidate_stats["transcribed"] += 1
            transcript_payload = json.loads((transcript_dir / "transcript.json").read_text(encoding="utf-8"))
            transcript_duration = max((float(segment.get("end", 0)) for segment in transcript_payload.get("segments", [])), default=0.0)
            # Eight seconds is an editorial floor, not a campaign duration rule.
            # It prevents the old 3–5 second fallback from producing incomplete posts.
            if campaign_max_duration:
                adaptive_min = campaign_min_duration or max(1.0, campaign_max_duration * 0.60)
                adaptive_max = campaign_max_duration
            else:
                adaptive_min = max(editorial_min_duration, min(20.0, transcript_duration * 0.45))
                adaptive_max = min(editorial_max_duration, max(adaptive_min + 1.0, min(60.0, max(10.0, transcript_duration))))
            run([
                sys.executable, "run.py", "select_clips", str(transcript_dir / "transcript.json"),
                "--min-seconds", f"{adaptive_min:.3f}", "--max-seconds", f"{adaptive_max:.3f}", "--limit", "10",
                "--source", str(source),
            ])
            local_candidates = json.loads((transcript_dir / "candidates.json").read_text(encoding="utf-8"))
            selection = local_candidates.get("selection") or {}
            if local_candidates.get("candidates"):
                run([
                    sys.executable, "run.py", "semantic_rank", str(transcript_dir / "candidates.json"),
                    "--plan", plan_path,
                ])
                local_candidates = json.loads((transcript_dir / "candidates.json").read_text(encoding="utf-8"))
            else:
                local_candidates["semantic_runtime"] = {
                    "schema_version": 1,
                    "engine": "skipped",
                    "fallback_used": False,
                    "reason": selection.get("reason_if_empty") or "selector_returned_no_candidates",
                }
                (transcript_dir / "candidates.json").write_text(json.dumps(local_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
            # A source below the editorial floor is reported as unsuitable rather
            # than forced into a three-second preview.
            if not local_candidates.get("candidates") and transcript_duration >= adaptive_min and adaptive_max < 60:
                run([
                    sys.executable, "run.py", "select_clips", str(transcript_dir / "transcript.json"),
                    "--min-seconds", f"{adaptive_min:.3f}", "--max-seconds", "60", "--limit", "10",
                ])
                local_candidates = json.loads((transcript_dir / "candidates.json").read_text(encoding="utf-8"))
                if local_candidates.get("candidates"):
                    run([
                        sys.executable, "run.py", "semantic_rank", str(transcript_dir / "candidates.json"),
                        "--plan", plan_path,
                    ])
                    local_candidates = json.loads((transcript_dir / "candidates.json").read_text(encoding="utf-8"))
            for local_item in local_candidates.get("candidates", []):
                candidate_stats["raw_candidates"] += 1
                semantic = local_item.get("semantic") or {}
                if semantic.get("decision") == "reject":
                    candidate_stats["semantic_rejects"] += 1
                # Qwen is advisory. Only the deterministic local hard-policy
                # gate may discard a candidate before human review.
                if semantic.get("decision") == "reject" and semantic.get("hard_policy_gate") is True:
                    candidate_stats["hard_policy_rejects"] += 1
                    continue
                relevance = check_candidate(plan, local_item)
                if relevance.get("status") == "blocked":
                    candidate_stats["relevance_blocks"] += 1
                    continue
                all_candidates.append({"candidate": dict(local_item), "source": str(source), "transcript": str(transcript_dir / "transcript.json"), "relevance": relevance})
            update(args.api_base, args.job_id, args.worker_token, "processing", min(75, 24 + int(48 * source_index / max(1, len(sources)))), f"Memproses bahan {source_index}/{len(sources)}")
        if not all_candidates:
            update(
                args.api_base,
                args.job_id,
                args.worker_token,
                "blocked",
                100,
                "Tidak ada kandidat aman untuk review dari asset resmi campaign",
                _candidate_audit_reason(candidate_stats, len(preflight_records), len(sources)),
            )
            return
        all_candidates.sort(key=lambda item: (-float(item["candidate"].get("score", 0)), item["candidate"].get("start", 0)))
        selected = all_candidates[:MAX_REVIEW_CANDIDATES]
        final_candidates = []
        for global_rank, item in enumerate(selected, 1):
            local_item = item["candidate"]
            local_payload = {"schema_version": 1, "candidates": [dict(local_item, rank=1)]}
            candidate_path = Path(item["transcript"]).parent / f"final-candidate-{global_rank:03d}.json"
            candidate_path.write_text(json.dumps(local_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            local_render = Path(item["transcript"]).parent / f"final-render-{global_rank:03d}"
            run([sys.executable, "run.py", "render_clips", item["source"], str(candidate_path), "--transcript", item["transcript"], "--plan", plan_path, "--out-dir", str(local_render)])
            rendered = local_render / "clip-001.mp4"
            if rendered.exists():
                target = render_dir / f"clip-{global_rank:03d}.mp4"
                shutil.copy2(rendered, target)
                final_candidates.append(dict(local_item, rank=global_rank, source=item["source"], relevance=item["relevance"]))
        all_candidates = final_candidates
        if not all_candidates:
            raise RuntimeError("dua kandidat terbaik tidak berhasil dirender")
        transcript_dir = transcript_root
        (transcript_dir / "candidates.json").write_text(json.dumps({"schema_version": 1, "candidates": all_candidates}, ensure_ascii=False, indent=2), encoding="utf-8")
        update(args.api_base, args.job_id, args.worker_token, "processing", 78, "Video vertical selesai, menjalankan validasi")
        validation_path = workspace / "validation.json"
        # Validation is per-preview: keep usable outputs in the review queue even
        # when another candidate fails a technical gate.
        run([sys.executable, "run.py", "validate_clips", "--plan", plan_path, "--candidates", str(transcript_dir / "candidates.json"), "--glob", str(render_dir / "*.mp4"), "--out", str(validation_path)], check=False)
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        results = validation.get("results") or []
        if results and all(item.get("status") == "fail" for item in results):
            update(args.api_base, args.job_id, args.worker_token, "blocked", 100, "Semua kandidat gagal quality/compliance gate; source perlu momen yang lebih utuh")
            return
        review_dir = workspace / "review"
        run([sys.executable, "run.py", "review_queue", "--plan", plan_path, "--candidates", str(transcript_dir / "candidates.json"), "--validation", str(validation_path), "--rendered-dir", str(render_dir), "--out-dir", str(review_dir)])
        update(args.api_base, args.job_id, args.worker_token, "processing", 92, "Mengunggah preview ke R2")
        review = json.load(open(review_dir / "review.json", encoding="utf-8")); previews = []
        for item in review.get("items", []):
            if item.get("status") == "blocked": continue
            video_path = review_dir / item["video"]; thumbnail_path = review_dir / item["thumbnail"] if item.get("thumbnail") else None
            prefix = f"jobs/{args.job_id}/clip-{int(item['rank']):03d}"
            video_url = upload_r2(args.api_base, args.job_id, args.worker_token, str(video_path), prefix + ".mp4", "video/mp4")
            thumb_url = upload_r2(args.api_base, args.job_id, args.worker_token, str(thumbnail_path), prefix + ".jpg", "image/jpeg") if thumbnail_path and thumbnail_path.exists() else None
            validation_payload = dict(item.get("validation", {}))
            validation_payload["semantic"] = item.get("semantic") or {}
            previews.append({"id": f"{args.job_id}-{item['rank']}", "rank": item["rank"], "status": "pending_review", "video_key": prefix + ".mp4", "thumbnail_key": prefix + ".jpg" if thumb_url else None, "download_url": video_url, "validation": validation_payload, "caption_draft": item.get("caption_draft"), "checklist": item.get("checklist", [])})
        api_call(args.api_base, f"/api/jobs/{args.job_id}/previews", args.worker_token, "POST", {"previews": previews})
        update(args.api_base, args.job_id, args.worker_token, "review", 100, f"{len(previews)} preview siap direview")
    except Exception as exc:
        try: update(args.api_base, args.job_id, args.worker_token, "error", 0, "Pipeline gagal", str(exc))
        except Exception: pass
        raise
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__": main()
