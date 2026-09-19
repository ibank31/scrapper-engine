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

import requests

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


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
            run([sys.executable, "run.py", "reward_detail", job["campaign_id"], "--no-translate", "--no-download"])
            details = list(Path(detail_root).rglob("detail.json"))
            if not details: raise RuntimeError("detail campaign tidak ditemukan")
            run([sys.executable, "run.py", "reward_plan", str(details[0])])
            plan_path = details[0].with_name("detail.plan.json")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        else:
            plan_path = Path(root) / "plan.json"
        plan_path = os.path.join(root, "plan.json")
        with open(plan_path, "w", encoding="utf-8") as fh: json.dump(plan, fh, ensure_ascii=False, indent=2)
        update(args.api_base, args.job_id, args.worker_token, "processing", 8, "Membaca rules campaign")
        workspace_root = os.path.join(root, "jobs")
        run([sys.executable, "run.py", "reward_intake", plan_path, "--workspace", workspace_root])
        workspace = next(Path(workspace_root).glob("*/"), None)
        if not workspace: raise RuntimeError("workspace asset tidak terbentuk")
        sources = [p for p in (workspace / "assets").rglob("*") if p.suffix.lower() in VIDEO_EXTENSIONS]
        if not sources: raise RuntimeError("tidak ada video asset langsung; periksa MANUAL_ASSETS.md")
        source = sources[0]
        update(args.api_base, args.job_id, args.worker_token, "processing", 24, "Bahan resmi sudah diambil")
        transcript_dir = workspace / "transcript"
        run([sys.executable, "run.py", "transcribe", str(source), "--out-dir", str(transcript_dir), "--model", args.whisper_model])
        update(args.api_base, args.job_id, args.worker_token, "processing", 52, "Transkripsi AI selesai, memilih highlight")
        run([sys.executable, "run.py", "select_clips", str(transcript_dir / "transcript.json"), "--limit", "10"])
        render_dir = workspace / "outputs"
        run([sys.executable, "run.py", "render_clips", str(source), str(transcript_dir / "candidates.json"), "--transcript", str(transcript_dir / "transcript.json"), "--plan", plan_path, "--out-dir", str(render_dir)])
        update(args.api_base, args.job_id, args.worker_token, "processing", 78, "Video vertical selesai, menjalankan validasi")
        validation_path = workspace / "validation.json"
        run([sys.executable, "run.py", "validate_clips", "--plan", plan_path, "--glob", str(render_dir / "*.mp4"), "--out", str(validation_path)])
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
