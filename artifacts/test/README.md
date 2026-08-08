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

## CI layout (TASK-01 / T0 + E2E-01 gate)

```text
artifacts/test/ci/
  report.json            # aggregate PASS/FAIL + agent_b_rerun hints
  report.md
  verification.json
  unit/report.json
  contract/report.json
  contract/outbound-messages.json
  integration/report.json
  integration/outbound-messages.json
  e2e/report.json        # gate-tagged E2E layer

artifacts/test/e2e-01/
  report.json
  report.md
  verification.json
  outbound-messages.json
  reminders.json
  trace.jsonl
```

Contents are gitignored except this README and `.gitkeep`. See [`agent-plan/testing/harnesses-and-fixtures.md`](../../agent-plan/testing/harnesses-and-fixtures.md).

### Agent B re-run

```bash
make test-ci && make test-ci-fail-closed
# Audit: artifacts/test/ci/report.json and artifacts/test/e2e-01/verification.json
```
