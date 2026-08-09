---
name: heartbeat-ops
description: "Morning brief and weekly memory review cron jobs; respect pause_agent and quiet hours."
metadata: { "openclaw": { "requires": { "config": ["skills.entries.heartbeat-ops.enabled", "cron.heartbeat_enabled"] } } }
---

# Heartbeat — morning brief & weekly review

Proactive **always-on** jobs for day start and weekly memory hygiene. Maps to `operations/heartbeat.py` (`HeartbeatService`).

## When to use

- Cron triggers morning brief (default ~07:30 local).
- Sunday evening weekly review nudge.
- User asks for a day overview without a full planning session.

## Jobs

| Job id | Outbound kind | Harness method |
| --- | --- | --- |
| `morning_brief` | `morning_brief` | `HeartbeatService.maybe_morning_brief` |
| `weekly_review` | `weekly_review` | `HeartbeatService.maybe_weekly_review` |

## Guards (fail closed)

1. **pause_agent** kill switch → emit suppressed (`reason=pause_agent`)
2. **Quiet hours** from memory profile `preferences.quiet_hours` → suppressed (`quiet_hours`)
3. Cron emitter still records proactive attempt for audit

## Morning brief content

Compact WhatsApp message: greet by name from hot profile, nudge calendar/todos/approvals, offer deeper plan on reply.

## Weekly review content

Nudge to skim episodic notes, drop stale prefs, confirm quiet hours still match routine.

## OpenClaw cron (production)

Enable in `openclaw.json` (see `config/openclaw/skills-production.json5`):

```json5
{
  cron: {
    heartbeat_enabled: true,
    jobs: [
      { id: "morning_brief", schedule: "0 7 30 * * *", timezone: "Europe/Madrid" },
      { id: "weekly_review", schedule: "0 19 0 * * 0", timezone: "Europe/Madrid" },
    ],
  },
}
```

Cron should start an agent turn with job context; this skill instructs Luna to compose the brief (not long monologues).

## Tools (optional direct dispatch)

| Tool | Tier | Notes |
| --- | --- | --- |
| `heartbeat_morning_brief` | Auto | Runs `maybe_morning_brief` pipeline |
| `heartbeat_weekly_review` | Auto | Runs `maybe_weekly_review` pipeline |

## References

- `{baseDir}/references/cron-jobs.md`
- `{baseDir}/references/harness-map.md`
- `agent-plan/operations/hosting.md` (always-on Gateway)
