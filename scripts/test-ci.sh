#!/usr/bin/env bash
# test:ci — merge gate entrypoint (unit + contract/INV-* + integration + gate e2e).
# Fail-closed: invariant failures exit non-zero.
#
# Happy path:     ./scripts/test-ci.sh
# Fail-closed:    ./scripts/test-ci.sh --break-invariant   # expect exit != 0
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BREAK=0
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --break-invariant)
      BREAK=1
      EXTRA+=(--break-invariant)
      ;;
    *)
      EXTRA+=("$arg")
      ;;
  esac
done

echo "==> personal-agent test:ci"
echo "    repo: $ROOT"
if [[ "$BREAK" -eq 1 ]]; then
  echo "    mode: BREAK INVARIANT (expect FAIL / non-zero exit)"
else
  echo "    mode: happy path (expect PASS)"
fi
echo ""

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

echo "==> layers: unit → contract/INV-* → integration → e2e (E2E-01 + E2E-03 + E2E-04 + E2E-05 gates)"
# Capture exit under set -e so we still print FAIL + artifact paths.
set +e
python3 "$ROOT/scripts/run_test_ci.py" "${EXTRA[@]}"
status=$?
set -e

echo ""
if [[ "$status" -eq 0 ]]; then
  echo "==> test:ci PASS"
else
  echo "==> test:ci FAIL (fail-closed)"
fi
echo "    artifacts: artifacts/test/ci/report.json"
echo "    e2e-01:    artifacts/test/e2e-01/report.json"
echo "    e2e-03:    artifacts/test/e2e-03/report.json"
echo "    e2e-04:    artifacts/test/e2e-04/report.json"
echo "    e2e-05:    artifacts/test/e2e-05/report.json"
echo "    Agent B re-run: see artifacts/test/ci/report.json → agent_b_rerun"
exit "$status"
