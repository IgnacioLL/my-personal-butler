# Reminders and habits

## Purpose

Reliable follow-through for personal commitments:

- one-shot: “remind me tomorrow at 18:00 to call grandma”
- recurring: “every Sunday remind me to call grandma”
- accountability: “check that I followed my diet after dinner”

## Intents

- create / list / snooze / cancel reminders
- convert chat promises into reminders
- escalate ignored reminders to call (policy-based)

## Mechanics

- Prefer OpenClaw cron / heartbeat for scheduling
- Store timezone explicitly
- Support natural language dates resolved against calendar context
- Deliver via WhatsApp by default; escalate to call when configured

## Habit vs reminder

| Type | Behavior |
| --- | --- |
| Reminder | fires, then done/snoozed/cancelled |
| Habit | recurring; completion tracked; streaks optional later |

## Escalation ladder

1. WhatsApp message
2. Android notification
3. Outbound call (only for tagged high-priority habits)

## Acceptance criteria

- [ ] Create reminder from WhatsApp audio
- [ ] Recurring Sunday grandma call works across weeks
- [ ] Snooze/cancel from WhatsApp or Android
- [ ] Missed high-priority habit can trigger a call policy
