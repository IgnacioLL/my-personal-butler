# Personal Agent

An always-on **OpenClaw Gateway**–centric personal agent: WhatsApp-first, voice-capable, memory-aware, and gated by explicit approvals for money, external side effects, and self-modification.

**Planning docs live in [`agent-plan/`](./agent-plan/index.md)** — read those before changing runtime behavior.

## Repository layout

```text
.
├── agent-plan/          # Product + testing plan (source of truth for design)
├── config/              # Gateway + harness config placeholders (no secrets)
├── src/
│   ├── harness/         # Fake clock, outbound catcher, INV runner (CI doubles)
│   ├── invariants/      # Discoverable INV-* contract checks
│   ├── policy/          # Ingress allowlist helpers
│   ├── skills/          # OpenClaw skills
│   └── tools/           # Shared tool helpers
├── fixtures/            # Deterministic test inputs (audio, approvals, calendar, …)
├── scripts/             # CI and dev helpers (`test:ci`)
├── artifacts/test/      # Machine-readable test outputs (gitignored except README)
└── status.md            # Implementation tracker (planner-owned)
```

We **do not** ship a custom orchestration runtime. The OpenClaw Gateway is the control plane; this repo adds skills, tools, config, and verification harnesses around it. See [architecture](./agent-plan/architecture.md).

## Getting started

1. Read [`agent-plan/index.md`](./agent-plan/index.md) and the testing docs under [`agent-plan/testing/`](./agent-plan/testing/index.md).
2. Copy config placeholders from [`config/`](./config/README.md) when wiring a local or harness Gateway profile. Production OpenClaw (Codex/Luna + WhatsApp QR): [`config/openclaw/`](./config/openclaw/README.md).
3. Track implementation progress in [`status.md`](./status.md).

## Running tests

Merge gate `test:ci` (see [`docs/ci-gates.md`](./docs/ci-gates.md) for full INV + E2E map):

| Command | Expectation |
| --- | --- |
| `./scripts/test-ci.sh` or `make test-ci` | **PASS** (exit 0) when invariants healthy |
| `./scripts/test-ci.sh --break-invariant` | **FAIL** (exit ≠ 0) — deliberate broken allowlist |
| `make test-ci-fail-closed` | **PASS** only if the broken mode fails (fail-closed proof) |

Layers run in order: **unit** → **contract/INV-*** → **integration** (harness profile) → **e2e** (gate-tagged E2E-01..10, including E2E-07/E2E-08 deny paths). Artifacts land under `artifacts/test/ci/` (`report.json`, `report.md`, `verification.json`, per-layer dirs, `outbound-messages.json`).

Nightly (non-blocking): `make soak-chaos` — restart, duplicate webhooks, clock jumps (see ci-gates.md).

### Agent B verification

1. `git pull` on `cursor/status-and-delegate-c450`
2. Happy path: `make test-ci` → exit 0; read `artifacts/test/ci/verification.json` (`result: PASS`, `gate_e2e` × 10, `invariants` × 23)
3. Fail-closed: `make test-ci-fail-closed` → exit 0 of the make target (inner CI must have failed)
4. Audit map: [`docs/ci-gates.md`](./docs/ci-gates.md)
5. Do not weaken invariants to go green

Stdlib Python 3 only — no pip installs required for `test:ci`.

## Fixtures

Deterministic packs under [`fixtures/`](./fixtures/README.md): `audio/`, `approvals/`, `calendar/`, `memory/`, `browser/`, `selfmod/`. No real secrets or PII.

## Implementation status

See [`status.md`](./status.md) for phased tasks, acceptance criteria, and dispatch log.
