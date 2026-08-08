# Testing strategy

## What “good” means here

This is not a web CRUD app. It is an always-on agent with tools, memory, voice, and irreversible actions. Testing must prioritize:

1. **Safety invariants** over pretty demos
2. **Deterministic doubles** over live WhatsApp/Booksy whenever possible
3. **Machine-judgable artifacts** over “looks fine to me”
4. **Autonomy** — an AI agent should be able to run, diagnose, and re-verify without a human in the loop

## Autonomy-first principles

### 1. No human required for the happy/regression path

Every phase exit criterion should be expressible as a command (or small command set) that exits non-zero on failure and writes a report under a known path (e.g. `artifacts/test/…`).

### 2. Replace humans with oracles

| Human judgment today | Autonomous substitute |
| --- | --- |
| “Did it remind me?” | assert reminder record + due timestamp in store |
| “Did it ask before buying?” | assert no commerce execute call before approval=accepted |
| “Was the transcript OK?” | fixture audio with expected transcript string / WER threshold |
| “Did Android show Accept?” | approval API/state assertion + optional UI snapshot diff |
| “Is the reply helpful?” | rubric-scored eval on frozen transcript fixtures (separate from CI blockers unless flaky-controlled) |

### 3. Live third parties are opt-in

Default CI uses mocks:

- WhatsApp channel → inbound fixture injector / mock transport
- Twilio → mock voice provider (OpenClaw already has mock-style paths conceptually)
- Calendar → fake calendar backend
- Booksy → recorded browser fixtures / stub portal
- Payments → dry-run merchant adapter

Nightly or manual “live smoke” flags may hit real services, but they are **not** the merge gate.

### 4. Tailor depth to the component

Not everything needs full e2e.

- Parsers, caps, expiry math → unit only is enough
- Approval matrix → heavy contract + property tests
- Reminder cron → integration with fake clock
- Booking/shopping/self-mod → gate tests + simulated execute; limited staged e2e

See [component-matrix.md](./component-matrix.md).

### 5. Time is a first-class test dependency

Reminders, quiet hours, approval expiry, and habit escalation need a **fake clock**. Never sleep wall-clock minutes in CI.

### 6. Flake policy

- Retry once for known-network live smoke only
- CI mocks must be deterministic; flakes are bugs
- Model-output checks that are non-deterministic belong in eval lanes with tolerances, not hard unit asserts on exact prose (assert structure/tools/state instead)

## What we explicitly do *not* rely on

- Manual WhatsApp tapping for every PR
- “Ask the user if grandma reminder worked”
- Unbounded browser runs against production Booksy in CI
- Self-mod applying to `main` as a test side effect

## Test environments

| Env | Purpose |
| --- | --- |
| `unit` | pure functions, no IO |
| `harness` | Gateway + mocks in-process or docker-compose |
| `staged` | near-real adapters, fake money, disposable calendar |
| `live-smoke` | rare; real WhatsApp/Twilio; gated; artifact-heavy |

## Definition of done for a feature

A capability is not done when it “worked once on my phone.” It is done when:

1. invariants covering it are green in CI
2. component tests listed in the matrix exist
3. at least one e2e journey covering it is green in `harness`
4. an AI agent can re-run the suite and produce a pass/fail report without human steps
