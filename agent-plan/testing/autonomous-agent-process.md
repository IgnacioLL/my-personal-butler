# Autonomous agent verification process

How an AI coding agent should test this system **without human review** for ordinary work.

## Loop

```text
1. Read failing invariant / feature acceptance criteria
2. Choose smallest test level that can falsify it
3. Run harness command(s) → write artifacts/
4. Diagnose from report.json + traces (not vibes)
5. Patch
6. Re-run until green OR classify as blocked (missing fixture/mock)
7. Only then mark the task done
```

## Rules of engagement for the AI tester

1. **Prefer mocks** — do not ask a human to send a WhatsApp audio to “just check.”
2. **Assert state, not prose** — check tools, DB, approval status, adapter call counts.
3. **Record artifacts** — another agent must be able to audit your conclusion from files alone.
4. **No silent weakening** — if a test is wrong, fix the test with rationale in the PR; don’t delete invariants.
5. **Fake the clock** — never wait real minutes for cron.
6. **Separate eval from gate** — flaky model wording ≠ failed safety.
7. **Stop at true blockers** — live credentials, missing device, or real money paths: document as `BLOCKED` in the report with exact reason; do not pretend green.

## Definition of an autonomous “verified” claim

A claim like “hard approve works for shopping” is verified only if:

- named tests/invariants ran in this environment
- artifacts path is cited
- execute-count-before-accept = 0 shown in trace
- accept path shown once

Use a short machine-readable stamp in `artifacts/test/verification.json`:

```json
{
  "claim": "shopping execute requires hard accept",
  "result": "PASS",
  "invariants": ["INV-APPR-001", "INV-PAY-002"],
  "commands": ["test:e2e --flow E2E-07"],
  "artifacts": ["artifacts/test/e2e-07/report.json"]
}
```

## When human review is still allowed (exceptions)

Keep this list short on purpose:

- first-ever live WhatsApp pairing on a real phone number
- first live Twilio call to a real handset
- subjective voice quality / persona taste
- legal/safety policy decisions (e.g. raising spend caps)

Even then, the AI should prepare the checklist and artifacts so the human only confirms the irreducible bit.

## Suggested agent checklist per PR

- [ ] `test:ci` green
- [ ] New behavior mapped in [component-matrix.md](./component-matrix.md)
- [ ] New risky action covered by an invariant id
- [ ] E2E flow updated if user journey changed
- [ ] Artifacts uploaded/stored for the run
- [ ] No live-smoke required for merge
