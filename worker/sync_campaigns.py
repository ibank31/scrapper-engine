#!/usr/bin/env python3
"""Fetch public Content Rewards campaigns and sync normalized rows to D1."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    api = os.environ["CLIPPER_API_URL"].rstrip("/")
    token = os.environ["CLIPPER_WORKER_TOKEN"]
    subprocess.run([sys.executable, "run.py", "reward_campaign"], cwd=ROOT, check=True)
    data = json.loads((ROOT / "data/reward_campaign/campaigns.json").read_text(encoding="utf-8"))
    response = requests.post(api + "/api/campaigns/sync", headers={"content-type": "application/json", "x-worker-token": token}, json={"campaigns": data.get("campaigns", [])}, timeout=120)
    response.raise_for_status()
    print("Synced campaigns:", response.json())

if __name__ == "__main__":
    main()
