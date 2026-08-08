# End-to-end flows

Cross-component journeys run on the Virtual User harness with mocks. Each flow lists setup, steps, and **machine checks**.

## E2E-01 — Voice reminder

**Setup:** seed timezone; fake clock Monday 10:00.

1. Inject audio fixture: “Remind me Sunday at 18:00 to call grandma.”
2. STT stub returns expected transcript.
3. Agent creates reminder.

**Checks:** reminder exists; due = next Sunday 18:00 local; outbound confirm message captured; no hard approval created.

## E2E-02 — Habit escalation ladder

**Setup:** recurring high-priority habit; quiet hours off.

1. Advance clock to fire time → WhatsApp reminder sent.
2. Advance without completion → Android notification recorded.
3. Advance again → mock outbound call placed.
4. After-call summary queued to WhatsApp.

**Checks:** ordered channel touches; call tools exclude buy/book/self-mod-apply.

## E2E-03 — Todo WhatsApp → Android

1. Text: “Add todo: buy oat milk.”
2. Read Android projection API.

**Checks:** same todo id/title/status; completing via Android API reflects in agent store.

## E2E-04 — Calendar soft confirm

1. “Schedule focus block Friday 09:00–11:00.”
2. Observe pending soft confirm; calendar adapter create count = 0.
3. Accept soft confirm.

**Checks:** event created once; deny path creates nothing.

## E2E-05 — Diet plan → groceries

1. Seed memory with dislikes/allergies.
2. “Plan meals for tomorrow.”
3. Agent returns structured plan + grocery todos.

**Checks:** disliked ingredients absent; grocery todos created; optional eval score ≥ threshold in eval lane.

## E2E-06 — Booksy propose → approve → book

1. Seed shop prefs + free calendar afternoon.
2. “Book a haircut next week afternoon.”
3. Stub portal returns slots; agent proposes 2–3 options.
4. Execute count = 0 until Accept.
5. Accept chosen slot.

**Checks:** one book execute; calendar writeback; WhatsApp confirmation; deny leaves execute at 0.

## E2E-07 — Shopping with cap / freeze

1. “Buy my usual protein powder.”
2. Proposal shows price; execute = 0.
3. Accept under cap → dry-run purchase logged.
4. Repeat with freeze on → execute blocked.
5. Repeat over cap → blocked with cap reason.

**Checks:** `INV-PAY-*` held; receipt/audit present on success.

## E2E-08 — Self-mod patch

1. “Add quiet hours: no calls after 22:00.”
2. Agent proposes diff on allowlisted path.
3. Apply tools unavailable until Accept.
4. Accept → patch applied on branch; audit has approval id.
5. Deny variant → working tree unchanged.

**Checks:** `INV-SELF-*`; rollback ref present.

## E2E-09 — Ignored hard approval expires

1. Create booking approval.
2. Advance clock past expiry.
3. Attempt late Accept.

**Checks:** status expired/cancelled policy; execute still 0.

## E2E-10 — Restart mid-flight

1. Create pending purchase approval.
2. Restart harness Gateway.
3. Pending approval still visible; Accept still works once.

**Checks:** durability of approval store; no duplicate execute.

## Coverage rule

Every build-roadmap phase exit must map to at least one E2E flow above (or a new flow added here first).
