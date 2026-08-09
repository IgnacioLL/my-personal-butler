---
name: reminders-habits
description: "Create one-shot and recurring reminders, habit schedules, snooze/cancel, and escalation ladders via WhatsApp."
metadata: { "openclaw": { "requires": { "config": ["skills.entries.reminders-habits.enabled"] } } }
---

# Reminders and habits

Natural-language reminders and weekly habits with explicit timezone. Maps to `capabilities/reminders/*` and OpenClaw **cron** for firing.

## When to use

- **One-shot**: “Remind me Sunday at 18:00 to call grandma.”
- **Recurring**: “Every Sunday remind me to call grandma.”
- **Habit**: recurring + escalation ladder (WhatsApp → Android → call for high priority).
- User asks to snooze or cancel an active reminder.

## Tools

| Tool | Tier | Harness module |
| --- | --- | --- |
| `reminder_create` | Auto | `ReminderService.create_from_utterance` |
| `habit_create` | Auto | same service with `as_habit=True` |
| `reminder_list` | Auto | `ReminderStore.list_active` |
| `reminder_snooze` | Auto | `ReminderStore.snooze` |
| `reminder_cancel` | Auto | `ReminderStore.cancel` |

### `reminder_create` / `habit_create` payload

```json
{
  "text": "call grandma",
  "timezone": "Europe/Madrid",
  "kind": "recurring",
  "due_at": "2026-01-11T18:00:00+01:00",
  "weekday": 6,
  "hour": 18,
  "minute": 0,
  "recipient": "+15550001111",
  "habit_priority": "normal",
  "escalation_enabled": false
}
```

Parse NL first with `capabilities.reminders.parse.parse_reminder` when the user speaks naturally.

## Scheduling

- **Production**: OpenClaw cron fires due reminders; outbound via WhatsApp default channel.
- **CI harness**: `FakeClock.advance` + `ReminderScheduler` (no wall sleep).
- **Pause**: `pause_agent` kill switch blocks proactive fires (`INV-KILL-001`).
- **Quiet hours**: proactive reminder fires respect profile quiet hours (see `heartbeat-ops`).

## Escalation ladder (habits)

1. WhatsApp reminder text
2. Android notification (`channels.android.notifications`)
3. Outbound call — high-priority habits only; mid-call tool allowlist applies (`INV-APPR-005`)

## Confirm outbound

After create, send a short WhatsApp confirm (`kind=reminder_confirm`). On fire: `kind=reminder_fire` or `Habit reminder:` prefix for habits.

## References

- `{baseDir}/references/harness-map.md`
- Product spec: `agent-plan/capabilities/reminders-and-habits.md`
