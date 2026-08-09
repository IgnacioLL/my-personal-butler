---
name: calendar
description: Read primary calendar and create/update/cancel events only after soft confirm; Google production adapter with conflict-aware suggestions.
metadata: {"openclaw":{"skillKey":"calendar","requires":{},"optionalEnv":["CALENDAR_LIVE","CALENDAR_MODE","GOOGLE_CALENDAR_CLIENT_ID","GOOGLE_CALENDAR_CLIENT_SECRET","GOOGLE_CALENDAR_REFRESH_TOKEN"]}}
user-invocable: true
---

# Calendar (Google)

Let the agent see your availability and schedule things without colliding with real life.

## Safety (mandatory)

1. **Soft confirm** before any calendar write (`calendar_create` / `modify` / `cancel`).
2. Propose → pending approval → Android/WhatsApp Accept → execute adapter write.
3. **Dry-run by default.** Live Google writes require **both**:
   - production config `live: true` **or** env `CALENDAR_LIVE=1`
   - OAuth secrets from `config/production/calendar.env.example`
4. Never set `CALENDAR_LIVE` or `CALENDAR_MODE=google` in CI.
   CI uses in-memory `StubCalendarAdapter` (`config/calendar.harness.json`).
5. When the proposed slot conflicts, call it out and suggest free alternatives
   before asking for soft confirm — do not silently overwrite.
6. Inviting other people → hard approve (later); v1 is owner calendar only.

## Config

- Production: `{baseDir}/../../config/production/calendar.json`
- Secrets: `config/production/calendar.env.example` → `calendar.local.env`
- Harness/CI: `config/calendar.harness.json` + `fixtures/calendar/`
- Adapter: `src/capabilities/calendar/google.py` (stdlib HTTPS)
- Factory: `src/capabilities/calendar/factory.py` (`CALENDAR_MODE=memory|google`)

## Flow

```text
User ask (WhatsApp)
  → read primary calendar / local mirror (Auto)
  → conflict check + free-slot suggestions
  → propose soft confirm card (create_count stays 0)
  → Accept on Android/WhatsApp
  → GoogleCalendarAdapter.create (dry-run or live)
  → confirm back on WhatsApp
```

## Approval card must show

- title
- start / end / timezone
- conflicts (if any) + suggested free slot
- soft confirm required

## Invariants (CI gates)

- `INV-APPR-003` — soft-confirm calendar writes do not hit the adapter before confirm
- E2E-04 — accept creates once; deny creates nothing

See `agent-plan/capabilities/calendar.md` and `docs/calendar-production.md`.
