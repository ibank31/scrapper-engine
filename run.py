#!/usr/bin/env python3
"""Scrapper Engine - satu pintu semua modul.

Usage:
  python run.py reward_campaign [--blob F | --local F]
  python run.py reward_detail <campaign_id_atau_url> [--no-translate --no-download]
  python run.py reward_plan <detail.json|flight.html> [--local]
  python run.py reward_intake <plan.json> [--workspace data/jobs]
  python run.py transcribe <video> [--model small]
  python run.py select_clips <transcript.json>
  python run.py render_clips <video> <candidates.json> [--transcript transcript.json]
  python run.py validate_clips --plan plan.json --glob 'renders/*.mp4'
  python run.py review_queue --plan plan.json --candidates candidates.json --validation validation.json --rendered-dir renders --out-dir review
  python run.py product_image --manifest manifests/xxx.json --repo ~/situs
"""
import os, runpy, sys

BASE = os.path.dirname(os.path.abspath(__file__))
MODULES = {
    "reward_campaign": "modules/reward_campaign/scrape.py",
    "reward_detail": "modules/reward_campaign/pull_detail.py",
    "reward_plan": "modules/reward_campaign/build_plan.py",
    "reward_intake": "modules/reward_campaign/intake.py",
    "transcribe": "modules/clipping/transcribe.py",
    "select_clips": "modules/clipping/select.py",
    "render_clips": "modules/clipping/render.py",
    "validate_clips": "modules/clipping/validate.py",
    "review_queue": "modules/clipping/review_queue.py",
    "product_image": "modules/product_image/run.py",
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODULES:
        print(__doc__.strip())
        print("\nModul tersedia: " + ", ".join(sorted(MODULES)))
        raise SystemExit(1)
    script = os.path.join(BASE, MODULES[sys.argv[1]])
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name="__main__")

if __name__ == "__main__":
    main()
