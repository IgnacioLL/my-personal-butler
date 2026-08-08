#!/usr/bin/env python3
"""Run E2E-04 Calendar soft confirm journey (Virtual User harness).

Gate-tagged; also invoked from test:ci. Stdlib only.

  python3 scripts/run_e2e_04.py
  make e2e-04
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness.virtual_user import run_e2e_04  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv  # no flags yet
    result = run_e2e_04(root=ROOT, write_artifacts=True)
    summary = {
        "flow": "E2E-04",
        "result": result.result,
        "accept_approval_id": result.accept_approval_id,
        "deny_approval_id": result.deny_approval_id,
        "calendar_create_after_accept": result.calendar_create_after_accept,
        "calendar_create_after_deny": result.calendar_create_after_deny,
        "artifacts": result.artifacts_dir,
        "checks": [
            {"id": c["id"], "result": c["result"]} for c in result.checks
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        f"\n==> E2E-04 {result.result} "
        f"(artifacts: {result.artifacts_dir}/report.json)"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
