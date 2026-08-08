# Testing

How we prove the personal agent works — designed so an **AI coding agent can verify most behavior autonomously**, without waiting on human review for ordinary passes/fails.

## Goal

Every important behavior should have:

1. a **falsifiable claim**
2. a **harness** that can drive it without a human clicking around
3. an **artifact** (logs, diffs, screenshots, JSON reports) another agent can judge
4. a **gate** that blocks merge/deploy on invariant failures

Humans are reserved for rare production-channel smoke and subjective “does this feel right?” checks — not for routine regression.

## Document map

```text
testing/
├── index.md                 ← you are here
├── strategy.md              ← philosophy + autonomy rules
├── test-levels.md           ← unit → contract → integration → e2e → soak
├── component-matrix.md      ← what each part needs (tailored)
├── harnesses-and-fixtures.md
├── safety-invariants.md     ← must-never-break rules (CI blockers)
├── e2e-flows.md             ← cross-component journeys
├── autonomous-agent-process.md  ← how an AI runs the loop alone
├── ci-gates.md
├── roadmap.md               ← testing unlocks aligned to build phases
└── components/
    ├── channels.md
    ├── intelligence.md
    ├── capabilities.md
    ├── trust-and-approvals.md
    └── self-modification.md
```

## Read order

1. [Strategy](./strategy.md)
2. [Safety invariants](./safety-invariants.md)
3. [Component matrix](./component-matrix.md)
4. [E2E flows](./e2e-flows.md)
5. [Autonomous agent process](./autonomous-agent-process.md)

## Default stance by risk

| Risk class | Example | Minimum proof |
| --- | --- | --- |
| Pure logic | date parsing, cap math | unit tests |
| Policy | hard-approve cannot auto-run | contract + adversarial cases |
| Integration | calendar mock, STT fixture | integration harness |
| Side effect | book / buy / apply patch | simulated execute + approval gate tests; staged e2e behind flags |
| Subjective UX | tone of WhatsApp reply | sampled eval set, scored automatically when possible |

## Link back to product plan

- Capabilities live under [`../capabilities/`](../capabilities/index.md)
- Approvals under [`../trust-and-safety/`](../trust-and-safety/index.md)
- Build phases under [`../operations/roadmap.md`](../operations/roadmap.md)
