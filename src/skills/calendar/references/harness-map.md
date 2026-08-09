# Map calendar OpenClaw skill tools → harness ActionGateway / adapters.

| Skill intent | action_type | Tier | Adapter |
| --- | --- | --- | --- |
| Read upcoming / free slots | `calendar_read` | Auto | store / `sync_window` |
| Propose create | `calendar_create` | Soft confirm | propose only (`create_count=0`) |
| Accept create | `calendar_create` execute | Soft (after Accept) | `StubCalendarAdapter` or `GoogleCalendarAdapter` |
| Modify / cancel | `calendar_modify` / `calendar_cancel` | Soft confirm | same |

## Production wiring

- Config: `config/production/calendar.json`
- Secrets: `config/production/calendar.env.example`
- Factory: `capabilities.calendar.factory.build_calendar_adapter`
- Soft confirm: `policy.action_gateway.ActionGateway`
- Conflicts: `CalendarStore.find_conflicts` + `suggest_free_slots`

## CI

Always `CALENDAR_MODE=memory` → `StubCalendarAdapter`. See `INV-APPR-003`, E2E-04.
