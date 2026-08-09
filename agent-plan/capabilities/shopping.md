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
| Simulation | new shopping skill starts in propose-only / **dry-run** mode |
| Freeze | `freeze spending` blocks execute even with stale Accept |
| Live charge | only if `mode=live` **and** `SHOPPING_LIVE=1` (never in CI) |

See [../trust-and-safety/approval-matrix.md](../trust-and-safety/approval-matrix.md).

## Flow

```text
“Buy more of my protein powder”
  → memory recalls brand/size
  → search merchant
  → show option + total
  → Accept on Android
  → purchase (dry-run default)
  → receipt summary on WhatsApp
```

## Production vs CI

| Surface | Path | Real money? |
| --- | --- | --- |
| CI / harness | Dry-run merchant + `config/shopping.harness.json` | **Never** |
| Production skill | `src/skills/shopping/` + `config/production/shopping.json` | Only if live flags both set |

Spend caps and freeze spending are mandatory on both paths.
Runbook: [`docs/bookings-shopping-production.md`](../../docs/bookings-shopping-production.md).
OpenClaw wiring: [`config/production/openclaw.skills.snippet.json`](../../config/production/openclaw.skills.snippet.json).

CI gates (must remain green): `INV-PAY-001`, `INV-PAY-002`, E2E-07.

## Anti-crazy rules

1. One purchase intent → one proposal (unless you ask for alternatives)
2. No upselling beyond the request
3. Prefer rebuying known items over novel discoveries
4. Freeze switch: “pause purchases” / `freeze spending` disables execute immediately

## Acceptance criteria

- [x] Agent can propose a purchase without executing (harness + E2E-07)
- [x] Accept executes once; Deny never executes
- [x] Cap breach blocks even if user text-says “just buy it” without raising cap (`INV-PAY-002`)
- [x] Freeze blocks stale accepted buy (`INV-PAY-001`)
- [x] Receipt/summary is logged (dry-run receipt in CI)
- [x] Production merchant adapter config + dry-run default + documented `SHOPPING_LIVE` flag (PROD-08)
