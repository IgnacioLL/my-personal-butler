# Test levels

## Pyramid (adapted for agents)

```text
            ┌────────────┐
            │ live-smoke │  rare, flagged, real channels
            └─────▲──────┘
             ┌────┴────┐
             │  e2e    │  full journeys on mocks/staged
             └────▲────┘
          ┌───────┴───────┐
          │ integration   │  gateway + 1–N adapters
          └───────▲───────┘
       ┌──────────┴──────────┐
       │ contracts / policy  │  approval, tool allowlists
       └──────────▲──────────┘
    ┌─────────────┴─────────────┐
    │ unit / pure logic         │
    └───────────────────────────┘
```

## Level details

### Unit

Fast, no network, no Gateway boot.

Examples: spend-cap math, quiet-hours check, reminder RRULE parsing, approval expiry, path-allowlist matcher for self-mod.

### Contract / policy

Assert interfaces and **invariants** between modules.

Examples:

- hard action → creates approval item; execute adapter not called
- call-mode tool list excludes buy/book/self-mod-apply
- WhatsApp non-allowlisted sender ignored

These are the highest ROI tests for this product.

### Integration

Boot enough of OpenClaw/Gateway (or a thin facade we own) with mocked channels/tools.

Examples: audio fixture → STT stub → agent turn → reminder created; todo created → Android projection updated.

### E2E (harness)

Multi-step user journeys driven by a scripted client (“virtual you”).

See [e2e-flows.md](./e2e-flows.md).

### Soak / chaos (later)

- clock jumps
- Gateway restart mid-pending-approval
- duplicate webhook delivery
- STT empty transcript
- approval Accept after expiry

### Eval (quality, not always merge-blocking)

Frozen prompts + expected tool traces / memory writes. Useful for diet planning quality and reply tone. Keep separate from safety CI unless stable.

## Mapping to commands (intent)

Exact tooling TBD at implementation, but plan for:

| Level | Example command intent |
| --- | --- |
| unit | `test:unit` |
| contract | `test:contracts` |
| integration | `test:integration` |
| e2e harness | `test:e2e` |
| live-smoke | `test:live-smoke` (manual/nightly flag) |
| all merge gates | `test:ci` |

Every command must emit JUnit/JSON + human markdown summary under `artifacts/`.
