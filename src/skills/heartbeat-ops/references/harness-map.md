# Harness map — heartbeat-ops

| Tool | Implementation |
| --- | --- |
| `heartbeat_morning_brief` | `operations.heartbeat.HeartbeatService.maybe_morning_brief` |
| `heartbeat_weekly_review` | `operations.heartbeat.HeartbeatService.maybe_weekly_review` |

Dependencies:

- `policy.quiet_hours.blocks_proactive`
- `policy.kill_switches.KillSwitches.is_paused`
- `harness.adapters.StubCronEmitter.emit_proactive`
- `intelligence.memory.store.MemoryStore` for name + quiet hours

TASK-25 artifacts: `artifacts/test/task-25/`, E2E-10 restart durability.
