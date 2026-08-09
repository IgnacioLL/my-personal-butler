# Cron jobs — heartbeat-ops

## Production schedule (operator-tunable)

| Job | Suggested schedule | Timezone source |
| --- | --- | --- |
| `morning_brief` | 07:30 daily | `identity.timezone` in memory profile |
| `weekly_review` | 19:00 Sunday | same |

Use the profile timezone when Gateway supports per-job TZ; otherwise set `cron.jobs[].timezone` explicitly.

## Harness verification

`integration.heartbeat.morning_brief_emits` — brief fires when policy allows.

`integration.heartbeat.quiet_hours_suppress` — night window blocks outbound.

`integration.heartbeat.pause_agent_suppress` — pause blocks proactive jobs.

`integration.heartbeat.weekly_review_stub` — weekly job emits when allowed.

Soak: `scripts/run_soak_chaos.py` — pause/quiet paths under chaos pack.

## Reboot durability

Pending approvals and memory survive Gateway restart (TASK-05 / E2E-10). Heartbeat jobs resume after reboot when `cron.heartbeat_enabled` is true.
