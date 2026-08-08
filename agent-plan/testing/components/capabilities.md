# Testing: capabilities

Reminders, todos, calendar, diet, bookings, shopping. (Self-mod has its own doc.)

## Reminders & habits

**Heavy on unit + integration with fake clock; e2e for one voice path.**

| Case | Level |
| --- | --- |
| One-shot natural language → correct due | U/I |
| Recurring weekly stable across DST if relevant | U |
| Snooze/cancel | I |
| Escalation ladder | E (E2E-02) |
| Pause agent stops proactive emits | C |

## Todos

| Case | Level |
| --- | --- |
| Create/list/complete | I |
| Dedup near-identical open todos | U/I |
| WhatsApp ↔ Android sync | E |

## Calendar

| Case | Level |
| --- | --- |
| Read summary | I |
| Conflict detection | U/I |
| Soft confirm gate | C/E |
| Timezone correctness | U/I |

Live Google OAuth belongs in staged/live-smoke, not merge CI.

## Diet & planning

| Case | Level |
| --- | --- |
| Respects allergies/dislikes from memory | I/E |
| Emits grocery todos | E |
| Check-in reminder scheduled | I |
| Plan quality | Ev (non-blocking) |

Assert **constraints and structure** (JSON/schema), not essay sameness.

## Bookings

| Case | Level |
| --- | --- |
| Slot proposals fit calendar | I/E |
| Execute = 0 until Accept | C/E |
| Success → calendar + confirm | E |
| Stub failure → no false success | I |
| No prod Booksy mutations in CI | C (env guard) |

## Shopping

| Case | Level |
| --- | --- |
| Proposal only by default | C |
| Accept dry-run purchase | E |
| Cap / freeze | C/E |
| No upsell assertions optional | Ev |

## Shared pattern for new capabilities

Before coding the skill, add:

1. one invariant if gated
2. one integration with doubles
3. one e2e flow id in [`../e2e-flows.md`](../e2e-flows.md)
