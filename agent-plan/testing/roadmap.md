# Testing roadmap

Aligns testing maturity with [`../operations/roadmap.md`](../operations/roadmap.md). A build phase is not exited until its testing unlock is green in harness CI.

## T0 — with Phase 0 foundations

- repo test commands scaffolding
- artifact directory convention
- fake clock utility
- invariant framework skeleton (`INV-*` runner)
- WhatsApp allowlist contract tests

**Exit:** `test:ci` runs (even if few tests) and fails on a deliberate broken invariant.

## T1 — with Phase 1 voice/memory/reminders

- audio fixture pack + STT stub
- E2E-01 voice reminder
- memory write/read integration
- outbound message catcher

**Exit:** voice-note reminder journey green without a human phone.

## T2 — with Phase 2 Android control plane

- approval + todo API doubles for Android
- E2E-03 todo sync
- soft-confirm calendar path wired for E2E-04 (calendar adapter can be shallow)

**Exit:** Accept/Deny can be exercised by Virtual User alone.

## T3 — with Phase 3 calendar/diet

- in-memory calendar conflicts
- E2E-04, E2E-05
- diet eval lane (non-blocking)

## T4 — with Phase 4 calls

- mock voice provider tests
- E2E-02 escalation ladder
- `INV-APPR-005` call tool allowlist

## T5 — with Phase 5 bookings

- stub portal
- E2E-06
- `INV-BOOK-*`

## T6 — with Phase 6 shopping

- dry-run merchant
- E2E-07 + cap/freeze invariants

## T7 — with Phase 7 self-mod

- sample allowlisted workspace fixtures
- E2E-08 + `INV-SELF-*`
- policy-change subtype tests

## T8 — with Phase 8 polish

- soak/chaos pack
- restart durability E2E-10
- tighten evals; optional limited live-smoke playbook

## Rule

If product roadmap wants to skip ahead (e.g. bookings before Android approvals), testing roadmap still requires **approval Virtual User** first — otherwise hard-approve cannot be autonomously proven.
