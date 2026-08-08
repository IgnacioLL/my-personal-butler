#!/usr/bin/env python3
"""Run E2E-05 Diet plan → groceries journey (Virtual User harness).

Gate-tagged; also invoked from test:ci. Stdlib only.

  python3 scripts/run_e2e_05.py
  make e2e-05
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness.virtual_user import run_e2e_05  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv  # no flags yet
    result = run_e2e_05(root=ROOT, write_artifacts=True)
    summary = {
        "flow": "E2E-05",
        "result": result.result,
        "plan_date": result.plan_date,
        "grocery_todo_count": result.grocery_todo_count,
        "eval_score": result.eval_score,
        "artifacts": result.artifacts_dir,
        "checks": [
            {"id": c["id"], "result": c["result"]} for c in result.checks
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        f"\n==> E2E-05 {result.result} "
        f"(artifacts: {result.artifacts_dir}/report.json)"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
