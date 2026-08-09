#!/usr/bin/env python3
"""Run E2E-08 Self-mod patch accept + deny journey (Virtual User harness).

Gate-tagged; also invoked from test:ci. Stdlib only.

  python3 scripts/run_e2e_08.py
  make e2e-08
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness.virtual_user import run_e2e_08  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv  # no flags yet
    result = run_e2e_08(root=ROOT, write_artifacts=True)
    summary = {
        "flow": "E2E-08",
        "result": result.result,
        "accept_approval_id": result.accept_approval_id,
        "deny_approval_id": result.deny_approval_id,
        "apply_count_after_accept": result.apply_count_after_accept,
        "apply_count_after_deny": result.apply_count_after_deny,
        "rollback_ref": result.rollback_ref,
        "commit_sha": result.commit_sha,
        "branch": result.branch,
        "tree_clean_after_propose": result.tree_clean_after_propose,
        "tree_clean_after_deny": result.tree_clean_after_deny,
        "artifacts": result.artifacts_dir,
        "checks": [
            {"id": c["id"], "result": c["result"]} for c in result.checks
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        f"\n==> E2E-08 {result.result} "
        f"(artifacts: {result.artifacts_dir}/report.json)"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
