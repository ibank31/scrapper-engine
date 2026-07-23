#!/usr/bin/env python3
"""Scrapper Engine - satu pintu semua modul.

Usage:
  python run.py reward_campaign [--blob F | --local F]
  python run.py reward_detail <campaign_id_atau_url> [--no-translate --no-download]
  python run.py product_image --manifest manifests/xxx.json --repo ~/situs
"""
import os, runpy, sys

BASE = os.path.dirname(os.path.abspath(__file__))
MODULES = {
    "reward_campaign": "modules/reward_campaign/scrape.py",
    "reward_detail": "modules/reward_campaign/pull_detail.py",
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
