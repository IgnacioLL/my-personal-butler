# Browser fixtures

Booksy-like HTML stubs and recorded portal sessions for booking skill tests.

- `booksy-stub-slots.json` — deterministic Main St Barber slots for TASK-19 / E2E-06
  (stub portal; no live Booksy). **CI-only** — production uses
  [`config/production/bookings.json`](../../config/production/bookings.json) +
  browser skill; live gated by `BOOKINGS_LIVE`.

See [`agent-plan/capabilities/bookings.md`](../../agent-plan/capabilities/bookings.md)
and [`docs/bookings-shopping-production.md`](../../docs/bookings-shopping-production.md).
