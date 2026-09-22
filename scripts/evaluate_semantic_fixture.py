#!/usr/bin/env python3
"""Evaluate the local semantic ranker against the checked-in golden corpus."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.semantic_ranker import rank_candidates_with_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate semantic ranker against a golden fixture")
    parser.add_argument("--fixture", default=str(ROOT / "tests/fixtures/semantic_cases.json"))
    parser.add_argument("--out", default="semantic-evaluation.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        ranked, runtime = rank_candidates_with_metadata([case["candidate"]], case["plan"])
        semantic = ranked[0]["semantic"]
        expected_risk = case.get("expected_risk")
        rows.append({
            "id": case["id"],
            "expected_decision": case["expected_decision"],
            "actual_decision": semantic.get("decision"),
            "decision_match": semantic.get("decision") == case["expected_decision"],
            "expected_risk": expected_risk,
            "actual_risks": semantic.get("risks", []),
            "risk_match": not expected_risk or expected_risk in semantic.get("risks", []),
            "engine": runtime["engine"],
            "fallback_used": runtime["fallback_used"],
            "fallback_reason": runtime["fallback_reason"],
        })
    decision_matches = sum(row["decision_match"] for row in rows)
    risk_matches = sum(row["risk_match"] for row in rows)
    payload = {
        "schema_version": 1,
        "fixture": os.path.relpath(args.fixture, ROOT),
        "case_count": len(rows),
        "decision_matches": decision_matches,
        "risk_matches": risk_matches,
        "decision_accuracy": round(decision_matches / len(rows), 4) if rows else 0,
        "risk_coverage": round(risk_matches / len(rows), 4) if rows else 0,
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("case_count", "decision_matches", "risk_matches", "decision_accuracy", "risk_coverage")}, indent=2))
    if decision_matches != len(rows) or risk_matches != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
