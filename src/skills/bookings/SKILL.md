---
name: bookings
description: Propose Booksy-class appointment slots and book only after hard Accept; calendar writeback on success.
metadata: {"openclaw":{"skillKey":"bookings","requires":{"config":["browser.enabled"]},"optionalEnv":["BOOKINGS_LIVE"]}}
user-invocable: true
---

# Bookings (Booksy-class)

Find and reserve real-world appointments (haircut, barber, spa) via Booksy-class sites.

## Safety (mandatory)

1. **Hard approve** before any reservation submit (`action_type: book`).
2. Propose slots only until the owner Accepts on Android/WhatsApp.
3. **Dry-run / propose-only by default.** Live booking requires **both**:
   - production config `mode: live`
   - env `BOOKINGS_LIVE=1`
4. Never set the live flag in CI. CI uses the stub portal only
   (`fixtures/browser/booksy-stub-slots.json`, `config/bookings.harness.json`).
5. Do not retry-book aggressively (double-booking risk). Cap book retries at 1.
6. Captcha / login / site change → stop, keep proposed times, ask owner to take over.

## Config

- Production: `{baseDir}/../../config/production/bookings.json` (or Gateway
  `skills.entries.bookings.config.productionConfig`)
- Harness/CI: `config/bookings.harness.json` + stub portal fixture
- OpenClaw snippet: `config/production/openclaw.skills.snippet.json`

## Flow

```text
User ask (WhatsApp)
  → prefs (shop, stylist, duration, windows)
  → calendar free slots
  → browser skill checks Booksy availability (separate browser profile)
  → propose 2–3 options (hard approve card)
  → Accept → execute reservation (only if live flags allow; else dry-run record)
  → WhatsApp confirm + calendar writeback
```

## Approval card must show

- shop / service
- date-time
- estimated price if known
- cancellation policy snippet if available

## Invariants (CI gates)

- `INV-BOOK-001` — book_count stays 0 until Accept
- `INV-BOOK-002` — failed booking ≠ user-facing success

See `agent-plan/capabilities/bookings.md` and `docs/bookings-shopping-production.md`.
