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


def upload_r2(path: str, key: str, content_type: str, bucket: str):
    import boto3
    client = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"], aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    client.upload_file(path, bucket, key, ExtraArgs={"ContentType": content_type, "CacheControl": "public,max-age=3600"})
    return client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=86400)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one cloud clipping job")
    ap.add_argument("--api-base", default=os.environ.get("CLIPPER_API_URL"), required=False)
    ap.add_argument("--job-id", default=os.environ.get("JOB_ID"), required=False)
    ap.add_argument("--worker-token", default=os.environ.get("CLIPPER_WORKER_TOKEN"), required=False)
    ap.add_argument("--whisper-model", default=os.environ.get("CLIPPER_WHISPER_MODEL", "small"))
    args = ap.parse_args()
    if not args.api_base or not args.job_id or not args.worker_token:
        raise SystemExit("CLIPPER_API_URL, JOB_ID, dan CLIPPER_WORKER_TOKEN wajib tersedia")
    root = tempfile.mkdtemp(prefix="clipper-job-")
    try:
        job = api_call(args.api_base, f"/api/jobs/{args.job_id}", args.worker_token)["job"]
        plan = job.get("campaign_plan")
        if not plan:
            raise RuntimeError("campaign belum memiliki compiled campaign plan")
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
        review = json.load(open(review_dir / "review.json", encoding="utf-8")); bucket = os.environ["R2_BUCKET"]; previews = []
        for item in review.get("items", []):
            if item.get("status") == "blocked": continue
            video_path = review_dir / item["video"]; thumbnail_path = review_dir / item["thumbnail"] if item.get("thumbnail") else None
            prefix = f"jobs/{args.job_id}/clip-{int(item['rank']):03d}"
            video_url = upload_r2(str(video_path), prefix + ".mp4", "video/mp4", bucket)
            thumb_url = upload_r2(str(thumbnail_path), prefix + ".jpg", "image/jpeg", bucket) if thumbnail_path and thumbnail_path.exists() else None
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
