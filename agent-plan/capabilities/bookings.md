# Bookings (Booksy and similar)

## Purpose

Have the agent find and reserve real-world appointments (haircut, barber, spa, etc.), especially via sites like Booksy.

## Scope

### v1.5
- Browse availability for a known provider/shop from memory
- Propose 2–3 slots that fit calendar + prefs
- Hard approve → complete booking
- Write calendar event + confirmation message

### Later
- Discover new providers
- Reschedule/cancel flows
- Multi-person bookings

## Flow

```text
User ask (WhatsApp)
  → read prefs (shop, stylist, duration, time windows)
  → read calendar free slots
  → browser skill checks Booksy availability
  → propose options
  → Android/WhatsApp hard approve
  → execute reservation
  → confirm + calendar write
```

## Approval

Always **hard approve** before submitting a reservation.

Approval card must show:

- shop / service
- date-time
- estimated price if known
- cancellation policy snippet if available

## Production vs CI

| Surface | Path | Live Booksy? |
| --- | --- | --- |
| CI / harness | Stub portal + `config/bookings.harness.json` | **Never** |
| Production skill | `src/skills/bookings/` + `config/production/bookings.json` | Only if `mode=live` **and** `BOOKINGS_LIVE=1` |

Defaults: dry-run / propose-only. Live flag is documented in
[`docs/bookings-shopping-production.md`](../../docs/bookings-shopping-production.md).
OpenClaw wiring: [`config/production/openclaw.skills.snippet.json`](../../config/production/openclaw.skills.snippet.json).

CI gates (must remain green): `INV-BOOK-001`, `INV-BOOK-002`, E2E-06.

## Failure handling

- Site changed / captcha / login required → stop and ask you to take over, keep proposed times
- Slot disappears → offer next best alternatives
- Never retry-book aggressively (double booking risk)

## Skill contents

- provider URL(s)
- login strategy (manual session / saved profile — decide carefully)
- preferred services list
- backup shops
- separate browser profile from personal browsing

## Acceptance criteria

- [x] Agent proposes valid slots that don’t conflict with calendar (harness + E2E-06)
- [x] No booking without Accept (`INV-BOOK-001`)
- [x] Successful booking produces WhatsApp confirmation + calendar event (stub portal)
- [x] Failed booking never leaves a false “done” state (`INV-BOOK-002`)
- [x] Production skill config + dry-run default + documented `BOOKINGS_LIVE` flag (PROD-08)
