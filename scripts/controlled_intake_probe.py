#!/usr/bin/env python3
"""Read-only controlled intake/transcription probe.

This intentionally performs full intake discovery/download, then transcribes only
an explicit sample. It never calls the Cloudflare job mutation endpoints.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--sample-size", type=int, default=3)
    ap.add_argument("--model", default="small")
    args = ap.parse_args()

    workspace_root = Path(args.workspace)
    intake = run([sys.executable, "run.py", "reward_intake", args.plan, "--workspace", str(workspace_root)])
    print(intake.stdout, end="")
    print(intake.stderr, end="", file=sys.stderr)
    workspaces = sorted(workspace_root.glob("*/"))
    if not workspaces:
        raise SystemExit("intake did not create a workspace")
    workspace = workspaces[-1]
    manifest = json.loads((workspace / "assets.json").read_text(encoding="utf-8"))
    source_manifest = manifest.get("asset_manifest") or manifest.get("source_manifest") or []
    asset_files = sorted(p for p in (workspace / "assets").rglob("*") if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".part") and p.suffix.lower() in VIDEO_EXTENSIONS)
    partial_files = sorted(p for p in (workspace / "assets").rglob("*.part") if p.is_file())

    # Fixed, explicit sample after full discovery/download. This is not an intake cap.
    sample = asset_files[: max(0, args.sample_size)]
    sample_paths = {str(p.resolve()) for p in sample}
    results: list[dict] = []
    for path in sample:
        source_id = path.stem
        transcript_dir = path.parent / "controlled-transcripts" / path.stem
        command = [sys.executable, "run.py", "transcribe", str(path), "--model", args.model, "--beam-size", "3", "--out-dir", str(transcript_dir)]
        completed = run(command)
        transcript_path = transcript_dir / "transcript.json"
        segments = []
        error = None
        if transcript_path.exists():
            try:
                segments = json.loads(transcript_path.read_text(encoding="utf-8")).get("segments") or []
            except json.JSONDecodeError as exc:
                error = f"invalid_transcript_json: {exc}"
        if completed.returncode != 0 and not error:
            error = (completed.stderr or completed.stdout or f"transcribe_exit_{completed.returncode}")[-1000:]
        candidate_count = 0
        candidate_path = transcript_dir / "candidates.json"
        if transcript_path.exists():
            candidate_run = run([sys.executable, "run.py", "select_clips", str(transcript_path), "--plan", args.plan, "--min-seconds", "10", "--max-seconds", "60", "--limit", "10", "--source", str(path), "--out", str(candidate_path)])
            if candidate_path.exists():
                try:
                    candidate_count = len(json.loads(candidate_path.read_text(encoding="utf-8")).get("candidates") or [])
                except json.JSONDecodeError:
                    pass
            if candidate_run.returncode != 0 and not error:
                error = (candidate_run.stderr or candidate_run.stdout or f"candidate_exit_{candidate_run.returncode}")[-1000:]
        results.append({
            "source_id": source_id,
            "local_path": str(path.relative_to(workspace)),
            "segments": len(segments),
            "candidate_count": candidate_count,
            "status": "analyzed" if not error else "failed",
            "error": error,
        })

    for entry in source_manifest:
        local_paths = {str((workspace / p).resolve()) for p in entry.get("local_paths") or []}
        entry["deep_analysis"] = "sampled" if local_paths & sample_paths else "not_sampled"
        matching = [r for r in results if r["local_path"] == entry.get("local_path") or r["local_path"] in entry.get("local_paths", [])]
        if matching:
            entry["segments"] = matching[0]["segments"]
            entry["candidate_count"] = matching[0]["candidate_count"]
            entry["analysis_status"] = matching[0]["status"]
            if matching[0]["error"]:
                entry["analysis_error"] = matching[0]["error"]

    discovered = len(source_manifest)
    accessible = sum(1 for e in source_manifest if e.get("accessible"))
    downloaded = sum(1 for e in source_manifest if e.get("downloaded"))
    failed = sum(1 for e in source_manifest if e.get("status") in {"INACCESSIBLE", "DOWNLOAD_FAILED", "inaccessible", "failed"})
    deferred = sum(1 for e in source_manifest if str(e.get("status", "")).startswith("DEFERRED"))
    skipped = sum(1 for e in source_manifest if str(e.get("status", "")).startswith("SKIPPED"))
    type_errors = Counter(e.get("source_type") for e in source_manifest if e.get("status") in {"INACCESSIBLE", "DOWNLOAD_FAILED", "inaccessible", "failed"})
    transcribed = len(results)
    segments_positive = sum(1 for r in results if r["segments"] > 0)
    segments_zero = sum(1 for r in results if r["segments"] == 0)
    raw_candidates = sum(r["candidate_count"] for r in results)
    discovery = manifest.get("discovery") or {}
    report = {
        "commit": os.environ.get("GITHUB_SHA"),
        "campaign_id": os.environ.get("CAMPAIGN_ID"),
        "intake_returncode": intake.returncode,
        "sampling": {"sample_size": len(sample), "policy": "first N deterministic sorted downloaded video files after full intake"},
        "metrics": {
            "total_discovered": discovered,
            "total_accessible": accessible,
            "total_downloaded": downloaded,
            "total_failed": failed,
            "total_deferred": deferred,
            "total_skipped": skipped,
            "errors_by_source_type": dict(type_errors),
            "sources_entered_transcription": transcribed,
            "sources_segments_gt_0": segments_positive,
            "sources_segments_eq_0": segments_zero,
            "raw_candidates": raw_candidates,
            "manifest_discovered_asset_count": int(discovery.get("discovered_asset_count") or 0),
            "manifest_discovered_media_asset_count": int(discovery.get("discovered_media_asset_count") or 0),
            "manifest_downloaded_bytes": int(discovery.get("downloaded_bytes") or 0),
            "partial_files_remaining": len(partial_files),
            "download_limit": (discovery.get("download_limits") or {}).get("max_assets"),
            "download_byte_budget": (discovery.get("download_limits") or {}).get("max_bytes"),
        },
        "candidate_sources": [r for r in results if r["candidate_count"] > 0],
        "integrity": {"no_partial_files": not partial_files, "manifest_has_asset_rows": bool(source_manifest), "discovery_metrics": discovery},
        "source_results": results,
        "source_manifest": source_manifest,
    }
    out = Path(os.environ.get("PROBE_OUT", workspace / "controlled-e2e-report.json"))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = out.with_suffix(".md")
    lines = ["# Controlled intake E2E report", "", f"Commit: `{report['commit']}`", f"Campaign: `{report['campaign_id']}`", "", "## Required metrics", "", "| Metric | Value |", "|---|---:|"]
    for key, value in report["metrics"].items():
        lines.append(f"| {key} | `{json.dumps(value, ensure_ascii=False)}` |")
    lines += ["", "## Source-level results", "", "| Source | Segments | Candidates | Status | Error |", "|---|---:|---:|---|---|"]
    for row in results:
        lines.append(f"| `{row['source_id']}` | {row['segments']} | {row['candidate_count']} | {row['status']} | {str(row['error'] or '').replace('|', '/')[:240]} |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
