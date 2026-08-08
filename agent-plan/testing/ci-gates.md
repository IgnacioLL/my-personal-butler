# CI gates

## Merge gate (`test:ci`)

Must pass on every PR:

1. unit
2. contract/policy (including **all** `INV-*` invariants)
3. integration (harness profile)
4. e2e flows tagged `gate` (at least E2E-01, E2E-03, E2E-04, E2E-07 deny path, E2E-08 deny path — expand as phases land)

Fail closed on invariant failure.

## Nightly (optional)

- fuller e2e pack
- soak/chaos (restart, duplicate webhooks, clock jumps)
- eval lane for diet/reply quality with budget caps
- staged adapter tests (still no real money)

## Live-smoke (manual/flagged)

- real WhatsApp text ping
- one real audio note on a dedicated test thread
- optional Twilio mock→real ladder

Never blocking merge unless you explicitly promote a tiny subset later.

## Branch protections (intent)

- cannot merge with failing `test:ci`
- cannot skip invariant suite
- self-mod apply to the agent repo in production still requires product-level hard approve (CI green ≠ auto-apply on the phone agent)

## Reports

CI publishes:

- markdown summary comment-friendly report
- JSON for agent consumption
- retained traces for failed jobs
