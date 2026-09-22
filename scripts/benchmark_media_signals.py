#!/usr/bin/env python3
"""Benchmark optional media signals on a local synthetic long fixture."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.media_signals import candidate_signals, source_quality_preflight


def make_fixture(path: str) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "24", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-shortest", path,
    ], check=True)


def main() -> None:
    transcript = {"segments": [
        {"start": 0, "end": 8, "text": "Here is the opening context for this controlled media fixture."},
        {"start": 8, "end": 16, "text": "The answer is to measure runtime and preserve the original interval."},
        {"start": 16, "end": 24, "text": "That means the result remains reviewable and complete."},
    ]}
    candidate = {"start": 2.0, "end": 18.0, "duration": 16.0, "text": "Here is the opening context. The answer is to measure runtime and preserve the original interval."}
    with tempfile.TemporaryDirectory(prefix="clipper-media-fixture-") as folder:
        source = os.path.join(folder, "synthetic-long-source.mp4")
        make_fixture(source)
        preflight_started = time.perf_counter()
        preflight = source_quality_preflight(source, transcript)
        preflight_runtime_ms = round((time.perf_counter() - preflight_started) * 1000, 1)
        signal_started = time.perf_counter()
        signals = candidate_signals(source, candidate, transcript)
        signal_wall_runtime_ms = round((time.perf_counter() - signal_started) * 1000, 1)
    payload = {
        "schema_version": 1,
        "fixture": {"duration_seconds": 24, "resolution": "640x360", "has_synthetic_audio": True},
        "preflight_runtime_ms": preflight_runtime_ms,
        "signal_wall_runtime_ms": signal_wall_runtime_ms,
        "preflight": preflight,
        "signals": signals,
        "timestamp_invariant": {"start": candidate["start"], "end": candidate["end"], "duration": candidate["duration"]},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not preflight.get("available") or not preflight.get("has_video") or not preflight.get("has_audio"):
        raise SystemExit("synthetic fixture preflight failed")
    if signals.get("runtime_ms", 0) > (signals.get("budget_seconds", 8) * 1000 + 1500):
        raise SystemExit("media signal budget exceeded by an unexpected margin")


if __name__ == "__main__":
    main()
