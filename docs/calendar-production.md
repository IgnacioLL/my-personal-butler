# Google Calendar production (PROD-06)

Soft-confirm calendar writes against Google Calendar API v3. Harness CI stays on the in-memory stub.

## What ships

| Piece | Path |
| --- | --- |
| Production adapter | `src/capabilities/calendar/google.py` |
| Factory (memory vs google) | `src/capabilities/calendar/factory.py` |
| Production config | `config/production/calendar.json` |
| Secrets template | `config/production/calendar.env.example` → `calendar.local.env` |
| Harness profile | `config/calendar.harness.json` |
| OpenClaw skill | `src/skills/calendar/SKILL.md` |

## Soft-confirm write path (unchanged)

```text
propose(calendar_create)  → create_count = 0
Accept (Android / WhatsApp)
execute(approval_id)      → GoogleCalendarAdapter.create once
```

`INV-APPR-003` and E2E-04 gate this for the in-memory stub. The Google adapter uses the same counters and gateway path.

## Operator setup

1. Google Cloud Console → enable **Google Calendar API** → OAuth client (Desktop).
2. Complete offline consent once; save `refresh_token`.
3. `cp config/production/calendar.env.example config/production/calendar.local.env`
4. Fill `GOOGLE_CALENDAR_CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN`.
5. Set `CALENDAR_MODE=google` (and optionally `CALENDAR_PROFILE=./config/production/calendar.json`).
6. Verify dry-run: leave `CALENDAR_LIVE` unset — adapter shapes API payloads and updates the local mirror only.
7. When ready for real writes: set `CALENDAR_LIVE=1` (or `"live": true` in the production JSON).

## Conflict-aware suggestions

`CalendarService` still runs conflict detection + free-slot suggestions against the attached `CalendarStore` before soft confirm. In production, call `GoogleCalendarAdapter.sync_window(time_min, time_max)` to refresh the mirror from Google before proposing; dry-run/CI seed from `fixtures/calendar/`.

## CI safety

- Default factory mode is **memory** (`StubCalendarAdapter`).
- `make test-ci` must not set `CALENDAR_MODE=google` or `CALENDAR_LIVE`.
- Production JSON keeps `"live": false`.

## Secrets

Never commit `calendar.local.env`, token JSON files, or real client secrets. `.gitignore` covers `config/production/*.local.env` and `config/calendar.local.*`.
