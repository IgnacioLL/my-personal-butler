# Bookings + shopping production (hard approve)

Operator runbook for enabling Booksy-class bookings and shopping merchant adapters
on an always-on OpenClaw Gateway. **CI stays on stub portal / dry-run merchant.**

## Artifacts

| Kind | Path |
| --- | --- |
| Bookings production config | [`config/production/bookings.json`](../config/production/bookings.json) |
| Shopping production config | [`config/production/shopping.json`](../config/production/shopping.json) |
| OpenClaw skills snippet | [`config/production/openclaw.skills.snippet.json`](../config/production/openclaw.skills.snippet.json) |
| Bookings skill | [`src/skills/bookings/SKILL.md`](../src/skills/bookings/SKILL.md) |
| Shopping skill | [`src/skills/shopping/SKILL.md`](../src/skills/shopping/SKILL.md) |
| CI bookings harness | [`config/bookings.harness.json`](../config/bookings.harness.json) |
| CI shopping harness | [`config/shopping.harness.json`](../config/shopping.harness.json) |

## Safety defaults (non-negotiable)

1. **Hard approve** for `book` and `buy` — no auto-execute from chat.
2. **Dry-run default** — production configs ship with `"mode": "dry_run"`.
3. **Spend caps** on shopping (daily / weekly) — cap breach blocks execute (`INV-PAY-002`).
4. **`freeze spending`** blocks shopping execute even with a stale accepted approval (`INV-PAY-001`).
5. Stub Booksy portal + dry-run merchant remain the **only** CI paths (`INV-BOOK-*`, `INV-PAY-*`).

## Live flags (documented; off by default)

Live side effects require **both** config mode and env flag:

| Skill | Config | Env | Effect when both set |
| --- | --- | --- | --- |
| Bookings | `"mode": "live"` in `bookings.json` | `BOOKINGS_LIVE=1` | Real Booksy-class reservation submit |
| Shopping | `"mode": "live"` in `shopping.json` | `SHOPPING_LIVE=1` | Real merchant charge / checkout |

Either alone keeps dry-run. Under `CI=1` / `OPENCLAW_CI=1` / `PERSONAL_AGENT_CI=1` /
`GITHUB_ACTIONS=true`, loaders always resolve to dry-run (`assert_ci_safe`).

```bash
# Example — operator host only, after hard-approve UX is proven:
export BOOKINGS_LIVE=0   # keep off until ready
export SHOPPING_LIVE=0
# Edit config/production/*.json mode only when intentionally going live.
```

**Never** export live flags in CI jobs or `make test-ci`.

## Enablement order

1. Keep skills `enabled: false` in OpenClaw until WhatsApp + Android approvals work.
2. Merge `config/production/openclaw.skills.snippet.json` into Gateway config;
   point `skills.load.extraDirs` at `./src/skills`.
3. Fill `REPLACE_*` shop / merchant URLs in production JSON (no secrets in git).
4. Use a **separate browser profile** for bookings (`browser.profile_name: bookings`).
5. Run propose → Accept once in dry-run; confirm calendar writeback / receipt.
6. Only then consider live flags (human decision — real money / external reservation).

## Kill switches

| Switch | Shopping | Bookings |
| --- | --- | --- |
| `freeze spending` | Blocks buy execute | n/a (not a payment) |
| `pause agent` | No proactive propose | No proactive propose |
| `cancel pending` | Pending buys cancelled | Pending books cancelled |

## CI gates (must stay green)

```bash
make test-ci
make test-ci-fail-closed
```

Invariants: `INV-BOOK-001`, `INV-BOOK-002`, `INV-PAY-001`, `INV-PAY-002`.
E2E: `make e2e-06` (bookings), `make e2e-07` (shopping).

## Capability docs

- [`agent-plan/capabilities/bookings.md`](../agent-plan/capabilities/bookings.md)
- [`agent-plan/capabilities/shopping.md`](../agent-plan/capabilities/shopping.md)
