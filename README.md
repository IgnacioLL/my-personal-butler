# Personal Agent

An always-on **OpenClaw Gateway**–centric personal agent: WhatsApp-first, voice-capable, memory-aware, and gated by explicit approvals for money, external side effects, and self-modification.

**Planning docs live in [`agent-plan/`](./agent-plan/index.md)** — read those before changing runtime behavior.

## Repository layout

```text
.
├── agent-plan/          # Product + testing plan (source of truth for design)
├── config/              # Gateway + harness config placeholders (no secrets)
├── src/                 # Custom OpenClaw skills/tools (extend Gateway primitives)
├── fixtures/            # Deterministic test inputs (audio, approvals, calendar, …)
├── scripts/             # CI and dev helpers
├── artifacts/test/      # Machine-readable test outputs (gitignored except README)
└── status.md            # Implementation tracker (planner-owned)
```

We **do not** ship a custom orchestration runtime. The OpenClaw Gateway is the control plane; this repo adds skills, tools, config, and verification harnesses around it. See [architecture](./agent-plan/architecture.md).

## Getting started

1. Read [`agent-plan/index.md`](./agent-plan/index.md) and the testing docs under [`agent-plan/testing/`](./agent-plan/testing/index.md).
2. Copy config placeholders from [`config/`](./config/README.md) when wiring a local or harness Gateway profile.
3. Track implementation progress in [`status.md`](./status.md).

## Running tests

T0 scaffolding is in place; TASK-01 will add invariant runners, fake clock, and real gates.

**CI entrypoint (stub today):**

```bash
./scripts/test-ci.sh
# or
make test-ci
```

The stub exits successfully and prints which layers TASK-01 will wire (unit, contract, integration, INV-*). Once TASK-01 lands, `test:ci` must **fail closed** on broken invariants.

Test artifacts are written under `artifacts/test/<task-or-flow>/` per [`agent-plan/testing/harnesses-and-fixtures.md`](./agent-plan/testing/harnesses-and-fixtures.md).

## Fixtures

Deterministic packs under [`fixtures/`](./fixtures/README.md): `audio/`, `approvals/`, `calendar/`, `memory/`, `browser/`, `selfmod/`. No real secrets or PII.

## Implementation status

See [`status.md`](./status.md) for phased tasks, acceptance criteria, and dispatch log.
