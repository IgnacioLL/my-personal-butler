#!/usr/bin/env bash
# test:ci — CI entrypoint (T0 stub; TASK-01 fleshes out layers + INV-* runner).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> personal-agent test:ci (T0 stub)"
echo "    repo: $ROOT"
echo ""

# Layer placeholders — TASK-01 will invoke real runners here.
layers=(unit contract integration invariants)
for layer in "${layers[@]}"; do
  echo "  [skip] $layer — not wired yet (TASK-01)"
done

echo ""
echo "==> test:ci stub complete (exit 0)"
echo "    Next: TASK-01 wires fake clock, artifact dirs, outbound catcher, INV-* fail-closed runner."
exit 0
