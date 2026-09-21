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
from pathlib import Path

# Repo root must be on sys.path so `from core...` works when the
# workflow invokes `python worker/run_job.py` (cwd is repo root,
# but the package root is not automatically on PYTHONPATH).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from core.relevance import check_candidate

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_REVIEW_CANDIDATES = 2


def api_call(base: str, path: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    response = requests.request(method, base.rstrip("/") + path, headers={"content-type": "application/json", "x-worker-token": token}, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def update(base: str, job_id: str, token: str, status: str, progress: int, message: str, error: str | None = None) -> None:
    api_call(base, f"/api/jobs/{job_id}", token, "PATCH", {"status": status, "progress": progress, "message": message, "error": error})


def run(command: list[str], cwd: str | None = None) -> None:
    subprocess.run(command, check=True, cwd=cwd, text=True)


def upload_r2(api_base: str, job_id: str, token: str, path: str, key: str, content_type: str):
    with open(path, "rb") as stream:
        response = requests.post(api_base.rstrip("/") + f"/api/jobs/{job_id}/upload", headers={"x-worker-token": token}, files={"file": (Path(path).name, stream, content_type)}, data={"key": key}, timeout=180)
    response.raise_for_status()
    return response.json()["download_url"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one cloud clipping job")
    ap.add_argument("--api-base", default=os.environ.get("CLIPPER_API_URL"), required=False)
    ap.add_argument("--job-id", default=os.environ.get("JOB_ID"), required=False)
    ap.add_argument("--worker-token", default=os.environ.get("CLIPPER_WORKER_TOKEN"), required=False)
    ap.add_argument("--whisper-model", default=os.environ.get("CLIPPER_WHISPER_MODEL", "small"))
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
    root = tempfile.mkdtemp(prefix="clipper-job-")
    try:
        job = api_call(args.api_base, f"/api/jobs/{args.job_id}", args.worker_token)["job"]
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
        ai_status = str(plan.get("ai_rules_status") or "")
        ai_conf = float(((plan.get("ai_rules") or {}).get("confidence") or 0) or 0)
        ai_ambiguities = (plan.get("ai_rules") or {}).get("ambiguities") or []
        if ai_status != "pass" or ai_conf < 0.70 or any("critical" in str(x).lower() for x in ai_ambiguities):
            update(
                args.api_base,
                args.job_id,
                args.worker_token,
                "blocked",
                100,
                "Rules campaign belum cukup dipahami AI untuk produksi otomatis",
                "ai_rules_status=%s confidence=%.2f critical_ambiguities=%d" % (
                    ai_status or "missing",
                    ai_conf,
                    sum(1 for x in ai_ambiguities if "critical" in str(x).lower()),
                ),
            )
            return
        update(args.api_base, args.job_id, args.worker_token, "processing", 8, "Membaca rules campaign")
        workspace_root = os.path.join(root, "jobs")
        run([sys.executable, "run.py", "reward_intake", plan_path, "--workspace", workspace_root])
        workspace = next(Path(workspace_root).glob("*/"), None)
        if not workspace: raise RuntimeError("workspace asset tidak terbentuk")
        sources = [p for p in (workspace / "assets").rglob("*") if p.suffix.lower() in VIDEO_EXTENSIONS]
        if not sources: raise RuntimeError("tidak ada video asset langsung; periksa MANUAL_ASSETS.md")
        update(args.api_base, args.job_id, args.worker_token, "processing", 24, f"{len(sources)} bahan resmi sudah diambil")
        transcript_root = workspace / "transcripts"
        render_dir = workspace / "outputs"
        transcript_root.mkdir(exist_ok=True)
        render_dir.mkdir(exist_ok=True)
        all_candidates = []
        for source_index, source in enumerate(sources, 1):
            transcript_dir = transcript_root / f"source-{source_index:02d}"
            run([sys.executable, "run.py", "transcribe", str(source), "--out-dir", str(transcript_dir), "--model", args.whisper_model])
            run([sys.executable, "run.py", "select_clips", str(transcript_dir / "transcript.json"), "--limit", "10"])
            local_candidates = json.loads((transcript_dir / "candidates.json").read_text(encoding="utf-8"))
            for local_item in local_candidates.get("candidates", []):
                relevance = check_candidate(plan, local_item)
                if relevance.get("status") == "blocked":
                    continue
                all_candidates.append({"candidate": dict(local_item), "source": str(source), "transcript": str(transcript_dir / "transcript.json"), "relevance": relevance})
            update(args.api_base, args.job_id, args.worker_token, "processing", min(75, 24 + int(48 * source_index / max(1, len(sources)))), f"Memproses bahan {source_index}/{len(sources)}")
        if not all_candidates:
            raise RuntimeError("tidak ada kandidat clip yang dapat dirender dari bahan campaign")
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
        run([sys.executable, "run.py", "validate_clips", "--plan", plan_path, "--candidates", str(transcript_dir / "candidates.json"), "--glob", str(render_dir / "*.mp4"), "--out", str(validation_path)])
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        results = validation.get("results") or []
        if results and all(item.get("status") == "fail" for item in results) and any((item.get("relevance") or {}).get("status") == "blocked" for item in results):
            update(args.api_base, args.job_id, args.worker_token, "blocked", 100, "Semua kandidat diblokir karena tidak relevan dengan campaign")
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
            previews.append({"id": f"{args.job_id}-{item['rank']}", "rank": item["rank"], "status": "pending_review", "video_key": prefix + ".mp4", "thumbnail_key": prefix + ".jpg" if thumb_url else None, "download_url": video_url, "validation": item.get("validation", {}), "caption_draft": item.get("caption_draft"), "checklist": item.get("checklist", [])})
        api_call(args.api_base, f"/api/jobs/{args.job_id}/previews", args.worker_token, "POST", {"previews": previews})
        update(args.api_base, args.job_id, args.worker_token, "review", 100, f"{len(previews)} preview siap direview")
    except Exception as exc:
        try: update(args.api_base, args.job_id, args.worker_token, "error", 0, "Pipeline gagal", str(exc))
        except Exception: pass
        raise
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__": main()
