#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.staging_matrix import run_failure_matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="staging-failure-matrix.json")
    parser.add_argument("--enable-provider-mutation", action="store_true")
    args = parser.parse_args()
    result = run_failure_matrix(provider_mutation_enabled=args.enable_provider_mutation)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
