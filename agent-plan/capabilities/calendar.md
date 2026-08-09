# Calendar

## Purpose

Let the agent see your availability and schedule things without colliding with real life.

## Scope (v1)

- Read primary calendar
- Propose events
- Create/update/cancel with **soft confirmation**
- Respect quiet hours / buffers when planning
- Conflict-aware suggestions (call out overlaps; propose free slots)

## Intents

- “What’s on my calendar tomorrow?”
- “Schedule deep work Friday morning”
- “Find an afternoon next week for a haircut”
- “Move my dentist appointment” (later if provider allows)

## Write policy

| Action | Tier |
| --- | --- |
| Read | Auto |
| Create event | Soft confirm |
| Modify/cancel | Soft confirm |
| Invite other people | Hard approve (later) |

## Planning heuristics

- Prefer your historically liked time windows (from memory)
- Leave travel buffers for physical appointments
- When booking external services, hold a tentative local event only after approval strategy is clear
- Never silently double-book — surface conflicts + alternatives on the soft-confirm card

## Integrations

**Provider:** Google Calendar (OAuth2 + Calendar API v3).

| Mode | Adapter | Config |
| --- | --- | --- |
| Harness / CI | In-memory `StubCalendarAdapter` | `config/calendar.harness.json` |
| Production | `GoogleCalendarAdapter` (stdlib HTTPS) | `config/production/calendar.json` + `calendar.env.example` |

Soft-confirm write path is identical in both modes: `ActionGateway.propose` → Accept → `adapter.create`. Live Google writes require `CALENDAR_LIVE=1` (dry-run default). See [docs/calendar-production.md](../../docs/calendar-production.md) and [src/skills/calendar/SKILL.md](../../src/skills/calendar/SKILL.md).

## Acceptance criteria

- [x] Agent can summarize upcoming events accurately (store / sync_window)
- [x] Agent refuses to double-book without calling it out (conflict + suggestions)
- [x] Event creation requires confirmation (`INV-APPR-003`, E2E-04)
- [x] Timezone handling is correct (payload `timezone` + Google `timeZone` fields)
- [x] Production OAuth/config templates exist; secrets never committed
