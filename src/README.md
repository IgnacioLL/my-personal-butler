# Source (`src/`)

Custom code that extends the **OpenClaw Gateway** — skills, tools, and thin adapters when a workflow cannot be expressed with stock Gateway primitives alone.

```text
src/
├── skills/    # OpenClaw skills (reminders, calendar, bookings, …)
└── tools/     # Shared tool helpers used by skills
```

Prefer Gateway channels, cron, nodes, and approvals over new microservices. See [`agent-plan/architecture.md`](../agent-plan/architecture.md).

Self-modification of files under this tree requires the hard-approve path in [`agent-plan/capabilities/self-modification.md`](../agent-plan/capabilities/self-modification.md).
