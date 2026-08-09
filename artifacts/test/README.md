# Test artifacts

Machine-readable outputs from harness and CI runs. Convention:

```text
artifacts/test/<task-or-flow>/
  report.json
  report.md
  verification.json      # optional autonomous stamp
  trace.jsonl
  outbound-messages.json
  ui/          # optional Android approval snapshots
  diffs/       # self-mod proposals
```

## CI layout (merge gate `test:ci`)

```text
artifacts/test/ci/
  report.json            # aggregate PASS/FAIL + agent_b_rerun hints
  report.md
  verification.json      # gate_e2e, invariants, gate_deny_paths, gate_map
  unit/report.json
  contract/report.json
  contract/outbound-messages.json
  integration/report.json
  integration/outbound-messages.json
  e2e/report.json        # gate-tagged E2E-01..10 layer

artifacts/test/e2e-01/ … e2e-10/
  report.json
  verification.json      # gate: true on merge-gate flows
  … flow-specific snapshots
```

Gate inventory and component-matrix mapping: [`docs/ci-gates.md`](../../docs/ci-gates.md).

Contents are gitignored except this README and `.gitkeep`. See [`agent-plan/testing/harnesses-and-fixtures.md`](../../agent-plan/testing/harnesses-and-fixtures.md).

### Agent B re-run

```bash
make test-ci && make test-ci-fail-closed
# Audit: artifacts/test/ci/verification.json + docs/ci-gates.md
```
