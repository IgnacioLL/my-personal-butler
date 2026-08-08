#!/usr/bin/env python3
"""Soak / chaos pack (nightly-oriented; optional standalone runner).

Exercises restart mid-approval, clock jumps, and duplicate webhook delivery.
Integration layer runs the same checks in test:ci; this script is for
nightly/manual reruns without the full CI stack.

  python3 scripts/run_soak_chaos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_test_ci import _run_task25_soak_chaos_checks  # noqa: E402


def main() -> int:
    checks = _run_task25_soak_chaos_checks(ROOT)
    overall = "PASS" if all(c["result"] == "PASS" for c in checks) else "FAIL"
    out = ROOT / "artifacts" / "test" / "task-25" / "soak-chaos.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"result": overall, "checks": checks}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"result": overall, "checks": checks}, indent=2, sort_keys=True))
    print(f"\n==> soak/chaos {overall} (artifact: {out})")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
