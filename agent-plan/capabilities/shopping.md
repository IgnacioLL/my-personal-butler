# Shopping

## Purpose

Let the agent prepare purchases and optionally complete them — without going crazy on your card.

## Scope

### v2 (after bookings feel safe)
- Find a product matching a request
- Compare 1–3 options
- Draft cart / checkout plan
- Hard approve with price + merchant
- Execute purchase
- Create delivery/todo follow-ups

### Explicitly gated forever
- Recurring subscriptions
- Carts above spend cap
- New merchants (first time always hard approve)

## Approval + guardrails

| Guard | Rule |
| --- | --- |
| Hard approve | every purchase |
| Spend cap | daily / weekly limits in config |
| Merchant policy | allowlist after first success optional |
| Cooling | if you Deny, don’t re-ask spammy |
| Simulation | new shopping skill starts in propose-only mode |

See [../trust-and-safety/approval-matrix.md](../trust-and-safety/approval-matrix.md).

## Flow

```text
“Buy more of my protein powder”
  → memory recalls brand/size
  → search merchant
  → show option + total
  → Accept on Android
  → purchase
  → receipt summary on WhatsApp
```

## Anti-crazy rules

1. One purchase intent → one proposal (unless you ask for alternatives)
2. No upselling beyond the request
3. Prefer rebuying known items over novel discoveries
4. Freeze switch: “pause purchases” disables the skill immediately

## Acceptance criteria

- [ ] Agent can propose a purchase without executing
- [ ] Accept executes once; Deny never executes
- [ ] Cap breach blocks even if user text-says “just buy it” without raising cap
- [ ] Receipt/summary is logged
