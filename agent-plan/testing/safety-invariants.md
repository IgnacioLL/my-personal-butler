# Safety invariants

These are **merge blockers**. If any fail, the change is not done — regardless of demos.

Express each as an automated test with a stable id.

## Ingress

| ID | Invariant |
| --- | --- |
| `INV-INGRESS-001` | Non-allowlisted WhatsApp sender produces no agent tools and no outbound side effects |
| `INV-INGRESS-002` | Group messages are ignored while groups are disabled |
| `INV-INGRESS-003` | Every inbound voice note either yields a transcript turn or a clarification ask — never a silent guessed intent for hard actions |

## Approvals

| ID | Invariant |
| --- | --- |
| `INV-APPR-001` | Hard actions (buy, book, self-mod apply, policy change) cannot execute without `approval.status == accepted` |
| `INV-APPR-002` | `denied` and `expired` approvals never execute |
| `INV-APPR-003` | Soft-confirm calendar writes do not hit the calendar adapter before confirm |
| `INV-APPR-004` | Approval expiry uses the clock; advancing past expiry transitions status without execute |
| `INV-APPR-005` | Call-mode sessions cannot invoke buy/book/self-mod-apply tools |

## Money & bookings

| ID | Invariant |
| --- | --- |
| `INV-PAY-001` | Spend freeze blocks commerce execute even if a stale approval exists (or approvals are cancelled on freeze — pick one policy and test it) |
| `INV-PAY-002` | Cap breach blocks execute and surfaces a clear rejection artifact |
| `INV-BOOK-001` | Booking adapter execute count stays 0 until Accept |
| `INV-BOOK-002` | Failed booking cannot mark the user-facing task as success |

## Self-mod

| ID | Invariant |
| --- | --- |
| `INV-SELF-001` | Writes outside path allowlist fail closed |
| `INV-SELF-002` | `freeze self-mod` disables apply/write tools immediately |
| `INV-SELF-003` | Apply without Accept is impossible in harness |
| `INV-SELF-004` | Secrets patterns are rejected from proposed commits |

## Kill switches

| ID | Invariant |
| --- | --- |
| `INV-KILL-001` | `pause agent` stops proactive cron emissions |
| `INV-KILL-002` | `cancel pending` flips all pending approvals to cancelled and prevents execute |

## Audit

| ID | Invariant |
| --- | --- |
| `INV-AUDIT-001` | Every successful side effect write leaves an audit record referencing approval id when gated |

## Policy for changing invariants

Weakening an invariant requires:

1. explicit doc change in this file
2. a **policy-change** self-mod approval subtype in product
3. CI still proving the new invariant holds

Never delete an invariant test “temporarily” to go green.
