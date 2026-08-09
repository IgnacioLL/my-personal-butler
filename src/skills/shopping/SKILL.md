---
name: shopping
description: Propose purchases under spend caps; execute only after hard Accept; freeze spending blocks buys; dry-run default.
metadata: {"openclaw":{"skillKey":"shopping","optionalEnv":["SHOPPING_LIVE"]}}
user-invocable: true
---

# Shopping

Prepare purchases and optionally complete them without going crazy on the card.

## Safety (mandatory)

1. **Hard approve** every purchase (`action_type: buy`).
2. Propose-only until Accept — never auto-buy from chat text alone.
3. **Spend caps** (daily / weekly) block execute even after Accept (`INV-PAY-002`).
4. **`freeze spending`** kill switch blocks execute even with a stale accepted
   approval (`INV-PAY-001`).
5. **Dry-run by default.** Live charge requires **both**:
   - production config `mode: live`
   - env `SHOPPING_LIVE=1`
6. Never set the live flag in CI. CI uses dry-run merchant +
   `config/shopping.harness.json` + `fixtures/shopping/merchant-catalog.json`.
7. New merchants: first purchase always hard approve. Cap breach is not overridden
   by “just buy it” chat.

## Config

- Production: `{baseDir}/../../config/production/shopping.json`
- Harness/CI: `config/shopping.harness.json`
- OpenClaw snippet: `config/production/openclaw.skills.snippet.json`

## Flow

```text
“Buy more of my protein powder”
  → memory recalls brand/size
  → merchant adapter search (prefer usual rebuy)
  → show option + total (hard approve)
  → Accept under cap + freeze off
  → dry-run receipt (default) or live charge if SHOPPING_LIVE=1 and mode=live
  → WhatsApp receipt summary
```

## Anti-crazy rules

1. One purchase intent → one proposal (unless owner asks for alternatives)
2. No upselling beyond the request
3. Prefer rebuying known items
4. Freeze switch disables execute immediately

## Invariants (CI gates)

- `INV-PAY-001` — freeze blocks stale accepted buy
- `INV-PAY-002` — spend cap enforcement

See `agent-plan/capabilities/shopping.md` and `docs/bookings-shopping-production.md`.
