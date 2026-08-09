# Source (`src/`)

Custom code that extends the **OpenClaw Gateway** — skills, tools, and thin adapters when a workflow cannot be expressed with stock Gateway primitives alone.

```text
src/
├── harness/       # Fake clock, outbound catcher, ingress sim, INV runner (CI)
├── invariants/    # Discoverable INV-* checks (contract/policy layer)
├── policy/        # Ingress allowlist helpers shared by stubs + future skills
├── skills/        # OpenClaw skills (reminders, calendar, bookings, …)
└── tools/         # Shared tool helpers used by skills
```

Prefer Gateway channels, cron, nodes, and approvals over new microservices. See [`agent-plan/architecture.md`](../agent-plan/architecture.md).

Harness doubles are for autonomous CI — not a second runtime. Self-modification of files under this tree requires the hard-approve path in [`agent-plan/capabilities/self-modification.md`](../agent-plan/capabilities/self-modification.md).
