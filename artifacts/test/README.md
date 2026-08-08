# Test artifacts

Machine-readable outputs from harness and CI runs. Convention:

```text
artifacts/test/<task-or-flow>/
  report.json
  report.md
  trace.jsonl
  outbound-messages.json
  ui/          # optional Android approval snapshots
  diffs/       # self-mod proposals
```

Contents are gitignored except this README and `.gitkeep`. See [`agent-plan/testing/harnesses-and-fixtures.md`](../../agent-plan/testing/harnesses-and-fixtures.md).
